# Clinic Appointment Scheduler

[![CI](https://github.com/Hathim0001/clinic-scheduler/actions/workflows/ci.yml/badge.svg)](https://github.com/Hathim0001/clinic-scheduler/actions/workflows/ci.yml)
![Python 3.13](https://img.shields.io/badge/python-3.13-3776ab)
![PostgreSQL 16](https://img.shields.io/badge/postgresql-16-336791)
![React 19](https://img.shields.io/badge/react-19-149eca)

> An appointment desk for a two-doctor clinic, where every booking is checked against the clinic's
> rules on the server, so a doctor is never double-booked, even when two receptionists click at once.

**Contents:**
[1 Title](#1-title-and-one-liner) ·
[2 Live links](#2-live-links) ·
[3 Tech stack](#3-tech-stack) ·
[4 Architecture](#4-architecture) ·
[5 Running locally](#5-running-locally) ·
[5a Deployment](#5a-deployment) ·
[6 Tests and coverage](#6-running-tests-and-coverage) ·
[7 API](#7-api-overview) ·
[8 Business rules](#8-business-rules-and-assumptions) ·
[9 Errors and logging](#9-error-handling-and-logging) ·
[10 Reviewer aids](#10-reviewer-aids) ·
[11 Limitations](#11-known-limitations) ·
[12 AI usage](#12-ai-and-third-party-usage)

## 1. Title and one-liner

**Problem 2: Clinic Appointment Scheduler** (KJBN Labs software engineering internship take-home).
A booking system for a two-doctor clinic that takes appointments by phone. It only offers slots that
can really be booked and enforces availability, the slot grid, double booking, the daily cap,
late-cancellation and deposit rules and the 60-day booking window, including under concurrent
requests. Every AI prompt used is logged in [PROMPTS.md](PROMPTS.md) and disclosed in
[section 12](#12-ai-and-third-party-usage).

**At a glance**

| | |
|---|---|
| Business rules | All 7 enforced in the backend, each with boundary tests and a race test where concurrency matters |
| Tests | 1,450 backend (99 % coverage) and 222 frontend; 26 browser flow checks and 24 accessibility scans |
| Robustness | OpenAPI fuzzed over every operation with no server error; one error shape for every failure |
| Data integrity | PostgreSQL exclusion, CHECK and UNIQUE constraints back the rules; hash-chained audit trail |
| Beyond the brief | Waitlist with offers, recurring bookings, reminders, staff roles, clinic-editable rules, trends report |

**Review in five minutes**

1. Open the [live UI](https://clinic-scheduler-ruby.vercel.app) and press **Seed day 09:30** in the amber clock bar: the demo data is built around that morning.
2. Try a rule: book Arjun Mehta with Dr. Menon at 10:00 on that day (he is already with Dr. Rao: the time is not offered), or cancel the 11:15 visit as the patient (inside two hours: a late cancel).
3. Open **Prove the rules** to run every rule scenario against the real database and see it rolled back.
4. Read [section 8](#8-business-rules-and-assumptions) for each rule, its code and its tests, and [section 11](#11-known-limitations) for what is not built.

## 2. Live links

Hosted on Vercel (UI), Render (API) and Neon (PostgreSQL). Section 5a lists the steps, and
`render.yaml`, `backend/Dockerfile`, `frontend/vercel.json` and `docker-compose.yml` are the committed
configuration.

| What | URL |
|---|---|
| UI | https://clinic-scheduler-ruby.vercel.app |
| API base | https://clinic-api-pn9t.onrender.com/api/v1 |
| API docs (OpenAPI) | https://clinic-api-pn9t.onrender.com/docs |

**Sign-in.** Sign-in is required by default, so that patient names and phone numbers are not readable
by anyone holding the link. The assignment makes authentication optional, so the hosted instance is
deliberately left open for the review (`ALLOW_OPEN_ACCESS=true`) and every page says so. The local
`docker compose` stack does the same. Section 5 lists the settings that switch sign-in on.

**Cold start.** On Render's free plan the API sleeps when idle and the first request can take about a
minute. A scheduled workflow pings it every 10 minutes to keep it awake (section 11), and the UI shows
"Waking the server" instead of a blank page.

## 3. Tech stack

| Layer | Choice | Why, where it is not the obvious one |
|---|---|---|
| Backend | Python 3.13, FastAPI 0.143, SQLAlchemy 2.1 (sync), Alembic, psycopg 3, Pydantic 2, structlog | A recommended stack. Sync SQLAlchemy keeps transactions and row locks easy to reason about |
| Database | PostgreSQL 16 | Not a free choice: `EXCLUDE USING gist` constraints make overlapping appointments impossible to store, which SQLite and MySQL cannot do |
| Frontend | React 19, TypeScript 6.0, Vite 8, TanStack Query, React Router 7 | A recommended stack |
| Tests | pytest, Hypothesis, pytest-cov (backend); Vitest and Testing Library (frontend); Schemathesis (in CI); a real Chrome with axe-core for end-to-end and accessibility checks | |
| Quality | ruff (lint and format), mypy (strict on `domain/`), ESLint, tsc | Enforced in CI |
| Hosting | Render (API, Docker), Neon (PostgreSQL), Vercel (UI) | Free tiers |
| CI/CD | GitHub Actions, Docker Compose | |

All versions are pinned in `backend/requirements*.txt` and `frontend/package-lock.json`.

## 4. Architecture

```
 Browser: React + TypeScript (Vercel)
        |  HTTPS, JSON         headers: X-Test-Clock (optional), X-Request-ID
        v
 FastAPI (Render) ----- middleware, outermost first --------------------------------------
        |               CORS  ->  request context: request id, 64 KiB body guard,
        |                         one JSON log line per request, catch-all 500
        v
   api/          routers and strict Pydantic schemas; each route calls ONE service method
        v
   services/     one transaction per call; takes the row locks; asks the domain to decide
     |       \
     |        v
     |      domain/       pure rules: no I/O, no framework, "now" is an argument
     v
   persistence/  SQLAlchemy models, repositories, error mapping
        v
 PostgreSQL 16 (Neon): CHECKs and EXCLUDE constraints back the booking rules
```

A booking, in order: the request is validated and bounded by the schema; `BookingService` opens a
transaction and locks the doctor row, then the patient row; it loads the doctor's hours, that day's
appointments and the patient's strikes; `first_violation` (the one rule predicate, also used to
offer slots) and `deposit_status` decide; the row is inserted and PostgreSQL has the last word on
overlaps; commit. Any domain error rolls everything back and leaves the standard error body.

| Folder | What it holds |
|---|---|
| `backend/app/api/` | HTTP only: routers, schemas, error handlers, middleware. No rules |
| `backend/app/services/` | Transactions, locks and orchestration: booking, availability, doctors, patients, queries |
| `backend/app/domain/` | **The business rules**: availability, slots, booking window, cancellation, penalties, state machine, phone numbers, the error catalogue |
| `backend/app/persistence/` | Models, repositories, the engine, mapping of database errors |
| `backend/migrations/` | Alembic: `0001_initial` creates the schema, including the constraints |
| `backend/scripts/` | `migrate_and_seed.py`, `seed.py`, `run_tests.py`, `burst.py` |
| `backend/tests/` | `unit/` (no database), `integration/` (PostgreSQL, including race tests), `api/` (through HTTP) |
| `frontend/` | The React app and its tests |
| `docs/` | `DESIGN-NOTES.md`, `PRIVACY-AND-OPERATIONS.md`, `sample-logs.jsonl` (real log lines), `prompts/` (the full planning brief) and `screenshots/` |
| `.github/workflows/ci.yml`, `docker-compose.yml`, `render.yaml` | CI, local stack, hosting |

**Where the rules live, and why there.** The rules are in `backend/app/domain/` because they are the
part that must be right and the part a reader checks first: that folder imports only the standard
library (a test scans its imports), takes the current time as an argument and is type-checked
strictly, so every rule can be tested in microseconds without a database or a clock. `services/`
enforces them inside transactions and locks, and the database constraints guarantee the ones that
concurrency could otherwise break. The UI never decides anything: it shows the slots, the reasons and
the allowed actions the API sends.

**What it looks like** (seeded demo data, the clock set to the seed morning, Monday 2026-10-19 09:30).
The interface is drawn from the clinic itself: ECG paper under every page, each doctor's day as a
blister pack of capsules, the queue as appointment tickets, cards as chart folders.

| | |
|---|---|
| ![Overview](docs/screenshots/overview.png) | ![Day view](docs/screenshots/day-view.png) |
| ![Queue](docs/screenshots/queue.png) | ![Queue at 375 px](docs/screenshots/phone-375px.png) |

**Each business rule, as the user sees it** (the pictures are taken by `frontend/e2e/screenshots.mjs`):

| Rule | Picture |
|---|---|
| 1. Only times on the doctor's grid and inside the doctor's hours are offered | ![Rule 1](docs/screenshots/rules/1-availability-and-grid.png) |
| 2. A doctor is never booked twice at once: taken slots are filled in and cannot be picked | ![Rule 2](docs/screenshots/rules/2-doctor-never-double-booked.png) |
| 3. A patient is never booked twice at once: Arjun Mehta is with Dr. Rao at 10:00, so that time is missing from Dr. Menon's list for him | ![Rule 3](docs/screenshots/rules/3-patient-never-double-booked.png) |
| 4. The daily cap: five of six booked, then the sixth is taken and the rest of the day closes | ![Before](docs/screenshots/rules/4-daily-cap-before.png) ![Reached](docs/screenshots/rules/4-daily-cap-reached.png) |
| 5. Two strikes in 30 days require a deposit acknowledgement; a patient cancelling close to the start is recorded as late | ![Deposit](docs/screenshots/rules/5-deposit-after-two-strikes.png) ![Late cancel](docs/screenshots/rules/5-late-cancellation.png) |
| 6. A reschedule cancels the old slot and books the new one together, or neither happens | ![Rule 6](docs/screenshots/rules/6-reschedule-is-atomic.png) |
| 7. Nothing in the past and nothing more than 60 days ahead | ![Rule 7](docs/screenshots/rules/7-booking-window.png) |
| All of the above, run live against the real database and rolled back | ![Proof](docs/screenshots/rules/proof-of-all-rules.png) |

## 5. Running locally

**Prerequisites:** Docker Desktop with Compose v2, Python 3.13, Node 22 (22.13 or later), git.

**One command, everything in containers** (database, API, UI):

```bash
docker compose up --build
# UI  http://localhost:8080     API docs  http://localhost:8000/docs
```

Optional settings for the stack (sign-in, demo logins, a message gateway) go in a `.env` copied from
the root [`.env.example`](.env.example); the backend's own settings are in `backend/.env.example`.

**For development**, with the API and the UI on the host (bash; PowerShell equivalents in comments):

```bash
docker compose up -d db                      # PostgreSQL 16 on localhost:5433

cd backend
python -m venv .venv
source .venv/bin/activate                    # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env                         # PowerShell: Copy-Item .env.example .env
python -m scripts.migrate_and_seed --if-empty    # creates the schema, seeds the demo data once
uvicorn app.main:create_app --factory --reload   # http://localhost:8000/docs

# in a second terminal
cd frontend
cp .env.example .env                         # PowerShell: Copy-Item .env.example .env
npm ci
npm run dev                                  # http://localhost:5173
npm run format:check && npm run lint && npm run typecheck   # what CI runs (npm run format fixes)
```

| Variable | Where | Meaning |
|---|---|---|
| `DATABASE_URL` | backend | SQLAlchemy URL. Default is the compose database. On Neon use the **direct** string (not the `-pooler` host) with `?sslmode=require`; `postgresql://` works as Neon shows it, `postgres://` does not |
| `CORS_ORIGINS` | backend | Comma-separated origins the browser UI may call from |
| `TEST_CLOCK_ENABLED` | backend | `true` lets a request set "now" with the `X-Test-Clock` header (reviewer aid, section 10). Off by default |
| `LOG_LEVEL` | backend | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |
| `DB_CONNECT_TIMEOUT_S` | backend | Seconds to wait for a database connection (default 10) |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | backend | Database connections kept per process and how many more a burst may borrow (defaults 5 and 5) |
| `TRUSTED_PROXY_HOPS` | backend | How many reverse proxies append to `X-Forwarded-For` (default 0; the Render blueprint sets 1). The rate limit counts the entry that many places from the right, because the left side can be forged |
| `ALLOW_OPEN_ACCESS` | backend | `false` by default: sign-in is **required**. Set `true` only for a demo; the app then says on every page that sign-in is off. Ignored (sign-in stays required) when a secret or shared password is set |
| `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD` | backend | Together, with `AUTH_SECRET`: creates the first administrator at start-up, only when no account exists yet, so a later change here never touches a clinic that is set up |
| `SEED_DEMO_ACCOUNTS`, `DEMO_ACCOUNTS_PASSWORD` | backend | Local demos only: with the seed, also creates `reception` and `dr.rao` / `dr.menon` logins (one per role) with that password, once |
| `STAFF_PASSWORD` | backend | Optional, 8+ characters. A single shared password: every route except the health checks, the clock and the login needs a signed token, and each audit row names who made the change |
| `AUTH_SECRET` | backend | 16+ characters. Signs sessions and turns on **individual staff accounts with roles** (administrator, receptionist or doctor): people sign in with their own username and password, and a demotion or a switch-off applies on the very next request. Create the first administrator with `python -m scripts.create_staff` (or sign in with `STAFF_PASSWORD`, if also set, which signs in as an administrator). Needed for sign-in with accounts |
| `METRICS_TOKEN` | backend | Optional, 8+ characters. When set, `GET /metrics` needs it as a Bearer token. Unset leaves the counters open (they hold counts only) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `NOTIFY_CHANNEL` | backend | Optional. Send messages and reminders straight through a Twilio account: all three of the first set together, and `NOTIFY_CHANNEL` is `sms` (default) or `whatsapp` (then `TWILIO_FROM` is your approved WhatsApp sender). Takes precedence over the webhook. Unset sends nothing by itself |
| `NOTIFY_WEBHOOK_URL`, `NOTIFY_WEBHOOK_TOKEN` | backend | Optional. Where messages to patients are POSTed as `{to, body, kind}` JSON (an SMS or WhatsApp gateway, or a relay in front of one), with the token as a Bearer header. Unset (the default) sends nothing: the messages wait on the Messages page for reception to phone through |
| `AUTH_TOKEN_TTL_HOURS` | backend | How long a sign-in lasts (default 12) |
| `OFFER_SWEEP_INTERVAL_S` | backend | How often lapsed waitlist offers are passed to the next patient (default 30; 0 turns the sweep off) |
| `RATE_LIMIT_PER_MINUTE` | backend | Requests per minute from one client address before `429 RATE_LIMITED` (default 600; 0 turns it off) |
| `SEED_ANCHOR_DATE` | seed | `YYYY-MM-DD` (India date) the seed scenarios are built around; default today |
| `TEST_DATABASE_URL` | tests | Test database; default `postgresql+psycopg://clinic:clinic@localhost:5433/clinic_test`, created on demand |
| `PORT` | backend (Render) | Listening port, default 8000 |
| `VITE_API_BASE_URL` | frontend | API location, default `http://localhost:8000/api/v1`. Inlined when the UI is **built** |

## 5a. Deployment

How the hosted instance is deployed (**steps marked manual are done in a provider dashboard**; the
configuration they use is committed). The order matters: the API needs the UI's origin for CORS and
the UI needs the API's address.

1. **GitHub (manual).** Create the repository and push `main`. The workflow in
   `.github/workflows/ci.yml` runs on every push: lint, types, a migration round trip, the tests
   with the coverage gate, the UI build, a compose smoke test with the burst script, and a secret
   scan.
2. **Neon (manual).** Create a project and copy the **direct** connection string with
   `sslmode=require`. From a laptop with that string in `DATABASE_URL`, run
   `python -m scripts.migrate_and_seed --reset` inside `backend/`. This creates the schema and the
   seed data in one step.
3. **Render (manual).** New, Blueprint, pick the repository: `render.yaml` defines the service
   (`backend/Dockerfile`, free plan, region Singapore, health check `/healthz`). In the dashboard enter
   `DATABASE_URL` (secret) and a temporary `CORS_ORIGINS=http://localhost:5173`. The container runs
   `python -m scripts.migrate_and_seed --if-empty`, then uvicorn, so a restart never duplicates data.
   Check `/healthz`, `/readyz` and `/docs`.
4. **Vercel (manual).** Import the repository, root directory `frontend`, framework Vite, and set
   `VITE_API_BASE_URL=https://<service>.onrender.com/api/v1`. `frontend/vercel.json` provides the
   single-page-app fallback.
5. **Render again (manual).** Set `CORS_ORIGINS=https://<project>.vercel.app` and redeploy.
   Vercel preview deployments use other origins and will be refused by CORS.
6. **Smoke.** Open the UI, check the clock bar, make one booking, and run
   `python backend/scripts/burst.py --base-url https://<service>.onrender.com`.

**Redeploy after a change:** push to `main`; Render and Vercel build automatically. A new
`VITE_API_BASE_URL` needs a UI redeploy. **Re-seed:** `python -m scripts.migrate_and_seed --reset`
from a laptop with the direct Neon string (Render's free plan has no shell). Do it on the morning of
the review, because the flags in the seed data are relative to the date.

## 6. Running tests and coverage

```bash
docker compose up -d db                      # the integration and API tests need PostgreSQL
cd backend && python scripts/run_tests.py    # all backend tests + coverage; writes ../coverage.txt
cd frontend && npm test -- --run             # all UI tests
```

`run_tests.py` exits non-zero if a test fails or if line coverage of the rules layer
(`app/domain` + `app/services`) is under 80 %. The committed report is [coverage.txt](coverage.txt).

| Measured on the last run | Result |
|---|---|
| Backend tests | 1,450 passing in about 10 minutes (unit tests without a database, integration and race tests on real PostgreSQL, and tests through HTTP) |
| Backend line and branch coverage, all of `app/` | 99 % (4,586 statements, 13 missed, branches included) |
| Rules layer (`app/domain` + `app/services`) | 99 % (2,304 statements, 1 missed; 3 branches partly covered); the gate is 80 % |
| Frontend tests (Vitest, network faked at `fetch`) | 222 passing; 91.2 % of lines, 82.4 % of branches covered (gate: 85 % lines, 75 % branches) |
| Browser end-to-end (real Chrome against the compose stack, `npm run e2e`) | 26 flow checks and 24 accessibility scans (axe-core, desktop and phone) |

**What is covered.** Every rule has fast unit tests with a boundary test for each number: the
2-hour cancel line (2h00m00s is normal, 1h59m59s is late), the 30-day look-back (inclusive, and one
second later is out), the 60-day horizon across month, year and leap-day boundaries, the daily cap,
window edges, the grid and a start with seconds. A Hypothesis test compares `free_slots` and
`first_violation` with an independently written oracle on every minute of random days, and a
mutation run (ten deliberate bugs, for example an exclusive look-back) is caught by the tests.
Integration tests run the services against real PostgreSQL, including races between real
connections: ten bookings of one slot give exactly one success, a cap of three holds against ten
simultaneous bookings, a booking racing a leave day always has one winner, and a real deadlock is
retried. 388 tests go through HTTP: every error code, hostile input (bad JSON, NaN, huge or
deeply nested bodies, ids out of range, year 1 and 9999, control characters, wrong methods, bad test
clocks), CORS and request ids, and logging without personal data. A test runs the burst script
against a real uvicorn socket. The schema is tested constraint by constraint, and an
import-scanning test keeps `domain/` free of frameworks.

**What is deliberately not covered.** Browsers other than Chrome, real SMS or email (none is sent), and load beyond a handful of simultaneous connections. The database-down and
deadlock paths are exercised with real failures where possible and with stand-ins for the driver's
errors where not. [Schemathesis](https://schemathesis.readthedocs.io/) 4.31 runs in CI (the `fuzz` job)
against the running containers with the rate limit off: all 59 operations in the
last local run, no server error. The browser checks in `frontend/e2e/` run in CI too (the
`compose-smoke` job): they book through the real form, race a stale page, triple-click Book, check the
deposit gate and the emergency warning, load every page at phone width, and scan every page with axe-core. The few lines `coverage.txt` lists as missed are defensive branches.

## 7. API overview

Base path `/api/v1`; interactive documentation at `/docs` and the schema at `/openapi.json`. Every
timestamp is returned twice, `..._utc` and `..._ist`.

| Method | Path | Purpose | Main error codes |
|---|---|---|---|
| GET | `/healthz` (root) | Liveness, never touches the database | |
| GET | `/readyz` (root) | The database answers | 503 `SERVICE_UNAVAILABLE` |
| GET | `/clock` | Effective "now", test-clock status, seed dates | 400 `INVALID_TEST_CLOCK` |
| GET | `/auth/status` | Does this server ask for a sign-in, and with individual accounts? (open) | |
| POST | `/auth/login` | A username and password (individual accounts) or a name and the shared staff password; returns a signed Bearer token and the role; 10 tries a minute per client (open) | 401 `UNAUTHENTICATED`, 429 |
| GET, POST | `/doctors` | List, create | 422 |
| DELETE | `/doctors/{id}` | Remove a doctor with no appointments on record | 404, 409 `DOCTOR_HAS_APPOINTMENTS` |
| GET, PATCH | `/doctors/{id}` | Read; change name, speciality, cap, slot length, `accepting_bookings` | 404, 409 `SLOT_LENGTH_LOCKED` |
| GET, PUT | `/doctors/{id}/weekly-windows` | Weekly pattern (replace) | 409 `AVAILABILITY_CONFLICTS`, 422 `WINDOW_OVERLAP`, `WINDOW_OFF_GRID` |
| GET | `/doctors/{id}/overrides?from&to` | Date overrides in a range (at most 90 days) | 422 |
| PUT, DELETE | `/doctors/{id}/overrides/{date}` | Leave, special hours or an extra day; remove | 409 `AVAILABILITY_CONFLICTS`, 422 |
| GET | `/doctors/{id}/slots?date&patient_id?&slots?` | Free starts for a visit of `slots` slots (1 to 4, default 1), with `unavailable_reason` | 404, 422 |
| GET | `/doctors/{id}/schedule?date&patient_id?` | Every grid slot of a day with its state | 404, 422 |
| GET, POST | `/patients` | Search by phone or name prefix; register (`allow_duplicate` despite a likely duplicate) | 409 `PHONE_TAKEN` (only the owner's id), `POSSIBLE_DUPLICATE`, 422 |
| POST | `/patients/{id}/consent` | Record that the privacy notice was accepted, by the patient or (`consent_by: GUARDIAN`, required for under 18s) a parent or guardian; `consent: true` on registration does the same | 404, 409 `PATIENT_ERASED`, 422 |
| POST | `/patients/{id}/erase` | **Admin.** Erase a patient's personal data on request: name, phone, date of birth and visit reasons are replaced; appointments stay as anonymous history; repeating it changes nothing | 409 `PATIENT_HAS_UPCOMING` |
| GET, PATCH | `/patients/{id}` | Patient with the deposit status and a literal `deposit_required` flag; correct name, phone or date of birth | 404, 409 `PHONE_TAKEN`, `POSSIBLE_DUPLICATE` |
| GET | `/patients/{id}/export` | Everything held about a patient: details, every appointment and its history | 404 |
| GET | `/patients/{id}/appointments` | History, newest first | 404 |
| GET | `/appointments` | List with filters, including `needs_attention` | 422 |
| POST | `/appointments` | Book. Send `Idempotency-Key` when retrying: the retry returns the original (200, `Idempotent-Replay: true`) | 404, 409 `IDEMPOTENCY_KEY_REUSED`, `DOCTOR_NOT_ACCEPTING`, 409 `SLOT_TAKEN`, `PATIENT_OVERLAP`, `DAILY_CAP_REACHED`; 422 `BOOKING_IN_PAST`, `BOOKING_TOO_FAR`, `OFF_GRID`, `OUTSIDE_AVAILABILITY`, `DEPOSIT_REQUIRED` |
| GET | `/appointments/{id}` | One appointment, with `allowed_actions` and `needs_attention` | 404 |
| GET | `/appointments/{id}/calendar.ics`, `/patients/{id}/calendar.ics` | Download an appointment, or a patient's upcoming ones, as an iCalendar file | 404 |
| POST | `/appointments/recurring` | Book a series (every 1 to 60 days, 2 to 12 appointments), all or none; `details.occurrence` says which one failed | 409 `SLOT_TAKEN`, 422 as for a booking |
| POST | `/appointments/{id}/cancel` | Cancel (patient or clinic); after the start a patient cancel is a late cancel | 409 `INVALID_TRANSITION` |
| POST | `/appointments/{id}/reschedule` | Cancel and rebook atomically (before the start only). `by` is `PATIENT` (default) or `CLINIC`; a patient move inside 2 hours needs `acknowledge_late` | 409 `APPOINTMENT_ALREADY_STARTED`, `LATE_RESCHEDULE_NEEDS_CONFIRMATION`, 422 `RESCHEDULE_NO_CHANGE`, `DEPOSIT_REQUIRED` |
| POST | `/appointments/{id}/complete`, `/no-show` | Mark after the start | 409 `TOO_EARLY_TO_MARK`, `INVALID_TRANSITION` |
| POST | `/appointments/{id}/confirmed-by-phone` | Reception rang the patient and they confirmed (recorded once; feeds the Calls page) | 404, 409 `INVALID_TRANSITION` |
| POST | `/appointments/{id}/check-in` | Patient arrived (on the day; repeating it changes nothing) | 409 `TOO_EARLY_TO_MARK`, `INVALID_TRANSITION` |
| POST | `/appointments/{id}/correct` | Fix a wrong outcome: completed and no-show swap, a late cancel is waived; a note is required | 409 `INVALID_CORRECTION` |
| — | `If-Match` on cancel, reschedule, complete, no-show, check-in, confirmed-by-phone and correct | Optional. Send the appointment's `etag` (also the `ETag` header of `GET /appointments/{id}`); if it changed since, nothing is done | 412 `PRECONDITION_FAILED`, `details.current_etag` |
| POST | `/appointments/{id}/undo-cancel` | Take back a cancellation made in the last 10 minutes, before the visit starts; every booking rule is checked again | 409 `UNDO_NOT_POSSIBLE`, `SLOT_TAKEN`, `DAILY_CAP_REACHED`, `PATIENT_OVERLAP` |
| GET | `/appointments/{id}/history` | Audit trail, oldest first | 404 |
| GET | `/queue?date&doctor_id&include_cancelled` | One day's queue in time order | 422 |
| POST, GET | `/doctors/{id}/waitlist` | Join the waitlist for a doctor and India date; list who is waiting or holds an offer (`?date`) | 409 `ALREADY_WAITING`, 422 `BOOKING_IN_PAST`, `BOOKING_TOO_FAR` |
| GET | `/patients/{id}/waitlist` | A patient's live waitlist entries, with any open offer | 404 |
| DELETE | `/waitlist/{id}` | Leave the waitlist | 404 `WAITLIST_ENTRY_NOT_FOUND`, 409 |
| POST | `/waitlist/{id}/decline` | Say no to an offer but keep the place; the slot goes to the next patient | 404, 409 `INVALID_TRANSITION` |
| POST | `/waitlist/{id}/accept` | Turn an offer into a booking, with every rule checked | 409 `OFFER_EXPIRED`, `SLOT_TAKEN`, 422 `DEPOSIT_REQUIRED` |
| GET | `/alternatives?doctor_id&date&patient_id?&slots?&limit?` | The nearest bookable times when a day has none: the same doctor's next days first, then other doctors (same speciality first); every option passed the booking rules for this patient and length | 404, 422 |
| GET | `/reports/summary.csv?from&to` | The same report as a CSV file (names that look like formulas are quoted) | 422 |
| GET | `/reports/trends?from&to&doctor_id?` | A row per day (visits, completed, no-shows, cancelled, still booked), no-show rates by weekday and by hour, and the no-show rate of reminded patients against the rest (at most 92 days) | 422 |
| GET | `/reports/trends.csv?from&to&doctor_id?` | The per-day series as a CSV file | 422 |
| GET | `/reports/summary?from&to` | Per doctor: appointments, outcomes, rates, utilisation, and freed / refilled / refilled-by-waitlist slots with a recovery rate (at most 92 days) | 422 |
| GET | `/policy` | The clinic's own rules (booking horizon, late-cancel window, strike count and look-back, undo window, waitlist hold, reminder hours), their defaults and allowed ranges | |
| PATCH | `/policy` | **Admin.** Change any of those rules; each has a range, nothing applies retroactively | 422 `VALIDATION_ERROR` |
| GET | `/notifications/delivery` | How messages leave the clinic (Twilio, a webhook, or by hand), the reminder times and the counts | |
| POST | `/notifications/reminders/run` | **Admin.** Queue the reminders due now (the server does this every 30 seconds on the real clock; this honours the test clock) | |
| GET | `/notifications?status=`, `/notifications/pending` | Messages the system wrote for patients, and how many still need sending | 422 |
| POST | `/notifications/{id}/sent` | Reception phoned or messaged the patient: mark it sent | 404 `NOTIFICATION_NOT_FOUND`, 409 |
| POST | `/staff/{id}/reset-code` | **Admin.** A single-use code (valid an hour, stored only as a hash) so a person can choose a new password | 404 `STAFF_NOT_FOUND` |
| POST | `/auth/reset-password`, `/auth/change-password` | Choose a new password with a reset code, or change your own with the current one; both end the account's older sessions. Five wrong codes lock the account's resets for 15 minutes | 401, 429 |
| GET, POST, PATCH | `/staff`, `/staff/{id}` | **Admin.** List, create and change staff accounts (role ADMIN, RECEPTIONIST or DOCTOR, a doctor's login names its doctor; switch off, set a password); never returns a hash | 409 `STAFF_USERNAME_TAKEN`, `LAST_ADMIN`, 404 `STAFF_NOT_FOUND` |
| GET | `/diagnostics/audit` | **Admin.** Recompute the audit hash chain in the database and list any event that no longer matches | |
| POST | `/diagnostics/proof` | Run the rule scenarios through the real services and database inside a transaction that is always rolled back; returns each scenario's expected and observed result and the row counts before and after | |
| POST | `/triage` | Does a text describe symptoms that may need emergency care? (a hint for the form, never a block) | 422 |

Lists are paginated (`limit` 1 to 100, default 20; `offset` 0 to 100,000) and return
`{items, total, limit, offset}`. The only unpaginated lists are bounded by construction.

**API conventions.** Collections and things are resources (`/patients`, `/appointments/{id}`) with
`GET`, `POST`, `PATCH` and `DELETE` as usual. A change of state that is more than an edit is a
named action under the resource: `cancel`, `reschedule`, `complete`, `no-show`, `check-in`, `correct`,
`accept`, `decline`. These are commands with rules, side effects (a waitlist offer, a strike) and
their own errors, which a `PATCH` of `status` could not express safely. They are `POST` because they
are not idempotent. Every list is paginated and returns `{items, total, limit, offset}`; every failure
has the one error shape in section 9; every instant is returned as `..._utc` and `..._ist`;
`/diagnostics/*` is for operators and is not part of the clinic workflow.

## 8. Business rules and assumptions

| Rule from the problem | Enforced in | Tests |
|---|---|---|
| 1. Inside the doctor's availability, on the 15 or 30 minute grid | `domain/availability.py` (`resolve_windows`, `fits_in_windows`), `domain/slots.py` (`is_on_grid`, `first_violation`) | `unit/test_availability.py`, `unit/test_slots.py`, `unit/test_property_slots.py`, `integration/test_booking_service.py` |
| 2. A doctor never has two overlapping appointments, even concurrently | DB constraint `no_doctor_overlap`; `first_violation`; the doctor-row lock in `services/booking_service.py` | `integration/test_db_constraints.py`, `integration/test_booking_races.py`, `api/test_live_burst.py` |
| 3. A patient never has two overlapping appointments (with any doctor) | DB constraint `no_patient_overlap`; `first_violation`; doctor-then-patient lock order | `integration/test_booking_service.py`, `integration/test_booking_races.py` |
| 4. Daily cap per doctor; cancelled appointments do not count | `first_violation`; the doctor-row lock | `unit/test_slots.py`, `integration/test_booking_service.py`, `integration/test_booking_races.py` |
| 5. Cancel 2 or more hours ahead is normal, later is a late cancel; 2 late cancels or no-shows in 30 days flag the patient and a deposit must be acknowledged | `domain/cancellation.py`, `domain/penalties.py`, `services/booking_service.py`; DB CHECK `appt_deposit_ack` | `unit/test_cancellation.py`, `unit/test_penalties.py`, `unit/test_property_slots.py`, `integration/test_booking_service.py` |
| 6. Reschedule is atomic | `BookingService.reschedule`: lock, cancel the old one, validate and insert the new one, link, in one transaction | `integration/test_booking_service.py` (reschedule tests), `integration/test_booking_races.py` |
| 7. Not in the past, at most 60 days ahead | `domain/booking_window.py` | `unit/test_booking_window.py`, `unit/test_slots.py` |

The order of checks is fixed: past or too far, off the grid, outside availability, daily cap, doctor
overlap, patient overlap, then the deposit. Offering a slot and accepting a booking use the same
function, so the UI cannot offer what the API then refuses.

**Concurrency.** Overlaps are blocked by `EXCLUDE USING gist` constraints. A count cannot be a
constraint, so every booking first takes `SELECT ... FOR UPDATE` on the doctor row, then the patient
row (a fixed lock order: appointment, then doctors by id, then patient). Availability changes take
the same doctor lock, so a booking and a change to the hours run one after the other. A deadlock is
retried once, then answered with 503. In an experiment without the doctor lock, ten simultaneous
bookings all got through a cap of three, and 285 of 760 losers of a same-slot race got a deadlock;
with the lock exactly three got through and none deadlocked. The race tests here fail if the lock is
removed.

### Assumptions

Every ambiguity I resolved, as a numbered assumption. The five that could most reasonably be read
the other way are A-05, A-08, A-10, A-12 and A-16.

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
| A-20 | A single clinic. Sign-in is required unless `ALLOW_OPEN_ACCESS` is set (A-53, A-62) |
| A-21 | A "day" for the cap is the India calendar date of the start |
| A-22 | The trailing 30 days are the closed interval from now minus 30 x 24 hours to now |
| A-27 | `needs_attention` means: booked, starting at or after now, and outside the doctor's effective windows. It is stored as `appointments.outside_hours`, refreshed in the same transaction as any change to hours, and a test checks it against the rule (A-67) |
| A-28 | Rescheduling to the same doctor and the same start is refused (`RESCHEDULE_NO_CHANGE`) so a no-op cannot create a strike |
| A-30 | Instants, including `X-Test-Clock`, are ISO 8601 text with an explicit offset between 2000 and 2099; an empty header, a malformed one, or any header while the clock is disabled is an error, never ignored |
| A-41 | The waitlist is per doctor and India date, first come first served. A cancellation or reschedule offers the freed slot to the first waiting patient who could actually book it (same check as a booking); the offer lasts 30 minutes or until the slot starts, is not a reservation, and accepting it is an ordinary booking (the deposit rule applies, and a lost race returns the patient to the queue) |
| A-42 | A recurring series keeps the same India time of day, books all occurrences in one transaction, and checks each exactly as a single booking; if one fails none is booked |

These 27 are the readings of the brief that change what the system does. The numbers are
stable, so some are missing here: the other 41 (design choices, API conventions and the features beyond the brief) are in
[docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md), which holds all 68.

## 9. Error handling and logging

**One response shape for every failure** (rule violations, bad input, an unknown route, a wrong method,
an oversized body, a database that is down and the catch-all 500):

```json
{"error": {"code": "SLOT_TAKEN", "message": "...", "details": {"same_patient": false}, "request_id": "..."}}
```

| Kind | Where it starts | Becomes |
|---|---|---|
| Bad input (types, bounds, unknown fields) | Pydantic schemas, the body guard | 400 `MALFORMED_JSON`, 413 `PAYLOAD_TOO_LARGE`, 422 `VALIDATION_ERROR` with the fields listed and **never the submitted value** |
| Rule violation or conflict | `domain/` raises `RuleViolation` or `ConflictError` with a code | 422 or 409; `NotFoundError` is 404 |
| Constraint the checks missed (a race) | PostgreSQL SQLSTATE and constraint name, mapped in `persistence/db_errors.py` | The same 409 or 422 the pre-check would have given |
| Database busy or down, lock timeout, deadlock after one retry | `OperationalError`, pool timeout | 503 `SERVICE_UNAVAILABLE` with `Retry-After: 1` |
| A client sending too many requests | In-memory sliding window per address | 429 `RATE_LIMITED` with `Retry-After` |
| Anything else | Any other exception | 500 `INTERNAL_ERROR` with a generic message and the request id; the stack trace is logged, never sent |

All 51 codes are in `backend/app/domain/errors.py` and `backend/app/api/errors.py`. Every write runs
in one transaction, so a failure leaves the data as it was.

**Logging.** structlog writes one JSON line per event to stdout: `ts` (UTC), `level`, `event` and the
`request_id`, which is also returned in the `X-Request-ID` header and in every error body. A
caller's id is accepted only if it matches `[A-Za-z0-9._-]{1,64}`, otherwise a new one is made.

| Level | Event | When | Fields (never a patient's name, phone, date of birth or reason) |
|---|---|---|---|
| info | `request` | Every response except `/healthz` and `/metrics` (those are debug) | method, path, status, `duration_ms`, domain ids, `effective_now` only with the test clock |
| info | `appointment.booked`, `.replayed`, `.series_booked`, `.cancelled`, `.rescheduled`, `.completed`, `.no_show`, `.checked_in`, `.corrected` | A change to an appointment committed | appointment, doctor and patient ids and the outcome, such as whether a cancellation was late |
| info | `patient.created`, `patient.updated`, `doctor.created`, `.updated`, `.deleted` | A directory change | the id and the names of the fields changed, not their values |
| info | `availability.changed` | Weekly hours or an override changed | doctor id, kind, date, whether the change was acknowledged, how many bookings it left needing attention |
| info | `waitlist.joined`, `.offered`, `.accepted`, `.declined`, `.left`, `.swept` | The waitlist moved | entry id, and doctor and patient ids where known |
| info | `auth.login` | A staff sign-in | the staff display name (an operator, not a patient; it is also the audit actor), never the password |
| info | `request.refused` | Bad input refused at the edge (malformed JSON, validation, 404, 405, 413, 429) | code, status |
| warning | `request.rejected` | A rule violation, or a database constraint mapped to a rule | code, status, ids |
| warning | `auth.login_failed` | A wrong staff password | none beyond the request id |
| error | `request.failed` | An unhandled exception (the stack trace is logged here, never sent) | error type |
| error | `database.unavailable`, `database.error`, `database.not_ready`, `waitlist.sweep_failed` | The database or a background task failed | error type |
| debug | `request` for `/healthz` and `/metrics` | Probes | as `request` |

`tests/api/test_headers_and_health.py` enforces the last column: one test runs a full session of writes
with recognisable names, phones and reasons and fails if any of them appears in any log line.

**Metrics.** `GET /metrics` (root, Prometheus text format) gives request counts by method and status,
rejections by error code and total request time. It holds no paths, ids or personal data, so it can be
read without the host's dashboard; the counters are per process and reset on restart.

[docs/sample-logs.jsonl](docs/sample-logs.jsonl) holds real lines from a scripted run (a booking, a
double click, a booking in the past, a flagged patient, a late cancellation, malformed JSON). **On
the hosted instance** the logs are in the Render dashboard, Logs tab (owner access). There is
deliberately no public log endpoint, because on a deployed instance it would look like a debug
endpoint; `/metrics` is the public, privacy-safe view.

## 10. Reviewer aids

**Test clock.** With `TEST_CLOCK_ENABLED=true` (set on the hosted instance), a request may carry
`X-Test-Clock: 2026-10-19T09:30:00+05:30`: that instant is "now" for that request only, for the
booking window, the cancellation rule and the deposit look-back. The response echoes
`X-Effective-Now`. A malformed, empty or repeated header, or any header while the clock is disabled,
is a 400, so a clock is never silently ignored. In the UI, the header bar has a time box (India
time), **Set clock**, **Seed day 09:30** and **Use the real time**, and shows an amber
**TEST CLOCK ACTIVE** badge. `GET /api/v1/clock` shows what the server is using.

```bash
curl -s localhost:8000/api/v1/queue -H "X-Test-Clock: 2026-10-19T09:30:00+05:30"
# the 11:15 appointment is 1h45m away: cancelling it now is a late cancel; 11:30 is exactly 2h away: a normal cancel
```

**Re-seed.** `cd backend && python -m scripts.migrate_and_seed --reset` (add `--print-scenarios` to see
the dates). With compose: `docker compose exec backend python -m scripts.migrate_and_seed --reset`.
Fifteen invented patients and about 45 appointments. The scenarios, for an anchor date of Saturday
2026-10-17 (they move with the anchor):

| Scenario | State | Try |
|---|---|---|
| Today's queue | Mon 2026-10-19: 8 appointments for Dr. Rao | Set the clock to the seed day 09:30: 09:00 and 09:15 can be marked completed or no-show |
| Extra Saturday | Sat 2026-10-24: Dr. Menon works 10:00-13:00 (override) | Book it; remove the override |
| Conflict demo | Tue 2026-10-20: Dr. Rao has 3 bookings | `PUT` a leave override: 409 with the patients; acknowledge to see `needs_attention` |
| Leave day with orphan | Wed 2026-10-28: Dr. Rao on leave, 1 booking inside it | The "needs attention" list and the day view heading |
| Cap demo | Fri 2026-10-23: Dr. Menon, cap 6, 5 booked, 3 slots free | One more booking works, the next gives `DAILY_CAP_REACHED` |
| Cross-doctor overlap | Arjun Mehta has Dr. Rao at 10:00 on Mon 2026-10-19 | Book him with Dr. Menon at 10:00: `PATIENT_OVERLAP` |
| Flagged patient | Kavita Nair +919000000001, flagged through 2026-11-11 | `DEPOSIT_REQUIRED` with the reasons, then book with the acknowledgement |
| One strike | Rohan Gupta +919000000002 | Not flagged; mark one more no-show |
| Expiring flag | Sneha Pillai +919000000003, flagged through 2026-10-18 | Set the clock to 2026-10-19: no longer flagged |

**Burst.** `python backend/scripts/burst.py --base-url http://localhost:8000 --requests 20` sends
20 simultaneous bookings of one slot: exactly one 201, nineteen `SLOT_TAKEN`, no 5xx.

**Fuzz.** `pip install schemathesis`, then
`st run http://localhost:8000/openapi.json --checks not_a_server_error`.

## 11. Known limitations

What is left after the work in sections 8 to 10, and why. Items the assignment asks for are not
limitations; items it makes optional or leaves out are.

- **Sign-in is required by default** and can be switched off only with `ALLOW_OPEN_ACCESS=true`,
  because the assignment makes authentication optional and a login could lock out a reviewer; a
  server left open says so on every page. When sign-in is on, it can be one shared password (`STAFF_PASSWORD`)
  or individual accounts with three roles (`AUTH_SECRET`): administrator, receptionist and doctor
  (who sees the schedule and marks only their own visits). A forgotten password is handled by an
  administrator issuing a single-use code, not by email. Not built: reset by email, two-factor
  sign-in. While sign-in is off any caller can read patient names
  and phones.
- **The hosted test clock is switched on on purpose.** The assignment requires a way for a reviewer
  to set "now"; that also lets any caller send `X-Test-Clock` and book in the past or skip the 60-day
  window. After the review set `TEST_CLOCK_ENABLED=false` in the Render dashboard.
- **Messages need a gateway account.** The outbox, the consent gate, the retries, the Twilio (SMS or
  WhatsApp) sender and the webhook are built and tested against a local stand-in for Twilio, but
  this project has no account: sending for real needs the clinic's own (WhatsApp business messages
  also need pre-approved templates). With no gateway configured, messages and reminders wait on the
  Messages page for reception to send by hand.
- **Reminders** are queued once per visit and kind (24 hours and 2 hours before by default, set in
  Clinic rules), only when they still make sense, and withdrawn when the visit is cancelled or
  moved. Not built: delivery receipts from the gateway, patient replies ("reply 1 to confirm"), and
  templates in other languages. Reception can also ring tomorrow's patients from the **Calls** page and
  record each call. Payments, a patient portal and multi-location are not built (not in the brief).
- **Cold start.** Render's free plan sleeps when idle. A scheduled workflow (`keepalive.yml`) pings
  `/healthz` every 10 minutes to prevent that; GitHub may pause scheduled workflows on a repository
  with no activity for 60 days, and a paid plan is the real fix.
- **The rate limit is in memory**, so with several instances each counts on its own. The hosted
  setup is one instance. A shared limit would need Redis or a database table.
- **Tamper-evident, not tamper-proof.** The audit trail is append-only in the database and
  hash-chained per appointment (A-68). A cancelled appointment cannot be restored; an outcome can be
  corrected with a note.
- **Scope the assignment does not ask for:** one clinic and India Standard Time; no branches, rooms
  or equipment; no appointment types with their own durations (a visit can last one to four of the
  doctor's slots, A-04); no guardian model (one phone, one patient, A-15); no payments, so the
  deposit is an acknowledgement.
- **Accessibility** is checked by axe-core on every page (desktop and phone) and by
  hand for keyboard use, plus tests for the skip link, page titles and focus on navigation. It has **not** been audited by a person who uses a screen
  reader; that cannot be done by the author or by software and is the one item here that stays open.
- **Privacy.** Consent can be recorded and a patient's data erased on request or by a retention
  purge (`python -m scripts.purge_inactive`, dry run by default); `GET /patients/{id}/export` is the
  access half. Logs hold ids and codes, never names, phones or reasons (a test enforces it); every
  response is `no-store` with `nosniff`, `no-referrer`, HSTS and a CSP. A child's consent must come from a
  parent or guardian (recorded, not verified), and the consent record survives erasure. See
  [docs/PRIVACY-AND-OPERATIONS.md](docs/PRIVACY-AND-OPERATIONS.md) for the breach procedure,
  backups and alerts. A real deployment would still
  need a written privacy notice, a retention period chosen by the clinic (the default of three years
  is a placeholder), a data processing agreement with Neon, Render and any message gateway, and
  legal review; this is engineering support for the Digital Personal Data Protection Act, not
  advice.
- **Load.** `python scripts/load.py --users 100` mixes reads, bookings and cancels from 100
  simultaneous users: no server error and no double booking, but at 100 users on a laptop the median
  request takes about two seconds because the pool holds ten connections. A test runs 60 users in
  the suite. Raise `DB_POOL_SIZE` for more, within what the database allows; no test goes past 100
  users.
- **The rule proof** (`POST /diagnostics/proof`) is administrator-only when sign-in is on; when it is
  off anyone can call it. It keeps nothing, but each run holds a database connection for a few
  seconds and burns sequence ids.
- The seed data is relative to the date it was created on: the flags drift as days pass, which is why
  there is a "Seed day" clock preset and a re-seed command.
- `Idempotency-Key` applies to single bookings only. Repeating a cancel or a reschedule is safe
  without one: the second attempt gets a conflict (`INVALID_TRANSITION` or `RESCHEDULE_NO_CHANGE`),
  never a second effect. Without a key a double-clicked booking is caught by the overlap check
  (`same_patient: true`).

## 12. AI and third-party usage

**AI assistant.** Claude Code (Anthropic) was used throughout and wrote most of the repository: the
plan, the experiments that tested the design (concurrency, schema, hostile input), the domain rules,
the services, the API, the React application, the tests, the container and CI configuration and the
documentation. The rules come from the problem statement; the interpretations and decisions are
recorded as assumptions in [section 8](#8-business-rules-and-assumptions) and in
[docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md). The assignment suggests writing the business rules by
hand; here the assistant wrote them from a plan, and the author reviews them and explains each one.

**Prompt log.** Every prompt is in [PROMPTS.md](PROMPTS.md), with what was done with the answer. The
full planning brief is in [docs/prompts/01-planning-brief.md](docs/prompts/01-planning-brief.md).

**Commit authorship.** Every commit is authored by the repository owner (`Hathim0001`) and carries no
AI co-author trailer, so the record of the assistant's work is this section, `PROMPTS.md` and
`SUBMISSION.md`, not the commit metadata.

**Third-party software.** Only what is pinned in `backend/requirements*.txt` and
`frontend/package-lock.json` (FastAPI, SQLAlchemy, Alembic, Pydantic, structlog, psycopg, pytest,
Hypothesis, ruff, mypy, React, Vite, TanStack Query, React Router, Vitest, Testing Library, ESLint),
the official PostgreSQL, Python, Node and nginx images, and the Inter, Playfair Display and JetBrains
Mono typefaces (open licence, bundled). No template or starter project was copied. Names and phone
numbers in the seed data are invented.
