# Backend File Guide: `backend/app/domain/transitions.py`

> **File Path:** [`backend/app/domain/transitions.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/transitions.py)  
> **Topic:** The Appointment State Machine, 10-Minute Undo & Outcome Corrections  
> **Key Function:** `allowed_actions(...)`, `can_undo_cancel(...)`, `check_correction(...)`

---

## 1. File Role & High-Level Purpose

An appointment lifecycle is not a free-for-all; it is a **strict finite-state machine (FSM)**. 

This file controls:
1. Which lifecycle transitions are legally permissible given the current status and time.
2. What operational buttons the UI receptionist is allowed to click.
3. The **10-minute undo cancellation** safety window.
4. **Correction rules** for fixing human recording errors (e.g. swapping Completed and No-Show).

---

## 2. Key Functions & Code Breakdown

### A. The 5 Core Statuses
```python
BOOKED -> [CANCELLED, LATE_CANCELLED, COMPLETED, NO_SHOW]
```
* **`BOOKED`:** The initial active state. Only `BOOKED` appointments can be cancelled, rescheduled, checked in, or marked completed/no-show.
* **Final States:** `COMPLETED`, `NO_SHOW`, `CANCELLED`, `LATE_CANCELLED` are terminal, with two exceptions:
  1. A cancellation can be **undone** within 10 minutes.
  2. Recorded outcomes can undergo **controlled correction**.

### B. `allowed_actions(...) -> list[str]` (Lines 57–80)
Determines permitted actions based on time:
* **Before start time (`now < start_at`):**
  - Actions: `["cancel", "reschedule"]`.
  - Plus `"check-in"` if today is the day of the visit.
* **At or after start time (`now >= start_at`):**
  - Actions: `["complete", "no-show", "cancel"]`. Rescheduling is disabled.
* **If already Cancelled:** May include `"undo-cancel"`.
* **If in a Terminal State:** May include `"correct"`.

### C. The 10-Minute Undo Rule: `can_undo_cancel(...)` (Lines 30–47)
Allows a receptionist to immediately reverse an accidental cancellation if:
```python
return (
    status in CANCELLED_STATUSES
    and not rescheduled
    and cancelled_at is not None
    and undo_window > timedelta(0)
    and timedelta(0) <= now - cancelled_at <= undo_window
    and now < start_at
)
```
1. Must be `CANCELLED` or `LATE_CANCELLED`.
2. Must **not** have been cancelled as part of a reschedule (`rescheduled_to_id is None`).
3. Must be requested within **10 minutes** of cancellation (`now - cancelled_at <= 10 min`).
4. Appointment must not have started yet (`now < start_at`).
5. *Service-level check:* The slot must not have been given away to the waitlist, and must still be free.

### D. Outcome Corrections: `CORRECTIONS` (Lines 49–55)
Allows reception staff to rectify mistakes without corrupting audit history:
```python
CORRECTIONS = {
    Status.COMPLETED: frozenset({Status.NO_SHOW}),
    Status.NO_SHOW: frozenset({Status.COMPLETED}),
    Status.LATE_CANCELLED: frozenset({Status.CANCELLED}),
}
```
* **Swapping outcomes:** If staff clicked "No-Show" but the patient was actually waiting in the room, it can be corrected to `COMPLETED` (and vice-versa).
* **Waiving a penalty:** A manager can forgive a `LATE_CANCELLED` penalty and change it to `CANCELLED`.
* **Note required:** Every correction requires a mandatory reason note and writes a new audit entry.

---

## 3. Interview Pitch (60-Second Explanation)

> *"In `transitions.py`, we implement a strict finite-state machine governing appointment lifecycles. Only `BOOKED` appointments can transition: before the start time they can be cancelled or rescheduled; once started, they can only be completed, marked as a no-show, or cancelled. To protect against receptionist misclicks, we provide a 10-minute undo window that can restore a cancelled appointment provided the slot hasn't been claimed by the waitlist. We also support controlled corrections—allowing staff to swap Completed and No-Show or waive a Late-Cancel penalty—with all changes logged in our tamper-evident audit history."*

---

## 4. Interview Live Coding Drills

### Drill 1: "Allow staff to undo a cancellation for up to 30 minutes."
**Answer:** Change `undo_minutes` in `Policy` or call `PATCH /policy {"undo_minutes": 30}`.

### Drill 2: "Prevent check-in if the appointment is more than 2 hours away."
**Answer:** In `check_can_check_in`:
```python
MAX_EARLY_CHECKIN = timedelta(hours=2)
if start_at - now > MAX_EARLY_CHECKIN:
    raise ConflictError(ErrorCode.TOO_EARLY_TO_MARK, "Check-in opens 2 hours before the visit.")
```

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why can't you undo an appointment that was cancelled as part of a reschedule?**  
  * **A:** When an appointment is rescheduled, the old appointment is cancelled and a *new* appointment is booked in the same transaction. If you were allowed to "undo" the old cancellation, you would end up with **two active appointments** for the patient instead of one.
* **Q: Why is `start_at` enforced for `complete` and `no_show`?**  
  * **A:** A patient cannot complete an appointment or be declared a no-show before the appointment has even occurred (`TOO_EARLY_TO_MARK`). Marking a no-show at 9:00 AM for a 2:00 PM appointment would be premature and punitive.
