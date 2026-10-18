# Code tour: explaining this code live

Most of this code was written with an AI assistant (Claude Code); [PROMPTS.md](../PROMPTS.md) logs
the prompts and README section 12 states what was and was not generated. The author's job is to be
able to **explain, change and defend** it. This page is the map for doing that in ten minutes, and a
set of drills with answers you can check by running the tests.

## The one idea to hold on to

A request goes **api → services → (domain, persistence)**. `domain/` is pure Python: no database, no
clock, no web. It decides *whether* something is allowed. `services/` opens one transaction, takes
locks, loads facts, asks the domain, writes. `persistence/` is SQLAlchemy and the PostgreSQL
constraints that have the last word. `api/` is HTTP only. `tests/unit/test_architecture.py` fails the
build if a layer imports from the wrong side.

`now` is always passed in; nothing in `domain/` or `services/` reads the system clock. That is what
makes every time rule testable at its boundary and lets the reviewer's `X-Test-Clock` work.

## Rule to code to test

| Rule from the brief | Decided in | Proven by |
|---|---|---|
| Slot grid, hours, no double booking, cap, patient overlap | `backend/app/domain/slots.py` `first_violation` (fixed order: accepting, window, grid, hours, cap, doctor overlap, patient overlap) | `tests/unit/test_slots.py`, `test_property_slots.py`, `tests/integration/test_booking_service.py` |
| 60-day window, past is strict | `domain/booking_window.py` `check_booking_window` (IST calendar dates) | `tests/unit/test_booking_window.py` |
| Cancel at least 2 h ahead is free, later is late; clinic never late | `domain/cancellation.py` `classify_cancellation` (`LATE_THRESHOLD`) | `tests/unit/test_cancellation.py` |
| Two strikes in 30 days need a deposit acknowledgement; derived, never stored | `domain/penalties.py` `deposit_status` | `tests/unit/test_penalties.py` |
| Status changes (who can do what, when) | `domain/transitions.py` | `tests/unit/test_transitions.py` |
| Phone: Indian mobile, normalised, **unique** | `domain/phone.py`; `UNIQUE (phone)` (`patients_phone_key`: created in 0001, dropped by 0005 for a shared-phone feature, restored by 0006); `services/patient_service.py` `_refuse_taken_phone` | `tests/unit/test_phone.py`, `tests/integration/test_db_constraints.py`, race test `test_ten_simultaneous_registrations_of_one_phone_give_one_patient` |
| Two requests at once cannot both win | `services/booking_service.py` (lock order: appointment, doctors by id, waitlist entry, patient) and `EXCLUDE` constraints in `0001_initial.sql` | `tests/integration/test_booking_races.py` (10 connections) |
| A booking is checked once, in one place | `booking_service.place_booking` calls `first_violation`; `availability_service.free_slots` calls the **same** function, so the UI never offers what booking would refuse | `tests/integration/test_availability_reads.py` |
| Moving an appointment is atomic | `booking_service.reschedule` and its four helpers (`_slots_for_move`, `_cancel_for_move`, `_late_move_question`, `_link_move`) | `tests/integration/test_booking_service.py`, `test_visits_and_late_moves.py`, and the "atomic-move" case on the Proof page |
| A retried request does not double-book | `booking_service.book_idempotent` + `idempotency_keys` | `tests/integration/test_hardening.py` |
| Optional sign-in, two roles, individual accounts | `api/deps.py` `require_staff` (reads the role and active flag from the database each request) and `require_admin`; `services/staff_service.py`; `core/passwords.py` (scrypt); `core/auth.py` (signed token) | `tests/api/test_staff_roles.py`, `tests/unit/test_auth_and_proxy.py` |
| Erase a patient, record consent, retention purge | `services/patient_service.py` `erase`, `record_consent`, `inactive_ids`; `scripts/purge_inactive.py` | `tests/integration/test_privacy.py` |
| A message about every change, never about a rolled-back one | `services/notification_service.py` `queue_message` (called inside the same transaction) and `dispatch` | `tests/integration/test_notifications.py` |
| `needs_attention` without scanning every booking | `appointments.outside_hours`, refreshed by `repo.refresh_outside_hours` in the same transaction as any change to hours; partial index in migration `0008` | `tests/integration/test_stored_attention.py` (stored flag equals the rule after random hour changes) |
| The audit trail shows tampering | Migration `0011`: a trigger hashes each event with the previous one of the same appointment; `verify_audit_chain()` | `tests/integration/test_audit_chain.py` |
| A child's consent comes from a guardian; erasure keeps the consent record | `patient_service._check_consent_by`, `_is_child`, `erase` | `tests/integration/test_privacy.py` (the 18th-birthday boundary is tested) |
| Five wrong passwords lock one account | `api/ratelimit.py` `LoginLockout`, used by `api/routers/auth.py` | `tests/api/test_staff_roles.py`, `tests/unit/test_auth_and_proxy.py` |
| The gateway is never called inside a database transaction | `notification_service._claim`, `_deliver`, `_finish` (a short lease, then send, then record) | `test_the_gateway_is_called_with_no_database_lock_held` |
| Reception confirms by phone | `booking_service.confirm_by_phone`; the Calls page | `tests/integration/test_operations.py`, `frontend/src/pages/Review.test.tsx` |
| Errors are stable codes, never a 500 for bad input | `domain/errors.py` (`ErrorCode`), `api/errors.py`, `persistence/db_errors.py` | `tests/api/test_hostile_input.py`, Schemathesis job in CI |

## Ten-minute read order

1. `backend/app/domain/model.py` and `errors.py`: the vocabulary (statuses, error codes).
2. `domain/slots.py`: the one function that answers "can this be booked?".
3. `domain/cancellation.py`, `penalties.py`, `booking_window.py`: the three time rules, each under 40 lines.
4. `services/booking_service.py`: `place_booking`, `book`, `cancel`, `reschedule`.
5. `persistence/models.py` constraints, then `migrations/versions/0001_*.py`.
6. `api/routers/appointments.py` to see how thin the HTTP layer is.
7. `frontend/src/components/booking/useBookingForm.ts`: the booking page's decisions, with `Book.tsx` as layout only.

## Drills: change it live

Each is small on purpose. Do the change, run the named test, and say why it fails or passes.

1. **"Make the late-cancel threshold 3 hours."** Change `LATE_THRESHOLD` in `domain/cancellation.py`.
   `tests/unit/test_cancellation.py` fails on the 2 h boundary cases, and the Proof page's
   "cancel-boundary" case fails too, which is the point of having it. Nothing else changes: no other
   file holds the number.
2. **"Strikes should last 14 days, not 30."** `LOOKBACK` in `domain/penalties.py`. The repository
   query `penalty_events` reads the same constant, so the SQL narrows with it.
3. **"Allow booking 90 days ahead."** `HORIZON_DAYS` in `domain/booking_window.py`; the waitlist
   imports it, so joining a waitlist follows. The "sixty-days" proof case will fail and must be
   updated, because it asserts the documented 60.
4. **"Three strikes, not two."** `STRIKES` in `penalties.py`. `deposit_status` indexes the
   second-most-recent strike (`recent[STRIKES - 1]`), so `required_until` follows.
5. **"Why is the phone unique in the database *and* in the service?"** The service check gives a
   readable `PHONE_TAKEN` with the owner's id; the constraint is what makes it true when two
   requests arrive together. The race test registers one phone ten times at once and gets one row.
6. **"What stops two people booking the same slot?"** Two layers: the doctor row is locked
   (`SELECT ... FOR UPDATE`) before the check, and the `no_doctor_overlap` constraint (`EXCLUDE USING gist` on
   `doctor_id` and `tstzrange(start_at, end_at)`, active statuses only, in
   `migrations/versions/0001_initial.sql`) rejects an overlap even if a bug skipped the lock;
   `no_patient_overlap` does the same for a patient.
   `test_ten_patients_racing_for_one_slot_give_exactly_one_booking`.
7. **"Add a rule: no bookings on Sundays."** It belongs in availability (a doctor simply has no
   Sunday windows), not in a new check. Show `resolve_windows` in `domain/availability.py`.
8. **"Why is `needs_attention` stored now, when it used to be derived?"** Derived on every read it
   scanned every booking. The stored `outside_hours` flag can only change when a doctor's hours
   change, so it is recomputed in that same transaction (`replace_weekly_windows`, `put_override`,
   `delete_override`). "In the future" is not stored (that would go stale), it is applied when
   reading. The random-sequence test is what lets you trust it.
9. **"What if a receptionist is demoted while signed in?"** The token's role is only a hint; for
   an individual account `require_staff` reloads the account, so the next request is refused with
   `FORBIDDEN`. `test_a_demotion_applies_to_the_token_already_issued`.
10. **"Why does erasure keep the appointments?"** The daily cap, the report and a doctor's
    schedule are made of them. Only what identifies a person is replaced; ids and times stay.
11. **"Where would a new error code go?"** `ErrorCode` in `domain/errors.py`, its status class is
   decided by the sets beneath it, and `frontend/src/lib/errors.ts` gives the text.

## Questions to be ready for

- *Why is deposit status not a column?* A stored flag goes stale when time passes or a status is
  corrected; deriving it from the history needs no job and follows the test clock.
- *Why does the UI list only valid times?* `free_slots` runs the same `first_violation`, so the form
  cannot offer a refusal. The server still re-checks at booking.
- *What is untested?* Real SMS/email, real payments (none exist), browsers other than Chrome, and
  load beyond a handful of concurrent connections.
- *What did the AI get wrong along the way?* the git history shows the corrections; the clearest is the
  shared-phone feature, which the AI proposed to lift a documented limit; it was removed again
  because the brief says phone is unique (migrations 0005 then 0006 record that detour).
