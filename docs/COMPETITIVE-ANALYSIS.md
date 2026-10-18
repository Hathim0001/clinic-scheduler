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
