# Clinic Appointment Scheduler

**Problem 2: Clinic Appointment Scheduler** (KJBN Labs software engineering internship take-home).
A booking system for a two-doctor clinic. The backend enforces availability, the slot grid, double
booking, the daily cap, cancellation and deposit rules, including under concurrent requests.

> **Work in progress.** The repository is built in milestones M0 to M6 with one commit per logical
> change. Sections below are filled in as the work lands, and anything marked *not yet* does not
> exist yet. Every AI prompt used is logged in [PROMPTS.md](PROMPTS.md).

## 2. Live links

Not yet deployed (milestone M5).

## 3. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.1 (sync), Alembic, psycopg 3, structlog | Recommended stack for the assignment |
| Database | PostgreSQL 16 | `EXCLUDE USING gist` constraints make overlapping appointments impossible to store |
| Frontend | React, TypeScript, Vite | Not yet |
| Hosting | Render (API), Neon (database), Vercel (UI) | Free tiers; not yet |
| Tests | pytest, pytest-cov, Hypothesis | |

## 4. Architecture

Not yet written (M6). Backend layering: `api` (HTTP only) calls `services` (transactions and locks),
which call `domain` (pure rules, no I/O) and `persistence` (SQLAlchemy models and queries).

| Folder | Purpose |
|---|---|
| `backend/` | The API, its tests, migrations and scripts |
| `docker-compose.yml` | Local services (the database for now) |

## 5. Running locally

Prerequisites: Docker Desktop, Python 3.13, git. Only the database and the unit tests exist so far.

```powershell
docker compose up -d db
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
pytest -m unit
```

```bash
docker compose up -d db && cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && cp .env.example .env
pytest -m unit
```

## 5a. Deployment

Not yet (M5).

## 6. Running tests and coverage

Not yet written (M6).

## 7. API overview

Not yet (M3).

## 8. Business rules and assumptions

Not yet written (M6).

## 9. Error handling and logging

Not yet written (M3 and M6).

## 10. Reviewer aids

Not yet written (M6).

## 11. Known limitations

Not yet written (M6). It will be honest.

## 12. AI and third-party usage

- **Claude Code (Anthropic)** is used throughout this project: for the planning document, for
  experiments that tested the design (concurrency, schema, hostile input), and for writing and
  reviewing code and tests. Commits written with its help carry a `Co-Authored-By: Claude` trailer.
- Every prompt given to it is logged in [PROMPTS.md](PROMPTS.md), with what was done with the answer.
- Third-party libraries are the ones pinned in `backend/requirements*.txt`.
