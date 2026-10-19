# Backend File Guide: `backend/app/domain/availability.py`

> **File Path:** [`backend/app/domain/availability.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/availability.py)  
> **Topic:** Doctor Working Hours, Date Overrides, Shift Fitting & Attention Flags  
> **Key Function:** `resolve_windows(day, weekly, override)`, `fits_in_windows(start_at, end_at, windows)`

---

## 1. File Role & High-Level Purpose

This file is responsible for **Rule 1a**: ensuring that appointments are booked only when the doctor is actually on duty. 

It handles:
1. Resolving whether a doctor is working from their **standard weekly recurring hours** or a **date-specific override** (e.g. leave days, emergency shift changes, or special weekend working hours).
2. Verifying that a visit fits completely within a single continuous shift.
3. Validating the integrity of configured working shifts (checking that shift boundaries fall on slot grid marks and don't overlap).
4. Flagging pre-existing appointments that are orphaned when a doctor shortens their hours (`needs_attention`).

---

## 2. Key Functions & Code Breakdown

### A. `resolve_windows(day: date, weekly: Sequence[WeeklyWindow], override: Sequence[Window] | None) -> tuple[tuple[Window, ...], str]` (Lines 27–40)
Determines the doctor's working shifts for a given calendar day:
```python
if override is not None:
    return _in_time_order(override), "OVERRIDE"
todays = (Window(w.start_min, w.end_min) for w in weekly if w.weekday == day.weekday())
return _in_time_order(todays), "WEEKLY"
```
* **Precedence:** Date overrides always take precedence over weekly schedules (`A-02`).
* **Leave Days:** If an override exists but its list of windows is empty (`override = []`), it indicates the doctor is **on leave** for that day.
* **Weekday matching:** Python's standard `weekday()` is used (Monday = 0, Sunday = 6).

### B. `fits_in_windows(start_at: datetime, end_at: datetime, windows: Sequence[Window]) -> bool` (Lines 42–54)
Checks if the visit interval `[start_at, end_at]` lies entirely inside **one** continuous working window (`A-03`):
```python
midnight = at_ist(ist_date(start_at), 0)
begin, finish = start_at - midnight, end_at - midnight
return any(
    timedelta(minutes=window.start_min) <= begin and finish <= timedelta(minutes=window.end_min)
    for window in windows
)
```
* **No split visits:** If a doctor works `09:00–13:00` and `14:00–18:00`, an appointment *cannot* run from `12:45` to `13:15` or span across the lunch break.
* Both start and finish must be contained within `[window.start_min, window.end_min]`.

### C. `validate_windows(windows: Sequence[Window], slot_length_min: int) -> None` (Lines 56–86)
Ensures clinic managers don't enter invalid working hours:
1. `0 <= start_min < end_min <= 1440` (Valid range in minutes for a 24-hour day).
2. `start_min % slot_length_min == 0` and `end_min % slot_length_min == 0` (`WINDOW_OFF_GRID`). A 30-minute doctor cannot have a shift starting at 09:10.
3. No overlapping shifts (`WINDOW_OVERLAP`). Adjacent shifts (`09:00–13:00` and `13:00–17:00`) are allowed.

### D. `needs_attention(appt: AppointmentFacts, now: datetime, windows: Sequence[Window]) -> bool` (Lines 89–99)
Checks if an appointment has been orphaned by a schedule change:
```python
return (
    appt.status is Status.BOOKED
    and appt.start_at >= now
    and not fits_in_windows(appt.start_at, appt.end_at, windows)
)
```
* If Dr. Rao originally worked until 5:00 PM and had a 4:30 PM booking, but later updates their shift to end at 4:00 PM, that 4:30 PM booking now falls outside working hours.
* The system does **not** silently delete or cancel it (`A-12`). It flags it as `needs_attention: true` so receptionists can call the patient to reschedule.

---

## 3. Interview Pitch (60-Second Explanation)

> *"In `availability.py`, we manage doctor shifts and schedule constraints. Daily availability is resolved by prioritizing date-specific overrides over recurring weekly schedules; an override with zero windows cleanly models a doctor taking leave. We enforce that every appointment must fit entirely within one continuous shift, preventing appointments from spanning across breaks. We also validate that working shifts align with the doctor's slot grid. When a doctor modifies their shift and leaves existing future bookings outside the new hours, we do not cancel them; instead, our `needs_attention` logic flags them so staff can proactively reschedule."*

---

## 4. Interview Live Coding Drills

### Drill 1: "Add a clinic rule: Doctors are completely closed on national holidays."
**How to solve:** In `resolve_windows()`, check if `day` is in a set of holiday dates. If so, return an empty tuple regardless of weekly schedule:
```python
NATIONAL_HOLIDAYS = {date(2026, 1, 26), date(2026, 8, 15), date(2026, 10, 2)}

def resolve_windows(day: date, weekly: Sequence[WeeklyWindow], override: Sequence[Window] | None):
    if day in NATIONAL_HOLIDAYS:
        return (), "HOLIDAY"
    if override is not None:
        return _in_time_order(override), "OVERRIDE"
    todays = (Window(w.start_min, w.end_min) for w in weekly if w.weekday == day.weekday())
    return _in_time_order(todays), "WEEKLY"
```

### Drill 2: "Allow appointments to start up to 10 minutes before a shift ends if the visit is short."
**How to solve:** In `fits_in_windows()`, adjust the tolerance on `finish <= timedelta(minutes=window.end_min)`.

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why does `override` replace weekly windows instead of merging with them?**  
  * **A:** Merging would make it impossible to model taking time off. For instance, if Dr. Rao normally works Monday 9am–5pm, and wants to take next Monday off, an override specifying `[]` (empty) cleanly cancels the day. If they were merged, the default Monday hours would still persist.
* **Q: Why is `needs_attention` stored in the database if the domain layer has a pure function for it?**  
  * **A:** Storing `outside_hours: bool` as an indexed column in the database allows the reception overview query (`GET /appointments?needs_attention=true`) to return in single-digit milliseconds without having to load thousands of past bookings and recompute availability on every HTTP request. It is refreshed within the same transaction that updates a doctor's hours.
