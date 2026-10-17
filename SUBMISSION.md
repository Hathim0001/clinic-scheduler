# SUBMISSION

Problem 2: Clinic Appointment Scheduler. Draft written with Claude Code (see README section 12 and
PROMPTS.md); the author is expected to read it, correct it and own it.

## A. What I built

A booking system for a two-doctor clinic: a FastAPI and PostgreSQL API with a React and TypeScript UI,
started locally with one `docker compose up --build`. All Core features are complete: doctors with
weekly hours and date overrides, patients with unique phones, free slots, booking, cancelling,
rescheduling, completed and no-show, patient history, a day view, today's queue and the reviewer test
clock. All seven business rules are enforced in the backend and hold under concurrent requests, with a
boundary test for every number. Partial: the hosted instance is configured (Render, Neon and Vercel
files, a runbook) but not deployed yet, and the UI has component tests but no browser end-to-end tests.
I built no Stretch items.

## B. Three design decisions

**1. Lock the doctor row before every booking and every change to the hours.** *Alternative:*
exclusion constraints alone, or SERIALIZABLE transactions with retries. *Why:* a constraint can stop
an overlap but not a count (the daily cap), and a change to the hours must not interleave with a
booking. Without the lock ten simultaneous bookings all passed a cap of three; with it exactly three
did. *Cost:* writes for one doctor are serialised, and every code path must keep the lock order.

**2. One pure predicate, `first_violation`, decides both which slots are offered and which bookings
are accepted.** *Alternative:* separate checks in the UI, the slot list and the booking endpoint.
*Why:* the UI can never offer a slot the API refuses, and the rules need no database or clock to test,
because "now" is an argument. *Cost:* each check loads that day's appointments into memory and copies
rows into dataclasses.

**3. Derive the deposit flag and `needs_attention` instead of storing them.** *Alternative:* a flag
column kept up to date by a job or a trigger. *Why:* a derived value cannot go stale, needs no
scheduler and follows the test clock. *Cost:* it is computed on each read, so the `needs_attention`
filter scans the matching rows.

## C. The hardest part

Proving the locking design instead of believing it. A same-slot race passed even with the doctor lock
removed, because the exclusion constraint already stops overlaps, so that test said nothing about the
lock. The tests that do need it are the daily cap under ten simultaneous bookings and a booking racing
a leave day: without the lock both fail on every run (`59608e2`, `d2158ee`). The lock lives in
`45fc2b5` (availability) and `0978a53` (booking). A mutation run on my rule tests then showed that
three of ten planted bugs (a 61-day horizon, a non-strict "past" check, an exclusive 30-day look-back)
survived random scenarios; I biased the generators toward boundary days and ages until all ten were
caught (`ad3fd0e`). A real PostgreSQL deadlock, retried once, is tested in `0248846`.

## D. How I handle failure

| Failure | Travels as | The user sees | Logged |
|---|---|---|---|
| Bad request | Pydantic schema, body guard | 400, 413 or 422 listing the fields, never the value | info |
| Rule violation | `RuleViolation` or `ConflictError` from `domain/`, transaction rolled back | 422 or 409 with a code and details | warning, code and ids |
| Database error | Constraint violation mapped by SQLSTATE and constraint name | The same 409 or 422 the pre-check gives; a database that is down or a lock timeout gives 503 with `Retry-After` | warning, or error for 503 |
| Unexpected exception | Caught by the request-context middleware, inside CORS | 500 with a generic message and the request id | error with stack trace (server only) |

Every response has one shape: `code`, `message`, `details`, `request_id`.

## E. Milestone log

| Milestone | Date completed | Commit |
|---|---|---|
| M0 Scaffold and tooling | 2026-10-17 | `f280d09` |
| M1 Schema, seed and rule tests | 2026-10-17 | `a3c0f93` |
| M2 Rules and services | 2026-10-17 | `0248846` |
| M3 API | 2026-10-17 | `e672db2` |
| M4 UI | 2026-10-17 | `838ef7a` |
| M5 Docker, CI, deployment config | 2026-10-17 | `b9c8181` |
| M6 Documentation | 2026-10-17 | `573f409` |

## F. If I had two more days

1. Deploy to Render, Neon and Vercel and rehearse every edge case on the hosted instance: a missing hosted link costs the most.
2. Playwright end-to-end tests for the booking, cancelling and conflict-dialog flows, because the UI is only component-tested.
3. Authentication with roles and rate limiting, since the API exposes patient names and phones.
4. Corrections of final statuses with an audit trail; today a mistaken no-show stays.
5. A stored, indexed `needs_attention` and pagination of the patient history, for a database that is no longer tiny.

## G. Self-assessment

| Criterion (weight) | Score | Why |
|---|---|---|
| Business logic correctness (25) | 5 | All seven rules and the listed edge cases are enforced and tested, including races; the open readings are numbered assumptions |
| Code clarity and structure (14) | 4 | Clear layers guarded by an import test, linters and strict types; a few long files such as `Admin.tsx` |
| Error and exception handling (10) | 5 | Typed errors, one shape, transactions, no stack traces to clients, worded messages in the UI |
| Logging and observability (8) | 4 | Structured JSON with request id and domain ids, warnings with codes, health endpoints; hosted logs are owner-only |
| Data modelling and persistence (9) | 5 | Exclusion and CHECK constraints, migrations, realistic seed, derived versus stored documented |
| API design (8) | 4 | Resource paths, pagination, OpenAPI checked by tests and a fuzz run; cancel and mark are action endpoints |
| UI usability (6) | 4 | Flows work without instructions, buttons follow the server, loading, error and phone layouts; never tried by a real receptionist |
| Testing (7) | 5 | 827 backend tests, a boundary test per number, property and race tests, 100 % on the rules layer; UI coverage not measured |
| Deployment and operability (5) | 3 | One-command local stack, Dockerfiles, CI and blueprint committed; not deployed yet, to be raised after the first deploy |
| Git hygiene (4) | 4 | Conventional commits with milestone tags in logical steps; one working day of history |
| Documentation and write-up (4) | 4 | README follows the format with limitations stated; this write-up cites commits |
