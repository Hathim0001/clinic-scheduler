# Backend File Guide: `backend/app/domain/policy.py`

> **File Path:** [`backend/app/domain/policy.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/policy.py)  
> **Topic:** Configurable Business Rules, Permitted Ranges & Zero-Code Modifications  
> **Key Function:** `Policy` dataclass, `problems(policy)`

---

## 1. File Role & High-Level Purpose

In production systems, hardcoding business constants (such as 60-day horizons, 2-hour cancellation windows, or 2-strike thresholds) is an anti-pattern. Different medical practices require different operational policies.

This file defines the **dynamic policy engine**:
- Stores all clinic operational parameters in a clean, typed dataclass.
- Enforces strict minimum and maximum validation bounds (`BOUNDS`) to prevent invalid clinic configurations.
- Allows administrators to tune business rules via API (`PATCH /api/v1/policy`) or web UI **without modifying code or redeploying the server**.

---

## 2. Key Data Structures & Code Breakdown

### A. Allowed Bounds: `BOUNDS` (Lines 16–25)
Defines the safe operational limits for every parameter:
```python
BOUNDS: dict[str, tuple[int, int]] = {
    "horizon_days": (1, 365),            # Between 1 day and 1 year
    "late_cancel_hours": (0, 72),        # Between 0 (disabled) and 3 days
    "strike_lookback_days": (1, 180),    # Between 1 day and 6 months
    "strikes": (1, 10),                  # Between 1 and 10 penalty events
    "undo_minutes": (0, 60),             # Between 0 (disabled) and 1 hour
    "offer_hold_minutes": (5, 240),      # Between 5 mins and 4 hours
    "reminder_first_hours": (0, 168),    # Up to 7 days before
    "reminder_second_hours": (0, 48),    # Up to 2 days before
}
```

### B. The `Policy` Dataclass (Lines 29–55)
Provides the project's default numbers (which match the assignment brief):
```python
@dataclass(frozen=True, slots=True)
class Policy:
    horizon_days: int = 60
    late_cancel_hours: int = 2
    strike_lookback_days: int = 30
    strikes: int = 2
    undo_minutes: int = 10
    offer_hold_minutes: int = 30
    reminder_first_hours: int = 24
    reminder_second_hours: int = 2
```
Contains helper properties for typed timedelta conversion:
- `policy.late_threshold -> timedelta(hours=self.late_cancel_hours)`
- `policy.lookback -> timedelta(days=self.strike_lookback_days)`
- `policy.undo_window -> timedelta(minutes=self.undo_minutes)`

### C. Validation: `problems(policy: Policy) -> dict[str, str]` (Lines 60–71)
Validates input when an administrator updates the policy:
- Checks every field against `BOUNDS`.
- Verifies logical relationships: e.g., the second reminder cannot be scheduled at the exact same hour as the first reminder.

---

## 3. Interview Pitch (60-Second Explanation)

> *"In `policy.py`, we externalize the clinic's business thresholds. While the assignment defines standard values—such as a 60-day window, a 2-hour late cancellation threshold, and 2 strikes in 30 days—we encapsulate these in an immutable `Policy` dataclass with strict min/max validation bounds. These settings are persisted in a single-row `clinic_policy` database table and injected into our pure domain functions on every request. This architecture enables clinic administrators to adjust business rules live through the UI without requiring code changes or service restarts."*

---

## 4. Interview Live Coding Drills

### Drill 1: "How do you change the late cancel threshold in an interview?"
**The Senior Engineer Answer:**  
*"I don't need to change any code. I can make an authenticated `PATCH` request to `/api/v1/policy` with `{"late_cancel_hours": 3}`. If you want to change the hardcoded fallback default for fresh installations, I simply update the default value in `domain/policy.py` on line 31."*

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Does updating a policy apply retroactively to past appointments?**  
  * **A:** No. If you reduce the late-cancel threshold from 2 hours to 1 hour, appointments cancelled yesterday remain recorded as whatever they were classified at the time of cancellation (`A-19`). However, because deposit status is derived dynamically on read, a patient whose strike fell 20 days ago will now be evaluated against whatever `strike_lookback_days` is currently active.
