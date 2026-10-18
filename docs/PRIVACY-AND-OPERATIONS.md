# Privacy and operations notes

What a clinic running this would need to decide and do. These are engineering notes for the
Digital Personal Data Protection (DPDP) Act 2023 and Rules 2025, written from law-firm summaries of
the Rules, **not** from the Gazette text and **not** legal advice. Check the current text before
relying on any date or period below.

## What the software does for privacy

| Need | Where | Notes |
|---|---|---|
| Record that the privacy notice was accepted | `consent` on registration, `POST /patients/{id}/consent` | Stores when, which notice version (`CONSENT_VERSION`) and **who** accepted: the patient or, for someone under 18, a parent or guardian |
| A child's consent comes from a guardian | `patient_service._check_consent_by` | Refused with 422 if a child's consent is recorded as the patient's own. The software records *that* a guardian accepted; it does not verify who they are or store their name, and "verifiable" parental consent (the Rules' wording) is a clinic procedure, not something this system can check |
| Access to one's data | `GET /patients/{id}/export` | Administrator only when sign-in is on |
| Erasure on request | `POST /patients/{id}/erase` | Replaces name, phone, date of birth and visit reasons; keeps appointments as anonymous history; **keeps the consent record** (time, notice version, who) because it holds no identity and the Rules are reported to expect consent records to outlive the data. Refused while a booking or waitlist place is upcoming |
| Retention | `python -m scripts.purge_inactive --days N [--apply]` | Dry run unless `--apply`; refuses less than 30 days. The default of three years is a placeholder: the clinic must set its own |
| Messages | The outbox | Not sent to a patient with no recorded consent; erased with the patient |
| Logs | structlog | Ids and codes only; a test fails if a name, phone or reason reaches a log line |

## What is the clinic's job

1. **Write the privacy notice** patients accept, and bump `CONSENT_VERSION` in
   `services/patient_service.py` whenever its wording changes, so the record says which text was
   accepted.
2. **Choose a retention period** and run the purge on a schedule (a Render cron job, or any cron).
   Medical-records law may require keeping clinical records longer than a privacy rule would; this
   needs a decision by someone qualified, and erasing before that decision would be wrong.
3. **Decide how a guardian is verified** (an ID check at the front desk, a signed form) and file that
   evidence outside this system.
4. **Sign data processing agreements** with the hosting providers (Render, Neon, Vercel) and with any
   message gateway.
5. **Tell patients before erasing** if the Rules require advance notice (reported as 48 hours): the
   software does not send that notice.

## Breach procedure (what to do if personal data may have been exposed)

The Rules are reported to require telling the Data Protection Board without delay and giving a
detailed report within 72 hours of becoming aware, and telling the affected people. A plan written
now is worth more than one written during an incident.

1. **Contain.** If a credential leaked, rotate it first: the Neon password (Neon dashboard, then the
   `DATABASE_URL` in Render), `STAFF_PASSWORD` and `AUTH_SECRET` (changing either signs everyone
   out), and the message-gateway token. Set `TEST_CLOCK_ENABLED=false` if it was left on.
2. **Establish what was reached.** The audit trail (`GET /diagnostics/audit` checks it has not been
   altered) and the request logs in the Render dashboard show which ids were read or changed; the
   logs hold ids and codes, never names, so work from ids.
3. **Record the time you became aware.** The 72-hour clock starts then.
4. **Notify**: the Board, then the affected patients, with what happened, what data, what you did
   and who to contact. The clinic's lawyer or data protection adviser should write this.
5. **Fix and review**: close the cause, add a test, and write down what changed.

## Backups, restore and alerts (free-tier reality)

- **Backups.** Neon keeps point-in-time history on its free plan for a limited window (check the
  current limit in its documentation). For a copy the clinic owns, run
  `pg_dump "$DATABASE_URL" --format=custom --file clinic-$(date +%F).dump` from a trusted machine
  on a schedule, store it encrypted, and test a restore with
  `pg_restore --clean --dbname "$SCRATCH_DATABASE_URL" clinic-<date>.dump` into a scratch database.
  Patient data in a dump is still patient data: protect and expire it like the database.
- **Restore order.** Restore the database, then redeploy the API (migrations run at start and are
  idempotent), then check `GET /readyz`, `GET /diagnostics/audit` and the day view.
- **Alerts.** There is no pager. Point any free uptime monitor at `GET /healthz` (process) and
  `GET /readyz` (database), and watch `GET /metrics` for a rising `clinic_rejections_total` or 5xx
  count. Set `METRICS_TOKEN` if `/metrics` should not be public.
- **Staging.** None. Use `docker compose up --build` with a scratch database to try a change; the
  hosted database should only receive migrations that have run there first.
- **Single instance.** The in-memory rate limit and login lockout count per process; a second API
  instance would count separately.
