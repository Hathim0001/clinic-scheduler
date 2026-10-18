# SUBMISSION: Problem 2, Clinic Appointment Scheduler

Most of the code was written with Claude Code; every prompt is in `PROMPTS.md` and the disclosure is README section 12. `docs/CODE-TOUR.md` maps each rule to its code and test.

## A. What I built

A booking system for a two-doctor clinic: a FastAPI and PostgreSQL API with a React and TypeScript UI, started locally with `docker compose up --build`. All Core features work: doctors with weekly hours and date overrides, patients with a unique phone, free slots, booking, cancelling, rescheduling, completed and no-show, history, a day view, today's queue and the reviewer test clock. All seven business rules are enforced in the backend and hold under simultaneous requests, with a boundary test for every number. Hosted on Vercel (UI), Render (API) and Neon (database), with links in README section 2. I also built the Stretch items (waitlist with automatic offers, recurring appointments, calendar export) and extras: nearest alternatives when a day is full, a "prove the rules" page that rolls back what it runs, a refill metric, optional staff accounts with roles, consent and erasure of patient data, and a message outbox.

## B. Three design decisions

**1. Lock the doctor row before every booking and every change to the hours.** *Alternative:* exclusion constraints alone, or SERIALIZABLE retries. *Why:* a constraint stops an overlap but not a count; without the lock ten simultaneous bookings all passed a cap of three, with it exactly three did. *Cost:* writes for one doctor are serialised, every path must take locks in the same order (appointment, doctors by id, waitlist entry, patient) to avoid deadlock, and a real deadlock is retried once.

**2. One pure predicate, `first_violation`, decides both which slots are offered and which bookings are accepted.** *Alternative:* separate checks in the UI, the slot list and the endpoint. *Why:* the UI can never offer a time the API refuses, and "now" is an argument, so rules test without a database or clock. *Cost:* each check loads that day's appointments into memory and copies rows into dataclasses, which is fine for a two-doctor clinic but would need a query-side filter for a large one.

**3. Derive the deposit flag instead of storing it.** *Alternative:* a column kept current by a job. *Why:* a derived value cannot go stale and follows the test clock. The same applies to `needs_attention`. *Cost:* it is computed on each read, so the needs-attention list scans every matching row and would need a stored flag on a large database.

## C. The hardest part

Proving the locking instead of believing it. A same-slot race passed even with the lock removed, because the exclusion constraint already stops overlaps, so that test proved nothing about the lock. Only the daily cap under ten simultaneous bookings and a booking racing a leave day fail without it (`ffd67af`, `846a8b4`); the ordered locks are in `a86d53f` and `6a2f532`. A mutation run then showed three of ten planted bugs (a 61-day horizon, a non-strict "past", an exclusive 30-day look-back) survived random scenarios, so I biased the generators to boundary days (`c916346`). The assistant also proposed shared phone numbers to lift a documented limit; I removed them again because the brief says phone is unique (`0e11e9d`), and the migration history (0005, then 0006) shows that detour.

## D. How I handle failure

| Failure | Travels as | User sees | Logged |
|---|---|---|---|
| Bad request | Pydantic schema, body guard | 400, 413 or 422 naming the field, never the value | info |
| Rule violation | `RuleViolation` / `ConflictError`, transaction rolled back | 409 or 422 with a code and details | warning, code and ids |
| Database error | Mapped by SQLSTATE and constraint name | The same 409 or 422; database down gives 503 with `Retry-After` | warning, error for 503 |
| Unexpected exception | Caught by the middleware, inside CORS | 500, generic message, request id | error with stack, server only |

Every response has one shape: `code`, `message`, `details`, `request_id`.

## E. Milestone log

| Milestone | Date completed | Commit |
|---|---|---|
| M0 Scaffold and tooling | 2026-10-17 | `b2bb58a` |
| M1 Schema, seed and rule tests | 2026-10-17 | `efff237` |
| M2 Rules and services | 2026-10-17 | `f44da64` |
| M3 API | 2026-10-17 | `a02efc2` |
| M4 UI | 2026-10-17 | `ba91b44` |
| M5 Docker, CI, deployment config | 2026-10-17 | `75ff1b1` |
| M6 Documentation | 2026-10-17 | `334ed71` |

These are the tagged `m0` to `m6` commits. Work after M6 (Stretch features, redesign, hardening) is tagged `[M2]` to `[M6]` by area, and `v1.0` is the final commit.

## F. If I had two more days

1. A person who uses a screen reader audits the UI; axe-core passes, which is not the same, and software cannot stand in for that.
2. A real SMS or WhatsApp gateway with delivery receipts and reminders; the outbox and the webhook are built, the account is not.
3. Password reset by email and two-factor sign-in for staff accounts.
4. A written privacy notice, a retention period and processor agreements, reviewed by someone qualified; the erase and purge tools exist.
5. Load tests beyond 100 users and a shared rate limit (Redis) for more than one API instance.

## G. Self-assessment

| Criterion (weight) | Score | Why |
|---|---|---|
| Business logic (25) | 5 | Seven rules and the edge cases enforced, tested at each boundary and under races; open readings are numbered assumptions |
| Code clarity (14) | 4 | Layers guarded by an import test, strict types; `Admin.tsx` is still long |
| Error handling (10) | 5 | Typed errors, one shape, rollback, no stack to clients |
| Logging (8) | 4 | Structured JSON with request id and codes, no personal data; hosted logs are owner-only |
| Data modelling (9) | 5 | Exclusion, CHECK and UNIQUE constraints, migrations, derived versus stored documented |
| API design (8) | 4 | Resource paths, pagination, OpenAPI fuzzed; cancel and mark are action endpoints |
| UI (6) | 4 | Flows work unaided, axe clean, phone layouts; never tried by a real receptionist |
| Testing (7) | 5 | 1,165 backend and 141 frontend tests, 99 % backend coverage, browser and fuzz runs in CI |
| Deployment (5) | 4 | One-command stack and CI; hosted and checked live (see README section 2) |
| Git hygiene (4) | 3 | Conventional commits, one author, tags; but commits were made in batches (several share a minute) over two days, not a steady cadence. Timestamps are the real ones, unedited |
| Documentation (4) | 4 | README in the required order, limitations stated, this write-up cites commits |
