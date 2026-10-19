# SUBMISSION: Problem 2, Clinic Appointment Scheduler

Most of the code was written with Claude Code; every prompt is in `PROMPTS.md` and the disclosure is README section 12. `docs/CODE-TOUR.md` maps each rule to its code and test.

## A. What I built

A booking system for a two-doctor clinic: a FastAPI and PostgreSQL API with a React and TypeScript UI, started locally with `docker compose up --build` and hosted on Vercel, Render and Neon (links in README section 2). All Core features work (doctors with weekly hours and date overrides, patients with a unique phone, free slots, booking, cancelling, rescheduling, completed and no-show, history, day view, today's queue and the reviewer test clock). All seven business rules are enforced in the backend, hold under simultaneous requests, and have a boundary test for every number. I also built the Stretch items (waitlist with automatic offers, recurring appointments, calendar export) and extras: nearest alternatives for a full day, a "prove the rules" page that rolls back what it runs, staff accounts with roles and password reset, doctor logins with a "My day" page, clinic-editable rules, reminders through a Twilio SMS or WhatsApp gateway or a webhook, a trends report, and consent and erasure of patient data. The UI is a calm, KJBN Labs-styled business app shell, checked with axe-core and in a real browser at phone, tablet and desktop widths.

## B. Three design decisions

**1. Lock the doctor row before every booking and every change to the hours.** *Alternative:* exclusion constraints alone, or SERIALIZABLE retries. *Why:* a constraint stops an overlap but not a count; without the lock ten simultaneous bookings all passed a cap of three, with it exactly three did. *Cost:* writes for one doctor are serialised and every path must take locks in one fixed order.

**2. One pure predicate, `first_violation`, decides both which slots are offered and which bookings are accepted.** *Alternative:* separate checks in the UI, the slot list and the endpoint. *Why:* the UI can never offer a time the API refuses, and "now" is an argument, so rules test without a database or clock. *Cost:* each check loads that day's appointments, fine for two doctors.

**3. Derive the deposit flag instead of storing it.** *Alternative:* a column kept current by a job. *Why:* a derived value cannot go stale and follows the test clock. *Cost:* computed on each read. (`needs_attention` started derived too; at scale it became a stored, indexed flag refreshed in the transaction that changes the hours.)

## C. The hardest part

Proving the locking instead of believing it. A same-slot race passed even with the lock removed, because the exclusion constraint already stops overlaps, so that test proved nothing about the lock. Only the daily cap under ten simultaneous bookings and a booking racing a leave day fail without it (`c0a916c`, `d64983b`); the ordered locks are in `4a250f0` and `e3d1efd`. A mutation run then showed three of ten planted bugs (a 61-day horizon, a non-strict "past", an exclusive 30-day look-back) survived random scenarios, so I biased the generators to boundary days (`f1caeec`). The assistant also proposed shared phone numbers to lift a documented limit; I removed them again because the brief says phone is unique (`9c50faf`), and the migration history (0005, then 0006) shows that detour.

## D. How I handle failure

| Failure | Travels as | User sees | Logged |
|---|---|---|---|
| Bad request | Schema, body guard | 400, 413 or 422 naming the field, never the value | info |
| Rule violation | `RuleViolation` / `ConflictError`, rolled back | 409 or 422, a code and details | warning, code and ids |
| Database error | Mapped by SQLSTATE and constraint | The same 409 or 422; database down: 503 with `Retry-After` | warning, error for 503 |
| Unexpected exception | Caught by the middleware | 500, generic message, request id | error with stack, server only |

Every response has one shape: `code`, `message`, `details`, `request_id`.

## E. Milestone log

| Milestone | Date completed | Commit |
|---|---|---|
| M0 Scaffold and tooling | 2026-10-17 | `1075d3d` |
| M1 Schema, seed and rule tests | 2026-10-17 | `91d1bb4` |
| M2 Rules and services | 2026-10-17 | `88121a4` |
| M3 API | 2026-10-17 | `42b2a18` |
| M4 UI | 2026-10-17 | `1b68991` |
| M5 Docker, CI, deployment config | 2026-10-17 | `2a1559b` |
| M6 Documentation | 2026-10-17 | `bd72eaf` |

The tagged `m0` to `m6` commits. Later work is tagged `[M2]` to `[M6]` by area; `v1.0` is the final commit (the last pass above is `[M4]`: `If-Match` in `2fb1c12`, undo of a cancel in `5953d14`, the undo bar and the remembered patient in `7ae020a`, the app shell and Overview redesign in `60e14d6`).

## F. If I had two more days

1. A person who uses a screen reader audits the UI; axe-core passes, which is not the same.
2. A live Twilio account for the reminders, with delivery receipts; the gateway, the outbox and the webhook are built and tested against a stub, but not against a paid account.
3. Password reset by email and two-factor sign-in for staff accounts (reset today is a one-time code issued by an administrator).
4. A privacy notice, retention period and processor agreements reviewed by someone qualified; the erase and purge tools exist.
5. Load tests beyond 100 users and a shared rate limit (Redis) for more than one API instance.

## G. Self-assessment

| Criterion (weight) | Score | Why |
|---|---|---|
| Business logic (25) | 5 | Seven rules and the edge cases enforced, tested at every boundary and under races; readings are numbered assumptions |
| Code clarity (14) | 5 | Layers guarded by an import test, strict types, no function past about 80 lines, a code tour with live drills |
| Error handling (10) | 5 | Typed errors, one shape, rollback, no stack to clients; the fuzzer found a 500 and it is fixed and tested |
| Logging (8) | 5 | Structured JSON with request id, a catalogue of events, a test that no log line holds personal data, `/metrics` |
| Data modelling (9) | 5 | Exclusion, CHECK and UNIQUE constraints, 15 migrations, stored versus derived documented, hash-chained audit |
| API design (8) | 5 | Conventions written down, pagination, idempotency keys, optional `If-Match`, one error shape, OpenAPI fuzzed over every operation |
| UI (6) | 4 | Flows work unaided, axe clean, phone layouts; never tried by a real receptionist or a screen-reader user |
| Testing (7) | 5 | 1,450 backend and 220 frontend tests, browser, fuzz and load runs, every statement of the rules layer covered |
| Deployment (5) | 4 | One-command stack, CI and a keep-alive; hosted and checked live (README section 2) |
| Git hygiene (4) | 3 | Conventional commits, one author, tags; but commits came in batches (several share a minute) over two days. Timestamps are real, unedited |
| Documentation (4) | 4 | README in the required order, limitations stated, this write-up cites commits |
