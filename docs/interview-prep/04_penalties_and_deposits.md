# Backend File Guide: `backend/app/domain/penalties.py`

> **File Path:** [`backend/app/domain/penalties.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/penalties.py)  
> **Topic:** The 2-Strike Penalty Rule, 30-Day Rolling Window & Dynamic Deposit Status  
> **Key Function:** `deposit_status(events, now, policy)`

---

## 1. File Role & High-Level Purpose

This file implements **Rule 5 (Second Half)**: preventing chronic no-shows and last-minute cancellations from abusing clinic time.

The rule:
> *"If a patient accumulates **2 or more strikes** (either `LATE_CANCELLED` or `NO_SHOW`) in a trailing **30-day window**, they are flagged. Any subsequent booking requires an explicit deposit acknowledgement (`deposit_confirmed: true`)."*

### Architectural Masterstroke: Derived Status (Not Stored)
The deposit requirement is **never stored as a flag or column in the database**. It is derived purely at runtime whenever the patient is queried or booked.
- Stored flags go stale as time passes and require background cron jobs to clean up.
- Derived flags update automatically as time flows forward, respond immediately if an outcome is corrected, and work seamlessly with simulated test clocks.

---

## 2. Key Functions & Code Breakdown

### `deposit_status(events: Iterable[PenaltyEvent], now: datetime, policy: Policy) -> DepositStatus` (Lines 20–45)
```python
def deposit_status(
    events: Iterable[PenaltyEvent], now: datetime, policy: Policy = DEFAULT_POLICY
) -> DepositStatus:
    recent = sorted(
        (event for event in events if now - policy.lookback <= event.at <= now),
        key=lambda event: (event.at, event.appointment_id),
        reverse=True,
    )
    days = policy.strike_lookback_days
    if len(recent) < policy.strikes:
        return DepositStatus(
            required=False, reasons=tuple(recent), required_until=None, lookback_days=days
        )
    return DepositStatus(
        required=True,
        reasons=tuple(recent),
        required_until=recent[policy.strikes - 1].at + policy.lookback,
        lookback_days=days,
    )
```

#### Detailed Logic & Edge Cases:
1. **The 30-Day Closed Interval (`A-22`):**
   `now - 30 days <= event.at <= now`. Both endpoints are inclusive. An event that occurred exactly 30 days ago to the second is counted. One second later, it falls outside the window.
2. **Event Timestamps (`A-13`):**
   - For a `LATE_CANCELLED` appointment, the strike timestamp `event.at` is the instant the cancellation was made (`cancelled_at`).
   - For a `NO_SHOW` appointment, `event.at` is the scheduled start time of the missed appointment (`start_at`).
3. **Exact Expiration Date (`required_until`):**
   When does the penalty end? It ends when the patient has fewer than `policy.strikes` strikes left in the trailing window.
   - If `strikes = 2`, the patient is clean the moment their **second-most-recent strike** becomes older than 30 days!
   - Code: `recent[policy.strikes - 1].at + policy.lookback`.
   - At `required_until + 1 second`, `deposit_status` automatically flips from `required=True` to `required=False`.

---

## 3. Interview Pitch (60-Second Explanation)

> *"In `penalties.py`, we implement our deposit penalty system. If a patient incurs 2 or more late cancellations or no-shows within the trailing 30 days, any new booking requires a deposit acknowledgement. Crucially, we derive this status dynamically on read rather than storing a persistent column. We filter the patient's penalty history across the closed interval `[now - 30 days, now]` and compute the exact instant the penalty expires based on when the tipping strike ages out. This design eliminates background cleanup cron jobs, prevents stale data, and allows historical and future simulation via test clocks."*

---

## 4. Interview Live Coding Drills

### Drill 1: "Change the policy so strikes expire after 14 days instead of 30, and require 3 strikes."
**Answer:** In [`policy.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/policy.py):
```python
# Change defaults:
strike_lookback_days: int = 14
strikes: int = 3
```
Or at runtime without restarting the server:
```bash
curl -X PATCH /api/v1/policy -d '{"strike_lookback_days": 14, "strikes": 3}'
```

### Drill 2: "Forgive strikes if the patient completes an appointment afterwards."
**Answer:** In `deposit_status`, inspect events after the last strike:
```python
last_strike_time = recent[0].at if recent else datetime.min
has_subsequent_completion = any(
    e.kind == Status.COMPLETED and e.at > last_strike_time for e in events
)
if has_subsequent_completion:
    return DepositStatus(required=False, reasons=(), required_until=None)
```

---

## 5. Trap Questions & Interviewer Gotchas

* **Q: Why not store `deposit_required` as a boolean on the `patients` table?**  
  * **A:** If you store a boolean in a database column, it represents a snapshot in time. Thirty days later, that boolean is still `true` unless a scheduled background worker wakes up and clears it. If the worker fails, runs late, or if you run multiple application replicas with varying clock drifts, patient records become inconsistent. Deriving the flag on every query guarantees 100% real-time consistency with zero background infrastructure.
* **Q: What happens if staff mistakenly marks a patient as NO_SHOW and corrects it to COMPLETED?**  
  * **A:** Because `deposit_status` queries the current state of appointment events, correcting the status immediately removes the strike from the calculation. The patient's deposit flag clears instantaneously with zero manual intervention.
