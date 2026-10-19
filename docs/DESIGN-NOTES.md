# Design notes: every numbered assumption

README section 8 keeps the assumptions that interpret the brief. This file holds all of them,
including the design choices and the features beyond the brief. The numbers are stable: tests and
code comments refer to them.

| # | Assumption |
|---|---|
| A-01 | The slot grid is anchored at midnight India time: a valid start has zero seconds and minutes since midnight divisible by the slot length |
| A-02 | A date override replaces that date's weekly windows entirely (it is not merged); no windows at all means leave |
| A-03 | An appointment must fit inside one window |
| A-04 | A visit lasts one to four of the doctor's slots (`slots`, default 1). The server computes `end_at` from the doctor's slot length, the start must be on the grid, the whole visit must fit inside one availability window, and nothing of the doctor's or the patient's may overlap any part of it. A database CHECK ties `end_at - start_at` to `slots`. The daily cap counts visits, not slots, and the report counts the slots a visit took |
| A-05 | "Not more than 60 days ahead" means the India date of the start is at most today plus 60 days (calendar days, not 60 x 24 hours) |
| A-06 | The slot length cannot change while future booked appointments exist, or if existing windows would leave the new grid |
| A-07 | "Past" is a start at or before now; a slot starting exactly now cannot be booked |
| A-08 | A patient cancel at or after the start is a Late-Cancel (it is less than 2 hours ahead, as the problem statement says); a clinic cancel never is. Only a reschedule is refused once the appointment has started, because it would book a new slot while leaving a started one |
| A-09 | A cancellation by the clinic is always a normal cancel and never counts against the patient |
| A-10 | A reschedule is a cancel of the old slot (following the 2-hour rule) plus a booking. When the clinic moves it that is never a late cancellation (as with A-09). When the patient moves it inside 2 hours it is one, which counts toward the deposit flag, so the server refuses until the move is confirmed with `acknowledge_late`; the question is asked last, after the new slot has been checked, so nobody is asked to accept a penalty for a move that could not happen. The old slot is offered to the waitlist either way |
| A-11 | Deposit eligibility for a reschedule uses the patient's status before that reschedule's own cancellation |
| A-12 | An availability change that would leave booked appointments outside the new hours is refused with the list (409) unless `acknowledge_conflicts` is true; acknowledged appointments stay booked and are listed as needing attention. Nothing is silently cancelled |
| A-13 | A late cancel counts from the time it was made; a no-show counts from the appointment's start |
| A-14 | `deposit_confirmed` is a staff acknowledgement only; no amount or payment is stored |
| A-15 | Phones are Indian mobile numbers, ASCII digits only, stored as `+91XXXXXXXXXX`. A phone number is unique, as the problem statement defines the patient: a `UNIQUE` constraint (migration 0006) is the final guard, and registering or editing onto a number in use is refused with `PHONE_TAKEN`. The error carries only the owner's id, not their name or birth date, so the API does not disclose who a number belongs to; search by phone finds them |
| A-16 | The daily cap counts booked, completed and no-show appointments; cancelled and late-cancelled ones do not |
| A-17 | The API returns UTC and India time, accepts any explicit offset and refuses a time without one |
| A-18 | Completed and no-show can only be marked at or after the start |
| A-19 | Completed, cancelled, late-cancelled and no-show are final, with one exception (A-48): a wrongly recorded outcome can be corrected |
| A-20 | A single clinic. Authentication is optional and off by default (A-53, A-62) |
| A-21 | A "day" for the cap is the India calendar date of the start |
| A-22 | The trailing 30 days are the closed interval from now minus 30 x 24 hours to now |
| A-23 | The test clock changes "now" for the domain and for `cancelled_at` and `status_changed_at`, but not the audit columns `created_at` and `updated_at` |
| A-24 | Lowering a doctor's cap never cancels existing appointments; it only blocks new ones |
| A-25 | The assignment window is 2026-10-17 to 2026-10-23 (the PDFs were saved on 2026-10-17; the date of the email is not known) |
| A-26 | Availability windows must start and end on the doctor's slot grid |
| A-27 | `needs_attention` means: booked, starting at or after now, and outside the doctor's effective windows. It is stored as `appointments.outside_hours`, refreshed in the same transaction as any change to hours, and a test checks it against the rule (A-67) |
| A-28 | Rescheduling to the same doctor and the same start is refused (`RESCHEDULE_NO_CHANGE`) so a no-op cannot create a strike |
| A-29 | A reschedule inherits `deposit_confirmed` from the old appointment unless restated; a currently flagged patient still needs it to be true |
| A-30 | Instants, including `X-Test-Clock`, are ISO 8601 text with an explicit offset between 2000 and 2099; an empty header, a malformed one, or any header while the clock is disabled is an error, never ignored |
| A-31 | A start with non-zero seconds or microseconds is off the grid |
| A-32 | Text is trimmed, length-bounded, valid Unicode and free of control characters (a reason or note may contain tab and line breaks); unknown JSON fields are refused |
| A-33 | Ids are integers from 1 to 2,147,483,647; booleans must be literal `true` or `false`; `limit` is at most 100 and `offset` at most 100,000 |
| A-34 | The queue shows one India day (default today by the clock) and hides cancelled appointments unless `include_cancelled=true` |
| A-35 | Seed data is built around an anchor date; the UI has a "Seed day" clock preset; the hosted database is re-seeded on the morning of the review |
| A-36 | Replacing the weekly windows follows the same conflict protocol as an override |
| A-37 | Only appointments a change would *newly* orphan block it; one already outside the hours (acknowledged earlier) does not hold unrelated edits hostage |
| A-38 | In the day schedule a slot that holds an appointment shows as booked even when it is in the past; past, capped, closed and busy apply to slots with no appointment |
| A-39 | Removing a date override that does not exist succeeds and does nothing |
| A-40 | A new patient's date of birth must be between 1900-01-01 and today by the effective clock |
| A-41 | The waitlist is per doctor and India date, first come first served. A cancellation or reschedule offers the freed slot to the first waiting patient who could actually book it (same check as a booking); the offer lasts 30 minutes or until the slot starts, is not a reservation, and accepting it is an ordinary booking (the deposit rule applies, and a lost race returns the patient to the queue) |
| A-42 | A recurring series keeps the same India time of day, books all occurrences in one transaction, and checks each exactly as a single booking; if one fails none is booked |
| A-43 | A doctor can be deleted only while no appointment of any status references them; their hours and leave go with them |
| A-44 | `deposit_required` on a patient is derived from the same rule as the deposit status, never stored; it is null in search results |
| A-45 | An `Idempotency-Key` is stored with its booking in the same transaction. The same key and the same request returns the original appointment even if it was cancelled since; the same key with another request is refused. A key is forgotten 24 hours after it was stored (by the database's clock, so a test clock cannot expire it) |
| A-46 | Check-in opens on the India date of the appointment and is recorded once. A checked-in patient cannot cancel or reschedule themselves; the clinic can still cancel, and complete or no-show work as before |
| A-47 | Registering, or editing, a patient into the same name (ignoring case and extra spaces) and date of birth as another patient is refused with the matches listed, unless the caller confirms with `allow_duplicate`. Different phones do not make two people different |
| A-48 | Corrections: completed becomes no-show or the other way round, and a late cancellation can be waived to a normal one. A note is required and the history keeps the original. A cancelled appointment cannot be restored (book again instead). The deposit flag, being derived, follows the correction |
| A-49 | A doctor with `accepting_bookings` off refuses new bookings and series and offers no slots, whatever their hours. Existing appointments, cancellations, marking and the waitlist are unaffected |
| A-50 | An offer that lapses, is declined or is abandoned by leaving is passed to the next patient who could take the slot. A patient who declines keeps their place for other slots but is never offered the same slot again. A lapsed offer is settled when someone next reads or changes that doctor's waitlist (there are no background jobs) |
| A-51 | Report definitions: a rescheduled appointment (cancelled only because it was moved) is counted as rescheduled, not as a cancellation, and its replacement is not a new booking; the no-show rate is no-shows out of completed plus no-shows; utilisation is appointments that took a slot (booked, completed, no-show) out of the slots the hours offered; periods are India dates |
| A-52 | The urgent-symptom check is a keyword match on the reason. It warns and marks the appointment; it never refuses a booking and is not a clinical tool |
| A-53 | Sign-in is required unless `ALLOW_OPEN_ACCESS=true` is set (the assignment makes it optional, so a review demo can stay open). With `STAFF_PASSWORD` there is one shared password and a name, producing a signed token that expires (HMAC-SHA256, so changing the password signs everyone out). With `AUTH_SECRET` there are individual accounts with two roles (A-62). The login route is limited to 10 attempts a minute per client, and five wrong passwords lock one account for 15 minutes |
| A-54 | Every audit row records its actor: the signed-in name, `anonymous` when login is off, `system` for work the server does itself. The audit table is append-only in the database (a trigger refuses UPDATE and DELETE), not just in the code |
| A-55 | Waitlist reads take no lock and write nothing: an offer whose time has run out is simply not shown. A server-side sweep (every 30 seconds, and safe to run on several instances) passes each lapsed slot to the next patient. Changing a doctor's waitlist does the same immediately |
| A-56 | The rate limit counts the address `TRUSTED_PROXY_HOPS` places from the right of `X-Forwarded-For`; with none configured it counts the socket address. Reading the left-most entry would let a caller change it on every request |
| A-57 | Rescheduling keeps the visit's length: in slots with the same doctor, in minutes with another, and it is refused when the minutes do not divide into that doctor's slots. A freed multi-slot visit is offered to the waitlist as a visit of that length, and a patient is only offered it if the whole of it suits them |
| A-58 | After a change the UI refreshes only the lists that change can alter (a table in `api/hooks.ts` names them), not everything on screen; changing the test clock is the one change that refreshes all |
| A-59 | `GET /alternatives` only reads. It probes up to 14 days for the same doctor and 3 days for other accepting doctors with the same `free_slots` used for booking, returns each (doctor, day)'s first start, and keeps half the list for the patient's own doctor so a busy fortnight cannot crowd out a free colleague. Booking an alternative goes through the normal booking path |
| A-60 | The rule proof (`POST /diagnostics/proof`) runs on a fixed clock with its own doctors and patients in a transaction that is rolled back (services' transactions become savepoints), so it neither reads nor keeps clinic data. It does consume database sequence numbers, so ids in the real tables may skip. Concurrency is not part of it: that is proven by the race tests, which need several real connections |
| A-61 | Recovery counts a cancellation (not a move) as *refilled* when another active appointment of the same doctor overlaps its time and was booked, by the effective clock, at or after the cancellation. It is credited to the waitlist when that booking's `BOOKED` event says `via: WAITLIST` |
| A-62 | Roles apply only when sign-in is on. An **administrator** sets the clinic up (doctors, hours, erasing a patient, the export, accounts, diagnostics); a **receptionist** does the day-to-day work (patients, bookings, the queue, the waitlist, reports, messages). With no sign-in at all everything is open, as the assignment allows. The role and the active flag are read from the database on every request, not trusted from the token |
| A-63 | The last active administrator account cannot be switched off or demoted, so the clinic cannot lock itself out. The shared `STAFF_PASSWORD` is not an account and does not count |
| A-64 | Erasing a patient is refused while they have an upcoming booking or a waitlist place (erasing would silently cancel care). The name, phone (replaced by a reserved-looking number that keeps `phone` unique), date of birth, consent and appointment reasons go; their messages keep only ids. Audit events keep ids and times but no personal data, except a free-text correction note a staff member typed, which the append-only guard stops us rewriting |
| A-65 | Consent is recorded, not required: registration works without it, because a clinic may rely on another lawful basis and the assignment does not ask for it. Without recorded consent the server never messages the patient (the message is SKIPPED and says to phone) |
| A-66 | Messages are written in the same transaction as the change they announce, for a booking, a clinic cancellation, a move and a waitlist offer. A patient's own cancellation is not messaged back. There are no reminders: nothing runs on a per-appointment timer |
| A-67 | `needs_attention` is stored as `appointments.outside_hours` and refreshed in the same transaction as any change to a doctor's hours, the only thing that can change it. "Future" is applied at read time, so it does not depend on a clock. A test compares the stored flag with the rule after random sequences of hour changes |
| A-68 | The audit hash chain is per appointment (each event hashes the previous event of the same appointment), which needs no global lock. It detects an edited or removed event in the middle of a history; it cannot detect events removed from the very end, and someone with full database rights could recompute the chain, so it is tamper-evident, not tamper-proof |
