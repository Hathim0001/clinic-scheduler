# Backend File Guide: `backend/app/domain/booking_window.py`

> **File Path:** [`backend/app/domain/booking_window.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/booking_window.py)  
> **Topic:** Booking Window Boundaries: Strict Past Guard & 60-Day Horizon  
> **Key Function:** `check_booking_window(start_at, now, horizon_days)`

---

## 1. File Role & High-Level Purpose

This file implements **Rule 7**: establishing the chronological boundaries of when appointments can be booked.
1. **Past Guard:** You cannot book a slot that has already occurred or is currently occurring.
2. **Horizon Guard:** You cannot book appointments too far into the future (default limit is 60 days).

---

## 2. Key Functions & Code Breakdown

### `check_booking_window(start_at: datetime, now: datetime, horizon_days: int = 60) -> ErrorCode | None` (Lines 14–30)
```python
def check_booking_window(
    start_at: datetime, now: datetime, horizon_days: int = HORIZON_DAYS
) -> ErrorCode | None:
    if start_at <= now:
        return ErrorCode.BOOKING_IN_PAST
    if ist_date(start_at) > ist_date(now) + timedelta(days=horizon_days):
        return ErrorCode.BOOKING_TOO_FAR
    return None
```

#### Detailed Rules & Assumptions:
1. **Strict Past (`A-07`):**
   - The comparison is `start_at <= now`, not `start_at < now`.
   - If `now` is `10:00:00.000000`, an appointment starting at `10:00:00.000000` is **rejected** as `BOOKING_IN_PAST`.
   - *Why?* A medical consultation cannot begin instantaneously at the exact microsecond of booking; check-in and doctor preparation require future time.
2. **Calendar Days, NOT $60 \times 24$ Hours (`A-05`):**
   - We extract the **IST calendar date** of both timestamps using `ist_date()`.
   - Formula: `ist_date(start_at) > ist_date(now) + timedelta(days=horizon_days)`.
   - *Why this distinction matters:*
     - If the rule were implemented as `start_at > now + timedelta(days=60)`, then on October 19 at 3:00 PM, a patient could book December 18 at 2:00 PM, but would be **blocked** from booking December 18 at 4:00 PM!
     - By comparing calendar dates, if December 18 is within 60 days, **every slot on December 18** (from morning to evening) is bookable. December 19 (Day 61) is rejected.

---

## 3. Interview Pitch (60-Second Explanation)

> *"In `booking_window.py`, we enforce the temporal bounds for all bookings. First, we enforce a strict past check where `start_at <= now` is rejected, ensuring no appointments can be scheduled for times that have already elapsed. Second, we enforce a 60-day maximum horizon. Crucially, we calculate this limit using Indian Standard Time calendar dates rather than raw hours (`60 x 24`). This ensures that patients can book any slot throughout the entire 60th day, providing a predictable user experience."*

---

## 4. Interview Live Coding Drills

### Drill 1: "Allow booking up to 90 days ahead for routine checkups."
**Answer:** Update `horizon_days` via policy or pass 90:
```python
horizon = 90 if is_routine_checkup else ctx.policy.horizon_days
violation = check_booking_window(start_at, ctx.now, horizon_days=horizon)
```

### Drill 2: "Require at least 1 hour of advance notice for bookings (no last-minute bookings)."
**Answer:** Modify the past check to require a lead time:
```python
MIN_LEAD_TIME = timedelta(hours=1)
if start_at < now + MIN_LEAD_TIME:
    return ErrorCode.BOOKING_IN_PAST  # or a custom LEAD_TIME_REQUIRED code
```

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why convert to IST date rather than comparing UTC dates?**  
  * **A:** IST is UTC+05:30. At 1:00 AM on October 20 in India, the UTC timestamp is 7:30 PM on October 19. If you compare UTC dates, the system would calculate the date boundary based on Greenwich Mean Time, cutting off clinic booking availability in the early morning hours for patients living in India.
