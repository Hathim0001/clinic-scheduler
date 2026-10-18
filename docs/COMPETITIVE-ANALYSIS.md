# Competitive analysis and where an LLM could (and could not) help

Searched on 2026-10-18. The sources are vendor pages, directory listings and practice blogs, not
independent studies, so figures below are **claims by those vendors** and are marked as such. I did
not find the Zocdoc, Calendly or SimplePractice feature pages in the search results, so I do not
compare against them; nothing here is said about a product I did not find evidence for.

## What the market offers

| Product / category | What the evidence says | Source |
|---|---|---|
| Acuity Scheduling | A built-in waitlist: a client joins from the booking page and gets a text when a matching slot opens; the clinic sets how close to the appointment a waitlist booking is accepted. Waitlist is on its Standard and Premium plans, for one-on-one appointments, with SMS. | [Acuity](https://acuityscheduling.com/learn/fill-slots-with-waitlist-software) |
| Novoflow (AI) | Claims to watch the schedule, offer a freed slot to the next caller and book the patient into the record without staff. Vendor claim. | [Novoflow](https://ai.novoflow.io/software-fills-cancelled-slots-immediately-novoflow) |
| DoctorConnect | Claims instant detection of cancellations and automatic text, email or app notification of waitlisted patients. Vendor claim. | [DoctorConnect](https://doctorconnect.net/waiting-list-management-streamline-appointments-fast) |
| MedicalMet | A prioritised waitlist with urgency levels and day preferences; when a slot opens it surfaces the best-matching patients and **staff pick** one. | [MedicalMet](https://www.medicalmet.advisoryapps.com/features/appointment-waitlist/) |
| Waitlist tools in general | A review notes some tools genuinely watch the live schedule and fill gaps, while others are "a tagged list inside a messaging inbox" a person still has to work. | [Emitrr](https://emitrr.com/?p=82920) |
| Ray by Practo (India) | Listed as scheduling plus patient engagement (booking, automated messages, intake forms, SMS/email), Capterra 4.0/5 from 8 reviews; one aggregator shows from Rs 999 a month (unconfirmed). | [Capterra](https://www.capterra.in/software/167778/ray), [FitGap](https://us.fitgap.com/products/ray-by-practo) |
| No-show and late-cancel policy | Practices typically use a 24 or 48 hour window and a fee of $25 to $75 or a share of the visit fee; some take a deposit at booking. Evidence is practitioner anecdote and vendor marketing; a 2008 article puts the average medical-office no-show rate at 5 to 7 percent. | [Medesk](https://www.medesk.net/en/blog/doctors-office-no-show-fee/), [Portrait](https://support.joinportrait.com/knowledge-legacy/no-shows-or-late-cancellations-setting-up-a-cancellation-or-deposit-fee), [AMA News 2008](https://amednews.com/article/20080602/business/306029998/5/) |

## What this means for the design

1. **A waitlist that fills a freed slot is table stakes**, and the weak version (a list a person
   works by hand) is common. This project's offer is automatic, time-limited, ordered, and goes
   through the same booking rules as any other booking, so a patient is never offered a time they
   could not book. The report now measures whether it works (innovation 3 below).
2. **Penalties are usually money**, taken by card at booking. This project has no payments by
   design (the problem statement asks for a *deposit acknowledgement*, not a payment), so the
   rule is a derived flag: two strikes in 30 days. That is simpler and cannot go stale, but it also
   means there is no real money at stake, which I say in the README rather than claim parity.
3. **Competitors sell outcomes; a take-home can only show correctness.** Where products claim
   "fewer no-shows", this project can only show that its rules hold at the boundaries and under
   concurrency. That is why the three additions below are about proving behaviour and measuring
   recovery, not about claiming business results.

## The three additions, and why these three

| Addition | The gap it answers | Where |
|---|---|---|
| **Nearest alternatives** when a day is full | The moment of refusal is where a phone call is lost; the MedicalMet-style "best match" idea, but only ever from times the booking rules accept for this patient and visit length | `GET /alternatives`, `Alternatives.tsx` |
| **Prove the rules** page | Vendors ask to be trusted; this runs the boundary scenarios on the real services and database, then rolls back, and shows the row counts before and after | `POST /diagnostics/proof`, `proof_service.py`, `/proof` |
| **Recovery metric** in the report | "Waitlist fills cancellations" is the standard claim; the report counts freed slots, how many were refilled, and how many by the waitlist | `record_service._recovery`, Report page |

## Could an LLM component help? A reasoned answer, not an implementation

Yes in three places, and I have deliberately **not** added one to the graded core:

| Idea | Value | Risk and cost | Decision |
|---|---|---|---|
| Free-text reason to urgency or speciality triage | The current triage is a keyword list with a disclaimer; a model could understand "pain in my chest when I climb stairs" | A wrong answer is a patient-safety problem; sending symptom text to a third party is a privacy and (in India) data-protection problem; it adds a paid, rate-limited dependency to the booking path | Keep the keyword rule. If added, it must only ever **raise** urgency, never lower it, and run behind a consent step |
| Natural-language booking ("Dr. Rao next Tuesday morning for Asha") | Faster for a receptionist | The model would only produce a *search*, not a booking: the output must be validated like any request, so the booking rules remain the only authority | Reasonable later feature; not needed to meet the brief |
| Summarising a patient's history for the doctor | Time saved | Sends health records to a third party; hallucinated history is dangerous | Out of scope |

The principle I would keep if one is added: **the model may suggest, the rules decide.** Every
suggestion goes through the same validation as a human request, nothing the model says is
trusted as data, and the clinic works with the model switched off. A component that fails
closed (falls back to today's behaviour) is the only kind that belongs in a booking path.

## Gap analysis: what the products above have and this one does not

Searched again on 2026-10-18. Feature claims come from the vendors' own pages or from review and
directory sites, so they show what is *advertised*, not what works well. Where a source was thin
the row says so.

| Capability | Evidence from competitors | This project | Matters for the brief? |
|---|---|---|---|
| Patients book for themselves online | Jane lets a clinic choose which treatments, times and staff are bookable online ([Jane](https://jane.app/features/online-booking)); Zocdoc says bookings from Zocdoc, Google or a practice website update the schedule ([Zocdoc](https://www.zocdoc.com/about/ai-llm-info/)) | **No.** Staff-only; the brief describes a clinic that takes bookings by phone | No |
| Reminders before the visit | Zocdoc lists emails 7 days and 1 day ahead and a text about 3 hours ahead; Jane and Ray send SMS or email reminders ([Jane](https://www.getapp.com/healthcare-pharmaceuticals-software/a/jane-app/reviews/), [Ray](https://www.capterra.com/p/167778/Ray/)) | **No.** Only confirmations, clinic cancellations and waitlist offers; no per-appointment timer | Stretch-adjacent; not asked |
| Two-way SMS (reply to confirm or reschedule) | Repeatedly named the differentiator in vendor guides ([DoctorConnect](https://doctorconnect.net/automated-appointment-reminders-reduce-no-shows)) | **No.** Outbound only, through a webhook the clinic must supply | No |
| A message gateway that actually sends | Built into every product above | **No account.** Messages queue and wait for reception unless `NOTIFY_WEBHOOK_URL` is set | No (SMS optional) |
| Money: deposits, no-show fees, card on file | Jane can take full or partial deposits and keep a card to enforce late-cancellation rules ([Jane guide](https://jane.app/guide/category/schedule)); practices commonly charge $25 to $75 or a share of the visit ([Medesk](https://www.medesk.net/en/blog/doctors-office-no-show-fee/)) | **No.** A deposit is an acknowledgement only, as the brief specifies | No (the brief says acknowledgement) |
| Waitlist that fills a freed slot | Acuity and Jane have one; some products only keep a list a person works by hand ([Acuity](https://acuityscheduling.com/learn/fill-slots-with-waitlist-software), [Emitrr](https://emitrr.com/?p=82920)) | **Yes**, automatic, timed, rule-checked, and measured in the report | Stretch, done |
| Multi-location, rooms, equipment | Jane lists multi-location, multi-practitioner and room booking ([GetApp](https://www.getapp.com/healthcare-pharmaceuticals-software/a/jane-app/)); Ray lists multi-branch support ([Capterra](https://www.capterra.com/p/167778/Ray/)) | **No.** One clinic | No (two-doctor clinic) |
| Appointment types with their own length, buffers, minimum notice, booking limits | Cal.com offers buffers, minimum notice and booking limits per event type ([Cal.com](https://cal.com/blog/mastering-event-level-time-limits-what-lies-beyond-buffer-times)) | **Partly.** A visit lasts 1 to 4 of the doctor's slots; no types, no buffers, no minimum notice | No |
| EHR or EMR, intake forms, insurance | Zocdoc says it connects to 175+ EHRs and collects insurance details and forms ([Zocdoc](https://www.zocdoc.com/about/ai-llm-info/)); Ray includes EMR and billing ([Capterra](https://www.capterra.com/p/167778/Ray/)) | **No.** A reason text and a symptom keyword warning only | No |
| Online discovery and reviews | Zocdoc and Practo are marketplaces | **No** | No |
| Reports and analytics | Standard in the above | **Basic.** Outcomes, rates, utilisation, refill rate; no export to CSV, no charts | Small gap |
| Calendar sync | Two-way sync with Google or Outlook in Cal.com and Zocdoc | **One-way**: `.ics` download | Stretch, done |
| Languages and local channels | Practo targets Indian clinics; WhatsApp is only thinly sourced for Ray | English only; no WhatsApp | No |
| Native or mobile app | Several | Responsive web only | No |

## Drawbacks that are ours, not a feature gap

These are weaknesses in what is built, whatever the competitors do:

1. **Never used by a real receptionist.** The flows were tested by software and by the author, not
   by someone running a front desk, so labels and ordering may not match how a clinic talks.
2. **No screen-reader audit by a person**, only axe-core and keyboard checks.
3. **Free-tier hosting.** One API instance, a database that suspends when idle, and a keep-alive
   workaround; no backups beyond the provider's, no staging environment, no alerts.
4. **One language and one time zone**, by design, but a hard limit for any other clinic.
5. **Large rule surface for a two-doctor clinic.** 68 numbered assumptions and a long limitations
   list are honest, but they are a lot to defend on a 45-minute call; the extras beyond the brief
   (accounts, messages, privacy tools, hash chain) add code that someone must be able to explain.
6. **Most of the code was written with an AI assistant.** It is disclosed and logged, but the brief
   names unexplained AI code as the one disqualifying risk, so understanding it is the real task.

## What this means for a decision

Nothing in the first table is something the brief asks for, and the brief says a complete Core
beats extra features. If one gap were closed first, the evidence points to **reminders and
two-way SMS**: they are the feature every product sells to cut no-shows (vendor figures of 30 to
50 percent are widely quoted but come from vendors and are not verified here), and the outbox and
webhook already built are the place to attach them. For the submission itself, the better use of
time is the list of things only the author can do: trying the edge cases on the hosted site and
rehearsing the code walkthrough.
