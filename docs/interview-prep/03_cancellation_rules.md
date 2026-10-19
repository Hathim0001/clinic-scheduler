# Backend File Guide: `backend/app/domain/cancellation.py`

> **File Path:** [`backend/app/domain/cancellation.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/cancellation.py)  
> **Topic:** Cancellation Windows, Actor Attribution & Reschedule Boundary Guards  
> **Key Function:** `classify_cancellation(start_at, now, by, late_threshold)`

---

## 1. File Role & High-Level Purpose

This file implements **Rule 5 (First Half)**: categorizing cancellations as either standard (`CANCELLED`) or late (`LATE_CANCELLED`), and preventing modification of appointments that have already started.

Cancellations have immediate business consequences:
- A regular cancellation frees up the slot with no penalty to the patient.
- A **Late-Cancel** frees the slot but assigns a **strike** to the patient. Accumulating 2 strikes triggers the deposit rule.
- A **Clinic-initiated cancel** must **never** penalize a patient (even if cancelled 5 minutes before the visit).

---

## 2. Key Functions & Code Breakdown

### A. `classify_cancellation(...) -> Status` (Lines 14–29)
```python
LATE_THRESHOLD = timedelta(hours=2)

def classify_cancellation(
    start_at: datetime,
    now: datetime,
    by: CancelledBy,
    late_threshold: timedelta = LATE_THRESHOLD,
) -> Status:
    if by is CancelledBy.CLINIC:
        return Status.CANCELLED
    return Status.CANCELLED if start_at - now >= late_threshold else Status.LATE_CANCELLED
```

#### Exact Boundaries & Nuances:
1. **Clinic Exemption (`A-09`):** When `by == CancelledBy.CLINIC`, the status is unconditionally `Status.CANCELLED`. If a doctor falls ill and the clinic cancels an appointment 15 minutes before the start time, the patient is never blamed.
2. **The 2-Hour Line:** 
   - `start_at - now >= timedelta(hours=2)`: Normal cancellation.
   - Example: Appointment at `11:30`.
     - Cancelled at `09:30:00` (exactly 2h 00m 00s remaining) $\rightarrow$ **Normal (`CANCELLED`)**.
     - Cancelled at `09:30:01` (1h 59m 59s remaining) $\rightarrow$ **Late (`LATE_CANCELLED`)**.
3. **Cancellations After Start (`A-08`):** If a patient calls to cancel 10 minutes *after* their appointment was supposed to start (`now > start_at`), `start_at - now` is negative, which is `< 2 hours`, so it is classified as `LATE_CANCELLED`.

### B. `check_can_reschedule(start_at: datetime, now: datetime) -> None` (Lines 31–38)
```python
def check_can_reschedule(start_at: datetime, now: datetime) -> None:
    if now >= start_at:
        raise ConflictError(
            ErrorCode.APPOINTMENT_ALREADY_STARTED,
            "The appointment has already started, so it can no longer be moved.",
        )
```
- A patient can cancel an appointment that has started (as a late cancel), but they **cannot reschedule** it.
- *Why?* Rescheduling an already-started appointment would book a new future slot while leaving a started/in-progress slot empty and unfillable. Once an appointment starts, the only valid operational outcomes are `COMPLETED`, `NO_SHOW`, or `CANCELLED`.

---

## 3. Interview Pitch (60-Second Explanation)

> *"In `cancellation.py`, we implement our cancellation classification rule based on a 2-hour threshold and actor attribution. If an appointment is cancelled by the clinic, it is always recorded as a standard cancellation to protect the patient. If cancelled by the patient $\ge$ 2 hours in advance, it is standard; under 2 hours or after the start time, it becomes a LATE_CANCELLED event that counts as a strike toward our deposit penalty. We also enforce that once an appointment's start time arrives, it can no longer be rescheduled, preventing patients from moving appointments that are already in progress."*

---

## 4. Interview Live Coding Drills

### Drill 1: "Make the late cancellation threshold configurable per doctor."
**Where to change:** Pass `doctor.late_cancel_hours` into `classify_cancellation()`.
```python
threshold = timedelta(hours=doctor.custom_late_hours if doctor.custom_late_hours else policy.late_cancel_hours)
outcome = classify_cancellation(start_at, now, by, late_threshold=threshold)
```

### Drill 2: "Allow VIP patients a 1-hour cancellation window instead of 2 hours."
```python
threshold = timedelta(hours=1) if patient.is_vip else policy.late_threshold
outcome = classify_cancellation(start_at, now, by, late_threshold=threshold)
```

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why does `classify_cancellation` take `now` as an argument instead of calling `datetime.now()`?**  
  * **A:** This makes the classification completely deterministic and testable. In unit tests, we pass timestamps with exact microsecond precision (`09:30:00` vs `09:30:01`) to verify boundary behavior without needing mocking libraries or sleeps. It also allows clinic staff to test cancellation policies under historical or future test clocks (`X-Test-Clock`).
* **Q: What is the difference between a `LATE_CANCELLED` appointment and a `NO_SHOW`?**  
  * **A:** Both count as strikes toward the deposit penalty. However, a `LATE_CANCELLED` appointment explicitly frees the time slot immediately so someone on the waitlist can take it. A `NO_SHOW` occupied the time slot until after the visit started without freeing it for anyone else.
