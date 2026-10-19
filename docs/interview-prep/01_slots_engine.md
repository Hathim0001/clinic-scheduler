# Backend File Guide: `backend/app/domain/slots.py`

> **File Path:** [`backend/app/domain/slots.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/slots.py)  
> **Topic:** The Central Slot Engine & Validation Orchestrator  
> **Key Function:** `first_violation(start_at, ctx, slots)`

---

## 1. File Role & High-Level Purpose

This is the **heart of the scheduling engine**. It is the single source of truth that answers: *"Can a patient book this doctor at this specific time?"*

Instead of having validation logic scattered across the UI, the slot picker, and the booking endpoint, everything is consolidated into one pure function: `first_violation()`. 
- When generating the calendar of free slots, `free_slots()` calls `first_violation()`.
- When an API request arrives to book, `BookingService` calls `first_violation()`.
- **Result:** The UI can never offer a time slot that the booking API will reject.

Like the rest of `domain/`, this file is **100% pure Python**:
- Zero database queries.
- Zero network or web framework dependencies.
- Zero calls to `datetime.now()` (time is injected via `ctx.now`).

---

## 2. Key Functions & Code Breakdown

### A. `is_on_grid(start_at: datetime, slot_length_min: int) -> bool` (Lines 31–40)
Checks that an appointment starts cleanly on the doctor's grid:
```python
local = start_at.astimezone(IST)
minute_of_day = local.hour * 60 + local.minute
return local.second == 0 and local.microsecond == 0 and minute_of_day % slot_length_min == 0
```
- Converts timestamp to Indian Standard Time (IST, UTC+05:30).
- Calculates minutes elapsed since midnight.
- Validates that `minute_of_day` is cleanly divisible by `slot_length_min` (15 or 30).
- Guarantees `second == 0` and `microsecond == 0` (e.g., `09:15:30` is rejected).

### B. `overlaps(a_start, a_end, b_start, b_end) -> bool` (Lines 26–29)
Determines if two appointments collide using **half-open intervals `[start, end)`**:
```python
return a_start < b_end and b_start < a_end
```
- If appointment A is 10:00–10:30 and appointment B is 10:30–11:00:
  `10:00 < 11:00` (True), but `10:30 < 10:30` (False) $\rightarrow$ **No overlap!** Back-to-back appointments work perfectly.

### C. `first_violation(start_at: datetime, ctx: SlotContext, slots: int = 1) -> ErrorCode | None` (Lines 42–78)
Evaluates all booking criteria in a **strict, prioritized order** (cheapest and most general checks first):

1. **Doctor Accepting Bookings:** Checks `ctx.doctor.accepting_bookings`. If False $\rightarrow$ `DOCTOR_NOT_ACCEPTING`.
2. **Booking Window:** Checks `check_booking_window(start_at, ctx.now, ctx.policy.horizon_days)` $\rightarrow$ `BOOKING_IN_PAST` or `BOOKING_TOO_FAR`.
3. **Slot Grid:** Checks `is_on_grid(start_at, length)` $\rightarrow$ `OFF_GRID`.
4. **Working Hours:** Checks `fits_in_windows(start_at, end_at, ctx.windows)` $\rightarrow$ `OUTSIDE_AVAILABILITY`.
5. **Daily Doctor Cap:** Counts active bookings for that doctor on that IST day. If $\ge$ `daily_cap` $\rightarrow$ `DAILY_CAP_REACHED`.
6. **Doctor Conflict:** Checks if any active appointment for this doctor overlaps the interval $\rightarrow$ `SLOT_TAKEN`.
7. **Patient Conflict:** Checks if any active appointment for this patient across *any* doctor overlaps $\rightarrow$ `PATIENT_OVERLAP`.
8. **Returns `None`** if all rules pass!

### D. `free_slots(day: date, ctx: SlotContext, slots: int = 1) -> list[datetime]` (Lines 93–99)
Generates all bookable start times for a day:
- Iterates over all possible grid ticks inside the doctor's working shifts (`candidate_starts()`).
- Filters candidates by running `first_violation(start, ctx, slots) is None`.

---

## 3. Interview Pitch (60-Second Explanation)

> *"In our system, `slots.py` implements the core scheduling predicate `first_violation`. It evaluates every booking rule in a deterministic sequence: checking whether the doctor is accepting patients, ensuring the time is within the 60-day IST window and not in the past, validating alignment to the 15- or 30-minute grid, verifying it fits completely within a working shift, checking the doctor's daily appointment cap, and finally checking for doctor or patient double-booking. We use half-open intervals so back-to-back appointments don't collide. Because both our free-slot finder and our booking transaction call this exact same pure function, our system guarantees that the UI never displays a slot the backend would reject."*

---

## 4. Interview Live Coding Drills

### Drill 1: "Make the daily cap count slots (time spent) instead of appointments (patients)."
**Current behavior:** A 60-minute visit (2 slots) counts as 1 appointment towards the cap.  
**Where to change:** Lines 68–70 in [`slots.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/slots.py#L68-L70).  
**Change:**
```python
# Before:
if sum(1 for a in doctor_active if ist_date(a.start_at) == day) >= ctx.doctor.daily_cap:
    return ErrorCode.DAILY_CAP_REACHED

# After:
if sum(a.slots for a in doctor_active if ist_date(a.start_at) == day) + slots > ctx.doctor.daily_cap:
    return ErrorCode.DAILY_CAP_REACHED
```

### Drill 2: "Add a mandatory 15-minute buffer between appointments for disinfection."
**Where to change:** In `overlaps()` or when calculating `end_at` for doctor conflicts.  
**Change in `first_violation`:**
```python
buffer = timedelta(minutes=15)
buffered_start = start_at - buffer
buffered_end = end_at + buffer
if any(overlaps(buffered_start, buffered_end, a.start_at, a.end_at) for a in doctor_active):
    return ErrorCode.SLOT_TAKEN
```

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why does the Daily Cap check come BEFORE the Slot Taken check in `first_violation`?**  
  * **A:** When a doctor reaches their daily cap, every single slot for the remainder of that day becomes unbookable. Returning `DAILY_CAP_REACHED` tells the user "Doctor is fully booked for the day", which is much more informative than telling them "Slot 10:00 is taken, slot 10:15 is taken, slot 10:30 is taken".
* **Q: Why is `start_at` converted to IST inside `is_on_grid`?**  
  * **A:** UTC midnight does not align with Indian calendar midnight (+05:30 offset). If you calculate minutes since UTC midnight, a 9:00 AM IST appointment would be evaluated against 3:30 AM UTC, which could skew grid alignment calculations on arbitrary slot intervals.
