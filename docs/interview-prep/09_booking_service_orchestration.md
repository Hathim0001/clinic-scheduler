# Backend File Guide: `backend/app/services/booking_service.py`

> **File Path:** [`backend/app/services/booking_service.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/services/booking_service.py)  
> **Topic:** Service Orchestration, Pessimistic Locking, Transactions & Idempotency  
> **Key Methods:** `book()`, `book_idempotent()`, `reschedule()`, `cancel()`, `undo_cancel()`, `correct()`

---

## 1. File Role & High-Level Purpose

If the `domain/` layer is the **brain** (making pure logical decisions), `BookingService` is the **nervous system**.

It coordinates:
1. **Transaction boundaries:** Every public method runs inside exactly one atomic database transaction (`run(self._factory, work)`). If anything fails, everything rolls back.
2. **Pessimistic row locking:** Takes locks using `SELECT ... FOR UPDATE` in a deterministic order to eliminate race conditions and deadlocks.
3. **Domain orchestration:** Loads database rows into frozen dataclasses, passes them to domain predicates like `first_violation()`, and persists the results.
4. **Side effects in-transaction:** Queues patient SMS/messages and writes immutable audit logs within the same database commit.
5. **Idempotency:** Protects against duplicate bookings from double-clicks or network timeouts.

---

## 2. The Golden Locking Hierarchy (Deadlock Prevention)

When booking, moving, or updating appointments, multiple entities must be locked. If Request A locks Doctor 1 then Doctor 2, while Request B locks Doctor 2 then Doctor 1, a **database deadlock** occurs.

To completely prevent deadlocks, `BookingService` enforces a strict, global lock hierarchy:
```
1. Existing Appointment (if updating)
   └── 2. Doctors ordered by ascending ID: doctor_id = 1, then doctor_id = 2
         └── 3. Patient row
```
See lines 376–377:
```python
target_doctor_id = doctor_id if doctor_id is not None else old.doctor_id
doctors = repo.lock_doctors(session, {old.doctor_id, target_doctor_id})
patient = repo.get_patient(session, old.patient_id, lock=True)
```
`lock_doctors()` sorts the IDs before issuing `SELECT ... FOR UPDATE`, guaranteeing that any two concurrent requests always lock doctors in identical sequence.

---

## 3. Key Methods Breakdown

### A. `place_booking(...) -> Appointment` (Lines 58–110)
The core private helper used by `book`, `book_idempotent`, `book_series`, and `reschedule`:
1. Checks that the patient has not been erased (`refuse_erased`).
2. Builds `SlotContext` with today's appointments and working hours.
3. Evaluates `first_violation(start_at, context, slots)`. If violated $\rightarrow$ raises `RuleViolation` or `ConflictError`.
4. Checks deposit requirement: `if deposit.required and not deposit_confirmed: raise DEPOSIT_REQUIRED`.
5. Inserts the `Appointment` row and calls `session.flush()`.
6. Queues a notification message in the outbox table.
7. Writes an audit entry to `appointment_events`.

### B. `book_idempotent(command, key, now) -> (AppointmentView, bool)` (Lines 151–198)
Protects against network retries:
1. Computes a SHA-256 fingerprint of the request payload.
2. Checks the `idempotency_keys` table.
3. If the key exists:
   - Same payload hash $\rightarrow$ Returns existing appointment (`200 OK`, `Idempotent-Replay: true`).
   - Different payload hash $\rightarrow$ Raises `409 IDEMPOTENCY_KEY_REUSED`.
4. If key is new: Books the appointment and stores the key in the same transaction.

### C. `reschedule(...) -> RescheduleResult` (Lines 345–413)
The atomic appointment move:
1. Locks old appointment, doctor(s), and patient.
2. Checks that appointment hasn't started (`check_can_reschedule`).
3. Cancels the old slot (`_cancel_for_move`), freeing up its spot on the schedule.
4. Places the new booking (`place_booking`).
5. **The Late Move Prompt:** If moving within 2 hours, it counts as a late cancellation strike. If `acknowledge_late=false`, it halts and prompts the user.
6. Links `old.rescheduled_to_id = new.id`.
7. Triggers `offer_freed_slot()` to give the old slot to the waitlist immediately!

### D. `cancel(...) -> CancelResult` (Lines 240–279)
1. Classifies cancellation (`classify_cancellation`) based on 2-hour threshold and actor.
2. Updates appointment status to `CANCELLED` or `LATE_CANCELLED`.
3. If cancelled by the clinic, queues an automated cancellation SMS.
4. Calls `offer_freed_slot()` to notify the waitlist.

---

## 4. Interview Pitch (60-Second Explanation)

> *"In `booking_service.py`, we manage transactional consistency and concurrency. Every booking or reschedule runs inside an isolated transaction. To eliminate deadlocks when rescheduling across doctors, we enforce a strict lock order: locking doctors by ascending ID, followed by the patient row. We pass database snapshots to pure domain predicates like `first_violation()` to evaluate rules. All side effects—such as appending to our audit event table, inserting idempotency records, and triggering waitlist offers—commit in that exact same transaction, guaranteeing that notifications and audits never fire for rolled-back operations."*

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why are SMS messages written to a database table instead of calling the SMS API directly inside `booking_service`?**  
  * **A:** Calling an external HTTP API (like Twilio) inside a database transaction is a major architectural anti-pattern. If Twilio takes 5 seconds to respond or times out, your database row locks are held open for 5 seconds, causing connection pool exhaustion and blocking all other patients from booking. Furthermore, if the transaction later rolls back due to a constraint violation, the patient would still receive an SMS saying they were booked! We use the **Transactional Outbox Pattern**: write the message to the `notifications` table in the transaction, and dispatch it asynchronously after the transaction commits.
