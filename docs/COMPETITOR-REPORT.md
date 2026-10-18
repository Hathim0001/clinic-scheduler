# Competitor intelligence and gap analysis (second pass)

Researched and written on 2026-10-18. This extends [COMPETITIVE-ANALYSIS.md](COMPETITIVE-ANALYSIS.md) and
corrects one thing in it (section 6). It follows the brief's deliverables in order, but it is **not**
the exhaustive study the brief describes: it is about 15 searches and 3 page fetches, no source code
of any competitor was read, and several review sites could not be opened. Section 14 says exactly what
that means for each conclusion.

Labels used throughout: **Verified** (read in the source), **Reported** (a search snippet or a vendor
page, not opened in full), **Not found** (searched, nothing seen; this does not mean it does not
exist), **Unknown**.

## 1. Executive summary

- **The application** books appointments for a two-doctor clinic and enforces seven business rules in
  the backend, including under concurrent requests. It also has a waitlist, recurring bookings,
  calendar export, optional staff accounts with roles, consent and erasure tools, a message outbox,
  a tamper-evident audit trail and a "prove the rules" page.
- **Where it stands against the brief:** every Core requirement and every Stretch item is built and
  tested (1,264 backend and 156 frontend tests, fuzzed, load-tested). The remaining risks are not
  features; they are the repository still being private, the history needing a final tidy of long
  commit subjects, and the author being able to explain the code on the call.
- **Strongest competitors for a clinic like this:** Jane App (feature depth, Capterra 4.8 from 514
  reviews, Reported), Practo Ray (Indian market, Capterra about 4.0 from 8 reviews, Reported),
  Zocdoc (patient acquisition, not clinic operations) and, for scheduling mechanics, Cal.com and
  Acuity.
- **Most important gaps vs competitors** (none required by the brief): no patient self-booking, no
  reminders, no real message gateway, no payments, no multi-location, no EHR link.
- **Exploitable competitor weaknesses (thin evidence):** double-booking defects and gaps are a
  recurring class (Cal.com's own changelog fixes a concurrent-confirmation double booking; one
  EZnet reviewer says recurring bookings do not warn about overlaps; a Jane reviewer asks for a
  same-day duplicate alert). Concurrency-proof booking is this project's one clearly demonstrable
  advantage.
- **A correction:** my earlier note said reminders were the first gap to close. A 2025 meta-analysis
  found SMS reminders did **not** reach statistical significance (RR 1.14, 95% CI 0.99 to 1.31) while
  telephone reminders did (RR 1.11, 1.04 to 1.19). A reception **call list for tomorrow** is better
  supported by the evidence than an SMS gateway, and needs no gateway.
- **Biggest risks to the submission:** private repository (−20), explaining AI-written code live,
  and the privacy features outrunning their legal footing (section 10).
- **Highest-value next steps:** the short list in section 11, led by the same-day duplicate alert,
  the reception call list and three privacy fixes that are mostly documentation.

## 2. Application baseline audit

What was inspected: the repository at `main`, the migrations, the test suites, CI results and the
hosted API (read-only requests). Everything below was checked in code or by running it unless marked.

| Area | State | Evidence |
|---|---|---|
| The seven rules, in the backend | **Verified** implemented | `domain/slots.py`, `cancellation.py`, `penalties.py`, `booking_window.py`; 1,264 passing tests |
| Concurrency | **Verified** | `EXCLUDE` constraints in `0001_initial.sql`, doctor-row lock, 10-connection race tests, 100-user load run (0 server errors, 0 overlaps) |
| Core API and UI flows | **Verified** | 57 operations in the live OpenAPI; 25 browser flow checks, 32 axe scans |
| Stretch: waitlist, recurring, ICS | **Verified** | tests and e2e |
| Extras beyond the brief | **Verified** | accounts and roles, consent and erasure, outbox, stored `outside_hours`, audit chain |
| Hosted | **Verified** this session | API, UI, seeded data, test clock, 400 and 422 on bad input |
| Reminders, SMS sending, payments, patient portal | **Not implemented** | by design |
| Screen-reader audit by a person | **Not done** | axe-core and keyboard checks only |
| Public repository | **Not yet** | private as of this report |

Measured today: `GET /alternatives` took 0.9 to 1.1 s from this machine against the hosted API
(three calls), versus 0.3 s for one day's slots. That is the cost of probing up to 14 days one query
at a time (`services/alternatives_service.py`).

### Findings in my own code (confirmed unless marked)

| ID | Where | Finding | Type | Severity |
|---|---|---|---|---|
| S-01 | `services/patient_service.py` `erase`, `core` privacy | Erasure also deletes the consent record. The DPDP Rules summary below says consent records should be kept at least seven years (Reported) | Design weakness | Medium, needs legal review |
| S-02 | patients table | Patients can be minors (the seed has birth dates in 2012) but nothing records a guardian or parental consent; DPDP requires verifiable parental consent for children's data (Reported) | Missing feature | Medium |
| S-03 | docs | No breach-response procedure; DPDP Rules reportedly require a first notice without delay and a detailed report within 72 hours (Reported) | Missing documentation | Medium, low effort |
| S-04 | `services/notification_service.py` `_deliver` | The HTTP call to the gateway runs inside the database transaction (row lock held up to the 5 s timeout) | Design weakness | Low (one connection at a time) |
| S-05 | `api/ratelimit.py` | Login throttling is per client address, not per account; no lockout, no second factor | Design weakness | Low to medium |
| S-06 | `api/routers/proof.py` | When sign-in is off anyone can run the proof (holds a connection for seconds) | Design weakness | Low; documented |
| S-07 | `/metrics` | Unauthenticated; holds counts only | Observation | Low |
| S-08 | `domain` erased phone | `+91` plus `6000000000 + id` is not guaranteed unused by a real number; a collision would make erasure fail with `PHONE_TAKEN` | Theoretical | Very low |
| S-09 | audit notes | A staff-typed correction note can hold personal data and the append-only guard stops us scrubbing it | Known limitation | Low; documented (A-64) |
| S-10 | UI | No warning when a patient already has another appointment the same day (not an overlap, so no rule fires) | Missing feature | Low |

**Update, later the same day:** S-01 to S-04, S-05 (per-account lockout), S-06 (cooldown), S-07 (optional
token), S-08 (reserved erased-phone shape) and S-10 were fixed; S-09 stays a documented limitation.

No defect was found that breaks a business rule. No crash on malformed input was found in the fuzz runs.

## 3. Competitive landscape

| Category | Product | Why relevant | Evidence |
|---|---|---|---|
| Direct, commercial | **Jane App** | Clinic scheduling, online booking, reminders, waitlist, deposits | Vendor pages, GetApp, Capterra (Reported) |
| Direct, commercial, India | **Practo Ray** | Indian clinic management with scheduling, EMR, queue | Capterra, FitGap, Zoho guide (Reported) |
| Direct, marketplace | **Zocdoc** | Patient booking and intake feeding practice calendars | Zocdoc AI/LLM info page (Reported) |
| Indirect, general scheduling | **Acuity Scheduling**, **Cal.com** | Mature slot, buffer, notice and waitlist mechanics | Vendor docs and blog (Reported) |
| Indirect, other | EZnet Scheduler, Clinika OS, Pabau | Appear in double-booking review searches | Capterra and SoftwareFinder (Reported) |
| Open source | **Cal.com**, **Easy!Appointments** | Self-hosted scheduling; source is public | Source not read; no issue found for Easy!Appointments |
| Academic | Samorani et al.; the 2025 reminder meta-analysis; a systematic review of no-show interventions | What actually reduces no-shows, and the equity risk of overbooking | Fetched or snippet, see section 5 |
| Manual | Paper diary, spreadsheets | The brief's starting point | The brief itself |

Not covered: OpenEMR, Bahmni, Frappe Healthcare, Google Play and App Store reviews, Reddit threads,
Trustpilot. The search tool does not return those pages reliably and I did not fetch them.

## 4. Competitor dossiers (condensed)

**Jane App.** Online booking with control over which treatments, times and staff are bookable;
SMS or email confirmations and reminders; deposits, or a card kept on file for late-cancellation
policy; automated waitlist reminders; multi-practitioner and multi-location (Reported, vendor and
GetApp). Technical internals: Unknown. Weaknesses reported on Capterra (a sample, not a count):
learning curve, several ways to do one task (billing), heavy setup for some features, unreliable
telehealth audio and video, a request for an alert when a client is already booked that day, and
solo practitioners paying staff-sized pricing.

**Practo Ray.** Appointment management, EMR, billing, SMS alerts, queue and waiting-list
management, multi-doctor and multi-branch (Reported). Only 8 Capterra reviews; the lowest sub-score is
customer service (3.8 of 5); one reviewer found it expensive; WhatsApp support is unconfirmed.
Internals: Unknown.

**Zocdoc.** Calendar-integrated booking from Zocdoc, Google and practice sites; claims 175+ EHR
integrations; reminders at 7 days, 1 day and about 3 hours; intake-task prompts at 48 h, 24 h and 90
min; no clear waitlist feature found (Reported, vendor-marketing and an AI-generated benchmark site).
Primarily patient acquisition.

**Cal.com.** Event types with buffers, minimum notice, booking limits (Reported). Its v6.4 release
notes say "two people confirming the same pending booking at the same time could result in a
double-booking" and that concurrent confirmations are now handled safely (**Verified** by fetching the
page; the page shows two different dates, 15 April 2026 and 17 October 2026, so the date is
unreliable). This is evidence that the concurrency problem this project solves is real for mature
products.

**Easy!Appointments.** Open-source PHP scheduler. A targeted search found no issue about concurrent
double booking; that is **Not found**, not proof of absence.

**EZnet Scheduler (review, single source).** A nurse says it does not warn about double bookings
when recurring reservations are created. One review, not corroborated.

## 5. Academic and technical evidence

| Source | What it shows | Status | Applicability |
|---|---|---|---|
| Meta-analysis of appointment reminders, *J Hosp Manag Health Policy*, 2025 | SMS: RR 1.14 (95% CI 0.99 to 1.31, 4 studies, 4,636 people, I² 91%, P = 0.07, **not significant**). Telephone: RR 1.11 (1.04 to 1.19, 5 studies, 3,369 people, I² 63%, P = 0.002). The authors say the subgroups did not directly compare SMS with phone, evidence is heterogeneous, English-only, and there is no cost-effectiveness analysis | **Verified** (page fetched) | Argues for a phone call list before an SMS gateway |
| Scoping review of reminder systems (Portuguese repository) | Reported no-show reductions of up to 40 to 50%; SMS most common; phone calls with confirmation worked better | Snippet only | Supports the same direction |
| Systematic review of no-show interventions (University of Glasgow repository) | High-certainty evidence that predictive-model-based text reminders reduce no-shows; the effect of predictive overbooking was uncertain; meta-analysis not possible | Snippet only | Needs patient history data and a model; out of scope |
| Samorani et al., *Machine Learning and Racial Bias in Medical Appointment Scheduling* (SSRN 2019; the search result gives *Manufacturing & Service Operations Management* 2022, DOI 10.1287/msom.2021.0999, which the fetched page does not confirm) | Combining ML no-show prediction with overbooking creates racial disparity in waiting time; adding a disparity term removes it without significant extra cost | **Verified** (page fetched), venue Reported | A reason **not** to add predictive overbooking: this project overbooks nobody |

Nothing here supports adding machine learning to a two-doctor clinic. Vendor figures of 30 to 50
percent fewer no-shows are widely repeated and trace to vendor blogs, not to a source opened here.

## 6. User feedback intelligence

Small samples, all from search results rather than the sites themselves. They show themes, not rates.

| Theme | Evidence | Pattern? | Relevance |
|---|---|---|---|
| Learning curve and too many ways to do one thing | Jane, Capterra reviews | Several reviewers | This project has one path per task; untested with real users |
| A duplicate-booking warning is wanted | Jane reviewer (same-day); EZnet reviewer (recurring overlaps) | Two different products, one review each | Cheap to add (S-10) |
| Setup effort | Jane reviewer | Isolated | Neutral |
| Telehealth reliability | Jane reviewers | Recurring | Out of scope |
| Price and tier fit | Jane (solo user), Ray (expensive) | Isolated each | Self-hosted free is a real advantage but also a support burden |
| Support quality | Ray sub-score 3.8 | One number from 8 reviews | Weak evidence |
| Reminders reduce no-shows | Jane users say so (GetApp); meta-analysis is mixed for SMS | Vendor-adjacent | Use the call list |

Not found: Reddit, Google Play and App Store feedback for any of these products. The underlying
problem ("double bookings, no-shows, changing availability") is described by vendor blogs; no
independent user thread was opened.

## 7. Master comparison matrix

Labels as defined at the top. "This" is this project.

| Capability | This | Jane | Practo Ray | Zocdoc | Cal.com |
|---|---|---|---|---|---|
| Concurrency-proof booking | **Verified** (constraints, race tests) | Unknown | Unknown | Unknown | Partial (fix noted in v6.4) |
| Per-doctor weekly hours and date overrides | **Verified** | Reported | Reported | Reported | Reported |
| Cancellation window and repeat-offender flag | **Verified** (derived, 2 in 30 days) | Partial (fees, deposits) | Not found | Not found | Not found |
| Waitlist with auto-offer | **Verified** | Reported | Reported (waiting list/queue) | Not found | Not found |
| Patient self-booking | Not applicable (phone clinic) | Reported | Reported | Reported | Reported |
| Reminders | Not implemented | Reported | Reported | Reported | Not found |
| Payments and deposits | Acknowledgement only | Reported | Reported (billing) | Not found | Not found |
| Multi-location | Not implemented | Reported | Reported | Not found | Not found |
| EHR/EMR | No | Reported | Reported (EMR) | Reported (175+) | No |
| Audit trail tamper-evident | **Verified** | Unknown | Unknown | Unknown | Unknown |
| Right to erasure tool | **Verified** | Unknown | Unknown | Unknown | Unknown |
| Open source / self-host | **Verified** (own repo) | No | No | No | Reported |
| Independently usability-tested | **No** | Reported (many reviews) | Reported (8 reviews) | Unknown | Unknown |

No numeric scores are given: there is no defensible rubric for them from this evidence.

## 8. Gap analysis

- **They have, we lack:** self-booking, reminders, a sending gateway, payments, multi-location, EHR,
  discovery, mobile apps, report export. None is required by the brief.
- **We have, evidence for them lacking is thin:** a booking proof page that rolls back, hash-chained
  audit, erasure tooling, a quantified refill metric for the waitlist. "Not found" in a competitor's
  public pages is not evidence that they lack it.
- **Both lack (as far as seen):** independent evidence of screen-reader accessibility.
- **We do poorly or risk doing poorly:** section 2 table, plus no real-user testing.
- **Competitors do poorly (reported):** discoverability and customisation load (Jane), support (Ray),
  duplicate warnings (EZnet, Jane request).
- **Rejected as out of scope:** patient portal, payments, EHR, multi-location, discovery, ML
  no-show prediction and predictive overbooking (equity risk, section 5), LLM features.

## 9. Competitor weaknesses I can address

1. **Double-booking and overlap defects.** Evidence: Cal.com v6.4 fix; the EZnet recurring review.
   Already addressed with database constraints, race tests, the all-or-none recurring series that
   names the failing occurrence, and the proof page. To show it: run `scripts/load.py` and the proof
   page in front of a reviewer. Defensible but easy to copy once known; the proof is the moat.
2. **Too many paths for one task (Jane).** One review theme. A single booking form with only valid
   times is how this project avoids it. Needs a real-user test to claim it.
3. **Same-day duplicate alert (Jane request).** Not built yet; see R-1.

Do not claim more: no competitor weakness here was confirmed by more than a handful of reviews.

## 10. Security, privacy and compliance

Authoritative text was not read; the DPDP Rules 2025 points below come from law-firm and consultancy
summaries (Reported) and need checking against the Gazette text.

- Notified 14 November 2025; consent-manager rules start about a year later and core duties about
  May 2027, so most obligations are not yet in force today.
- Reported: deletion when purpose lapses or consent is withdrawn; consent records kept at least
  seven years; initial breach notice without delay and a detailed report within 72 hours;
  verifiable parental consent for children; notice before erasure.
- **For this project:** S-01 (consent record vs erasure), S-02 (minors), S-03 (breach procedure) are
  the three to resolve. All are in-scope-supporting, none is required by the assignment, and the
  README already says it is engineering support, not legal advice.
- Headers, logging without personal data, rate limiting, hashed passwords (scrypt) and the
  dependency audit (`npm audit`: 0 vulnerabilities; Python outdated list: fastapi, graphql-core and
  jsonschema_rs have newer patch or minor versions, no advisory checked because `pip-audit` is not
  installed here) are in place.

## 11. Prioritised backlog

Priority = impact times evidence confidence, divided by effort, filtered by scope. Effort in rough
engineer-hours, assuming one person who knows the code.

| ID | Item | Scope | Priority | Effort | Evidence | Why |
|---|---|---|---|---|---|---|
| R-0 | Make the repository public; fix long commit subjects; push | In scope (deliverable) | **P0** | 1 h | The brief | −20 and a git-hygiene deduction otherwise |
| R-1 | Same-day duplicate alert when booking **(done)** | In-scope supporting | P1 | 2 to 3 h | Jane and EZnet reviews (weak) | Cheap, visible, rule-adjacent |
| R-2 | Reception "call list" for tomorrow's appointments, marked called/not **(done: the Calls page)** | Conditional (reminders are not in the brief) | P2 | 3 to 5 h | 2025 meta-analysis, phone RR 1.11 significant | Better supported than SMS, no gateway |
| R-3 | Docs: breach procedure, consent-record retention note, minors note **(done, and the consent and guardian code)** | In-scope supporting | P2 | 1 to 2 h | DPDP summaries (Reported) | Closes S-01 to S-03 on paper |
| R-4 | Per-account login throttle **(done)** | In-scope supporting | P2 | 2 h | Standard practice | S-05 |
| R-5 | Move the gateway call out of the DB transaction **(done)** | Technical | P3 | 2 to 3 h | Code reading | S-04 |
| R-6 | `alternatives` in one transaction per doctor instead of up to 17 **(done)** | Technical | P3 | 3 h | Measured 0.9 to 1.1 s | Latency |
| R-7 | CSV export of the report **(done)** | Low cost | P3 | 1 h | Gap table | Nice to have |
| R-8 | Real-user test with a receptionist; a screen-reader user | Validation | **P1 for confidence** | 2 to 4 h | Section 14 | Only way to know |
| R-9 | SMS gateway account and reminders | Conditional | Defer | days | Evidence mixed for SMS | Cost and uncertain benefit |
| R-10 | ML no-show prediction, overbooking | Out of scope | **Reject** | n/a | Samorani et al. | Equity risk, no data |
| R-11 | Patient portal, payments, EHR, multi-location | Out of scope | Reject | n/a | Gap table | Different product |

### Specifications for the top items

**R-1 same-day duplicate alert.** Backend: `GET /patients/{id}/appointments?date=` already exists via
filters; add `same_day` to the slot-selection response or have the UI query the patient's
appointments for the chosen date. UI: in `components/booking`, show a non-blocking warning ("Meera
already has an appointment on this day at 10:00 with Dr. Rao") when a booked appointment shares the
India date. No rule changes; booking still allowed. Tests: a Vitest test with a fake API that returns
one appointment that day; an e2e case. Acceptance: the warning appears, booking still succeeds, no
warning for a cancelled appointment.

**R-2 call list.** `GET /queue?date=tomorrow` already lists appointments. Add a boolean
`confirmation_called_at` on appointments (migration), a `POST /appointments/{id}/confirmed-by-phone`,
and a page that lists tomorrow's bookings with a "Called" button. Security: reception role allowed.
Tests: transition tests, a role test, a UI test. Acceptance: marking is recorded in the audit trail
and cannot be done for a cancelled appointment. Validation plan: compare no-show counts in the
report before and after only if a real clinic uses it; otherwise state it is untested.

## 12. Validation plan

- **R-1/R-2:** unit and e2e tests as above; success is behavioural (warning shown, call recorded).
  No performance claim.
- **R-8:** five task scenarios (book, cancel late, move inside 2 hours, find a flagged patient,
  handle a conflict) with one receptionist; measure completion and the point of confusion. Same with
  one screen-reader user on the booking and queue pages.
- **Regression:** the existing suites, the fuzz run and `scripts/load.py` after each change.
- **Do not promise** a no-show reduction. It cannot be measured without real use.

## 13. Roadmap

1. **Fix immediately:** R-0.
2. **Implement next:** R-1, R-3.
3. **Experiment and validate:** R-8, then R-2 if a clinic wants it.
4. **Defer:** R-4 to R-7, R-9.
5. **Reject:** R-10, R-11, any LLM feature.

## 14. Confidence and limitations

- **Thoroughly verified:** the application baseline (code, tests, live API); the reminder
  meta-analysis numbers; the Cal.com v6.4 sentence; the Samorani finding.
- **Partially investigated:** every competitor's features and reviews, from search snippets and
  vendor pages, never from the products themselves or full review sets.
- **Could not access or did not attempt:** competitor source code, GitHub issue trackers, Reddit,
  Google Play, App Store, Trustpilot, G2, PubMed, Semantic Scholar; the DPDP Rules Gazette text.
- **Limited evidence:** the duplicate-warning theme (two single reviews); Ray's support rating (8
  reviews); all no-show percentages from vendors.
- **Not equivalent:** Zocdoc is a marketplace; Cal.com is a general scheduler; Jane and Ray are full
  practice-management suites. This project is a two-doctor scheduling core.
- **Needs your confirmation:** whether any reminder feature is in scope for you; whether minors'
  data matters for the demo; whether to spend remaining time on R-1 or only on rehearsal.
- **Would raise confidence most:** a receptionist and a screen-reader user trying it; reading the
  DPDP Rules text; a month of real use.

## 15. Research log

Searches this pass: Easy!Appointments and Cal.com double-booking issues; double-booking complaints
on Capterra; reminder and no-show systematic reviews; Jane App and Practo Ray Capterra reviews;
overbooking and equity research; DPDP Rules 2025. Fetched: the 2025 reminder meta-analysis, the
Cal.com v6.4 post, the Samorani publication page. Earlier pass: Acuity waitlist, Novoflow,
DoctorConnect, MedicalMet, Zocdoc, Jane, Ray, Cal.com booking limits, no-show policy blogs.
Diminishing returns were reached on the competitor feature lists; they were not reached on user
feedback or on open-source internals.

## 16. Source register

Access date for all: 2026-10-18. "Fetched" means the page was opened; the rest are search results.

| Topic | Source | URL | Status |
|---|---|---|---|
| Reminder meta-analysis | A systematic review and meta-analysis of appointment reminders for enhancing hospital attendance, J Hosp Manag Health Policy, 2025 | https://jhmhp.amegroups.org/article/view/10215/html | Fetched |
| Reminder scoping review | Scoping review of reminder systems, Instituto Politécnico de Lisboa repository | https://repositorio.ipl.pt/entities/publication/a31ce80e-4b6f-4b7e-91b2-43e785f404fa | Snippet |
| No-show interventions review | University of Glasgow repository | https://eprints.gla.ac.uk/287844/1/287844.pdf | Snippet |
| Overbooking equity | Samorani et al., Machine Learning and Racial Bias in Medical Appointment Scheduling, Santa Clara University | https://www.scu.edu/business/isa/research/selected-publications/machine-learning-and-racial-bias-in-medical-appointment-scheduling.html | Fetched |
| Overbooking mechanism | PMC commentary | https://pmc.ncbi.nlm.nih.gov/articles/PMC7067080 | Snippet |
| Cal.com concurrency fix | Cal.com v6.4 release notes | https://cal.com/blog/calcom-v6-4 | Fetched |
| Cal.com limits | Minimum notice, buffers, booking limits | https://cal.com/blog/mastering-event-level-time-limits-what-lies-beyond-buffer-times | Snippet |
| Jane reviews | Capterra, Jane reviews | https://www.capterra.com/p/178984/Jane-App/reviews/ | Snippet |
| Jane features | Jane online booking; Jane guide; GetApp | https://jane.app/features/online-booking , https://jane.app/guide/category/schedule , https://www.getapp.com/healthcare-pharmaceuticals-software/a/jane-app/reviews/ | Snippet |
| Practo Ray | Capterra reviews and pricing; FitGap | https://www.capterra.com/p/167778/Ray/reviews/ , https://us.fitgap.com/products/ray-by-practo | Snippet |
| Zocdoc | Zocdoc structured information page | https://www.zocdoc.com/about/ai-llm-info/ | Snippet (vendor) |
| EZnet review | Capterra, EZnet Scheduler reviews | https://www.capterra.com/p/130929/EZnet-Scheduler/reviews/?page=3 | Snippet |
| Acuity waitlist | Acuity Scheduling | https://acuityscheduling.com/learn/fill-slots-with-waitlist-software | Snippet |
| DPDP Rules 2025 | JSA Prism, KPMG, EY, Mondaq, SCC Online summaries | https://www.jsalaw.com/wp-content/uploads/2025/11/JSA-Prism-InfoTech-November-2025-DPDP-Rules.Final_.pdf , https://assets.kpmg.com/content/dam/kpmgsites/in/pdf/2025/11/dpdp-rules-2025-guidance-to-dpdp-act-implementation.pdf , https://www.mondaq.com/india/data-protection/1708164/digital-personal-data-protection-rules-2025-notified | Snippets; Gazette text not read |
| No-show fees | Medesk; Portrait | https://www.medesk.net/en/blog/doctors-office-no-show-fee/ , https://support.joinportrait.com/knowledge-legacy/no-shows-or-late-cancellations-setting-up-a-cancellation-or-deposit-fee | Snippet |
