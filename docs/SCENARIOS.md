# Edge-case scenarios: what is covered, what was added, what is out of scope

The file `req.txt` lists about 400 "what if" scenarios for an appointment system. This page sorts
all of them by theme. Each line says one of:

- **Covered**: the project already handled it before this review pass, and where to look.
- **Added**: built in this pass, with tests.
- **Partly**: handled for the single-clinic case, with the remainder named.
- **Out of scope**: far beyond a one-clinic, one-timezone scheduler built in a week, with the reason.
  The assignment keeps authentication, SMS and payments optional or out of the scope (plan section
  2); the rules that were graded come first.

The scenarios are quoted by their wording in `req.txt`, not by number, because the file restarts its
numbering several times.

## 1. Two requests for the same thing

| Scenario | Status | How |
|---|---|---|
| Two patients book the same slot at once; A cancels 10:00 while B and C request it; many requests compete for one resource; two simultaneous reschedules of one patient; a cancel racing a "completed"; a deadlock when appointments update together | **Covered** | Doctor row lock first, then the patient; PostgreSQL `EXCLUDE` constraints have the last word; one deterministic winner and a clean 409 for the rest. `tests/integration/test_booking_races.py`, 10-thread bursts |
| Patient clicks Book repeatedly; a retry creates a second confirmed appointment; the response times out and the patient retries; an integration sends the same booking event twice; a transaction succeeds but the app reports failure | **Covered, then Added** | A second identical click already gave `SLOT_TAKEN` with `same_patient: true`. **Added:** the `Idempotency-Key` header on `POST /appointments`. A retry with the same key returns the first appointment (200, `Idempotent-Replay: true`); the same key with a different body is `IDEMPOTENCY_KEY_REUSED`. The key is stored in the booking's own transaction, so ten simultaneous copies book exactly once. The booking form sends one key per distinct attempt |
| A rescheduling workflow fails halfway; the server crashes during a reschedule; the old appointment is cancelled but the replacement fails | **Covered** | Cancel and rebook are one transaction: any failure leaves the original untouched (tested, including that no history is written) |
| A waiting-list offer accepted by several patients; a patient accepts after the offer expired or another took the slot; a background job processes the same waiting-list entry twice | **Covered** | Offers lock the doctor row and re-run the booking rules at accept time; an expired offer is `OFFER_EXPIRED`; a lost race is `SLOT_TAKEN` and returns the patient to the queue |
| A bot repeatedly reserves and releases popular slots; patients refresh to gain an advantage; automated scripts get unfair advantage | **Covered** | There is no "hold": a slot is either booked or free, so there is nothing to hoard. A per-address rate limit (429 with `Retry-After`) slows scripts. First come, first served is the stated policy |
| A surge overwhelms search; a denial-of-service attack | **Partly** | Rate limiting and a small, indexed query set. Real DoS protection belongs to the host or a CDN |

## 2. Doctor availability changes

| Scenario | Status | How |
|---|---|---|
| Doctor becomes unavailable or changes hours after bookings exist; an unscheduled break or emergency block; a temporary administrative block; the change affects only one date | **Covered** | Weekly hours plus per-date overrides. A change that would strand bookings is refused with the list of affected patients (409) unless acknowledged; acknowledged ones stay booked and are flagged `needs_attention`. Nothing is silently cancelled |
| A holiday is announced after recurring appointments were generated; a public holiday midway through a series | **Covered** | A leave-day override flags the affected appointments the same way. A new series is checked occurrence by occurrence |
| A recurring series silently creates conflicts or an incomplete series | **Covered** | `POST /appointments/recurring` is all or none and names the occurrence that failed (`details.occurrence`). It never produces a partial series |
| The clinic changes its maximum daily capacity after bookings exist; a doctor requests a temporary cap | **Covered** | Lowering the cap never cancels anything (A-24); it only stops further bookings on over-cap days |
| A doctor is temporarily suspended from taking new patients; a doctor no longer works at the clinic; a clinic temporarily stops accepting bookings | **Added** | `accepting_bookings` on the doctor. New bookings and series are refused with `DOCTOR_NOT_ACCEPTING`, the day view says why, and existing appointments are left alone and can still be cancelled or marked |
| A doctor is deleted while historical appointments reference them; an administrator deletes the wrong doctor | **Covered** | Deleting a doctor with any appointment on record is `DOCTOR_HAS_APPOINTMENTS`; the UI asks twice |
| A doctor changes consultation duration | **Covered** | Refused while future bookings exist or windows would leave the grid (A-06) |
| A doctor changes availability while a patient is browsing slots; a cache shows a stale free slot | **Covered** | The server re-runs every rule when a booking arrives, and there is no server cache; the UI refetches after every change |
| Split shifts with a long midday closure; a booking that ends after closing | **Covered** | Several windows per day; an appointment must fit inside one window |
| Rotating or alternating-week shifts; seasonal hours; a nonstandard weekly cycle | **Partly** | The weekly pattern repeats every week. Alternating weeks can be set with date overrides; the pattern itself is not built |
| Regional holiday for one branch; a doctor works at two branches with travel time; moved to another branch | **Out of scope** | One clinic only (A-20). Branches would need a branch table on every rule |

## 3. Outcomes, penalties and mistakes

| Scenario | Status | How |
|---|---|---|
| Patient misses an appointment; cancels after the deadline; cancels at the last minute | **Covered** | The 2-hour late-cancel rule, no-show marking, and the deposit flag after two strikes in 30 days. A patient cancel at or after the start is a late cancel |
| An appointment is marked completed by mistake; a patient disputes a no-show penalty or a fee caused by an outage; attendance status must be corrected after the visit | **Added** | `POST /appointments/{id}/correct`: completed and no-show swap, a late cancellation can be waived. A note is required, the original outcome stays in the history, and because the deposit flag is derived from statuses it lifts immediately |
| A cancelled appointment is mistakenly restored | **Out of scope** | Restoring would silently take a slot someone else may already hold. The safe route is to book again, which re-checks every rule |
| A patient repeatedly postpones or changes their mind | **Partly** | Every move is in the audit history; no limit on the number of moves is enforced |
| A patient requests a different doctor after check-in | **Covered** | The clinic cancels and rebooks, or reschedules before check-in |
| The audit log is modified or lost; an audit event is written but the booking transaction fails; an audit report must separate the original time from later changes; a copy of the historical timeline | **Added** | `appointment_events`, written in the same transaction as each change (so it cannot describe a rolled-back change), append-only in the code. `GET /appointments/{id}/history` and `GET /patients/{id}/export` |

## 4. Arrival and the waiting room

| Scenario | Status | How |
|---|---|---|
| Patient arrives but reception cannot find the booking; two check-in systems register the same patient; a patient cancels while already checked in; checked in at the wrong place | **Added** | `POST /appointments/{id}/check-in`: opens on the day, repeating it changes nothing (tested under concurrency), and a checked-in patient cannot cancel or reschedule themselves (`ALREADY_CHECKED_IN`) while the clinic still can. The queue shows who has arrived. Finding a booking is by phone or name |
| A patient arrives late and delays everything; a consultation overruns; delay estimates | **Out of scope** | Needs live consultation timing and a delay model; the queue lists the day in time order |
| Walk-ins ahead of confirmed patients; priority treatment; staff change a priority; the schedule is fragmented; fairness quotas; a lottery | **Out of scope** | No walk-in or priority model. The waitlist is first come, first served |
| Patient leaves before being seen; cannot be located | **Partly** | The clinic can mark a no-show after the start; there is no waiting-room tracking |

## 5. Patients and identity

| Scenario | Status | How |
|---|---|---|
| A patient changes their phone number; their name changes; an incorrect date of birth | **Added** | `PATCH /patients/{id}`; appointments follow the patient; a phone already used by someone else is `PHONE_TAKEN` |
| Two profiles exist for one person; a receptionist picks the wrong similar patient; a parent with two similar children | **Added** | Registering or renaming into the same name and date of birth is refused with the matching patients listed (`POSSIBLE_DUPLICATE`); "Use that patient" or "Register anyway" are both one click, so twins are still possible. The picker shows phone numbers to tell similar names apart |
| Two different patients share a phone number (family) | **Covered, by design** | A phone is unique (A-15), so a family sharing one mobile registers one person per number. A guardian model would be needed to share one |
| A parent or relative books for someone; a guardian loses authority; consent of the person booked | **Out of scope** | Needs accounts and relationships. Without authentication (A-20) there is no "who is booking" to check |
| Several accounts with different phones to bypass limits | **Partly** | The duplicate guard catches the same name and birth date; deliberate evasion is not detectable without identity checks |
| Duplicate profiles merged or merged wrongly; a merge during a booking | **Out of scope** | No merge tool; a merge touches every table that references a patient |
| A patient requests deletion of their data; retention rules change | **Out of scope** | Deleting would break the audit and the cap counts. `GET /patients/{id}/export` covers the access request. Retention is a policy decision for the clinic |
| A patient requests access to their appointment history | **Added** | `GET /patients/{id}/export` and a download link on the patient page |

## 6. Emergencies and urgent symptoms

| Scenario | Status | How |
|---|---|---|
| A patient describes life-threatening symptoms while booking a routine appointment; an urgent symptom treated as ordinary | **Added** | A keyword check (`POST /triage`) shows a prominent "call 112" warning on the booking form while the reason is typed. The booking is never blocked, and appointments whose reason matches carry `urgent_symptoms` so the queue marks them. It is a safety net, not a clinical triage tool |
| Emergency patients arrive during a fully booked schedule; reserve capacity for urgent cases; urgent request with no qualified clinician; same-day request after the schedule is full | **Partly** | The waitlist and cancellation offers help with same-day demand. Reserved urgent capacity and staff overrides of the cap are not built (they would change the verified rules) |

## 7. Notifications and reminders

Every scenario about SMS, WhatsApp, e-mail, reminders, delivery receipts, wrong language, opt-out,
inbound replies, provider outages or rate limits, expired links, recipient mapping, emergency
contacts and background reminder jobs is **out of scope**. The system sends nothing. The reasons:
SMS and payments are optional in the assignment, and a notification subsystem is a product of its own
(an outbox, provider adapters, retries, templates per language, consent records). What exists
instead: an offer from the waitlist is visible on the patient page, a booking returns its details to
the screen that made it, and any appointment can be downloaded to the patient's own calendar
(`.ics`, with a stable `UID`, so re-importing updates rather than duplicates).

## 8. Time, dates and calendars

| Scenario | Status | How |
|---|---|---|
| Booked across time zones; the device shows another zone; the patient travels; a different zone in the confirmation | **Covered** | One clinic zone (IST). Instants are stored in UTC and every response carries both UTC and IST; a request without an offset is refused |
| Daylight-saving ambiguity; the clinic changes its time zone | **Covered / out of scope** | India has no daylight saving. Changing the clinic's zone is out of scope |
| An appointment crosses midnight; date-only validation allows an overlap | **Covered** | Overlap is checked on time ranges by a database constraint, not on dates. A window may run to 24:00 |
| A leap day or year end; a recurring booking over a leap year; a past date from a conversion bug; a wrong date picked in the calendar; just before midnight with a different server date | **Covered** | The India calendar date is computed from the instant; the 60-day window and the past check use it; the test clock lets a reviewer try the boundaries |
| A booking moved outside the horizon | **Covered** | Reschedule applies the same checks |
| Two calendar systems read an all-day closure differently; duplicate calendar events | **Covered** | Leave is modelled as no windows, not as an all-day event; exports use a stable `UID` per appointment |
| Two servers' clocks differ | **Covered** | One database clock plus one "now" per request; the test clock exists only when switched on |

## 9. Failures and operations

| Scenario | Status | How |
|---|---|---|
| The database is temporarily unavailable; the connection pool is exhausted; the application restarts mid-submit | **Covered** | 503 `SERVICE_UNAVAILABLE` with the standard error body, `/readyz`, a connection timeout, a retry after a deadlock. A restart mid-request leaves either a committed booking (the idempotency key makes the retry safe) or nothing |
| A database migration fails halfway | **Covered** | Migrations are transactional in PostgreSQL; upgrade, downgrade and upgrade is tested |
| A background cleanup job deletes active appointments; a task runs twice or never runs | **Covered** | There are no background jobs (ADR-04): offers and expiries are settled when the data is read or changed |
| A software update changes scheduling rules or identifiers; an old client sends an outdated format | **Covered** | Strict request schemas refuse unknown fields with a clear 422; ids are stable integers; the API is under `/api/v1` |
| A backup is restored from an older point; a backup is incomplete; recovery without notifications | **Out of scope** | Hosting concern (the database provider's point-in-time restore). The exclusion constraints would stop a conflicting rebooking after a restore |
| System offline during clinic hours; a regional internet outage; a power outage disables kiosks | **Out of scope** | Needs an offline mode and a paper fallback procedure. The app reports the outage clearly and recovers without data loss |
| Ransomware or a compromised account | **Out of scope** | Operational security; there are no accounts |

## 10. Security and privacy

Authentication is optional in the assignment, so it is **off by default** (it would lock out a
reviewer) and available by setting `STAFF_PASSWORD`. With it on: every data route needs a signed,
expiring token; guessing the password is limited to 10 tries a minute per client; and every audit row
names who made the change. With it off, the scenarios that depend on **who** is asking stay out of
reach: a staff member changing a booking without authorisation, a compromised account, exporting the
whole list, another branch's staff, a leaver's account, an unauthorised change to hours, and a patient
enumerating appointments by guessing ids. Even with it on there are no roles, so every signed-in
person can do everything, and there is one shared password rather than individual accounts.

Covered either way: strict input validation and no echo of hostile input
(`tests/api/test_hostile_input.py`), request size limits, a per-client rate limit that cannot be
dodged by forging `X-Forwarded-For`, parameterised SQL only, no personal data in the logs, manipulated
parameters (a time outside the hours, off the grid, in the past) refused by the same rules that offer
slots, and an audit table the database itself refuses to change or delete.

## 11. Rules and policy beyond the seven in the brief

Out of scope: appointment types and different durations or cleanup times, rooms, equipment, nurses
and shared resources, referrals, prerequisites and care pathways, lab results, eligibility, age
limits, insurance, authorisation codes, subsidies, payments, refunds, discounts, interpreters,
accessibility needs, infection precautions, preparation instructions, consent forms and chaperones,
teleconsultation, locum and trainee supervision, training time, protected review time, mandatory
breaks, travel time, staffing capacity, clinic mergers, new vendors and imports from other systems,
and event streams from external systems. Each is a feature on its own, and none of them is among the
seven rules the assignment grades. Several could be added later by extending the single shared
predicate `first_violation`, which is the one place a booking rule is decided.

## 12. Reporting and analytics

| Scenario | Status | How |
|---|---|---|
| A report counts reschedules as new bookings or as cancellations; a dashboard shows fewer cancellations than occurred; two departments define no-show differently; utilisation ignores breaks and blocked time; a report uses the wrong period because of time zones | **Added** | `GET /reports/summary` and a Report page. A moved appointment counts once, as "rescheduled"; the replacement is not a new booking; the no-show rate is no-shows out of completed plus no-shows; utilisation is the appointments that took a slot out of the slots the doctor's hours offered, so leave days and special hours count; periods are India dates. Every definition is written down (README section 8) |
| Forecasting, branch comparisons, last-minute cancellation effect, unfound-slot measurement, anonymised analytics, reporting during recovery | **Out of scope** | Analytics products; the report is a base for them |

## 13. Automation and intelligent scheduling

Every scenario about recommendation models, no-show prediction, voice or chat booking, automated
cancellation agents and optimisation is **out of scope**: nothing in this system decides for a
person. The one automatic action, a waitlist offer, follows a written rule, is never a booking until
the patient accepts it, and is checked against the authoritative rules at that moment.

## Summary of what changed in this pass

Added: idempotent booking retries; an audit history with a patient export; check-in; outcome
corrections; patient edits and a duplicate guard; a doctor switch for new bookings; waitlist decline
and pass-on (a lapsed or declined offer now goes to the next patient instead of stranding the slot);
an urgent-symptom warning; a summary report. See the migration `0003_operations.py`.
