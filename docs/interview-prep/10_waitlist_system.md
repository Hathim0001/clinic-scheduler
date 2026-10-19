# Backend File Guide: `backend/app/services/waitlist_service.py` & `waitlist_offers.py`

> **File Paths:**  
> - [`backend/app/services/waitlist_service.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/services/waitlist_service.py)  
> - [`backend/app/services/waitlist_offers.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/services/waitlist_offers.py)  
> **Topic:** Automated Waitlist, FIFO Queueing, 30-Minute Hold & Slot Offers  
> **Key Methods:** `offer_freed_slot()`, `accept_offer()`, `decline_offer()`, `sweep_lapsed_offers()`

---

## 1. File Role & High-Level Purpose

When all slots for a doctor are booked on a given date, patients don't have to repeatedly refresh the page or call the clinic. They can join a **first-come, first-served (FIFO) waitlist** for that doctor and date.

This subsystem manages:
1. Patients queueing for a fully booked day.
2. **Instant automatic slot offers:** The millisecond an appointment is cancelled or rescheduled, the system identifies the next eligible patient in line and offers the slot to them.
3. **Exclusive 30-minute hold:** The freed slot is held exclusively for the offered patient for 30 minutes (`policy.offer_hold_minutes`).
4. **Lapse handling & sweeping:** If the patient declines or lets the 30-minute window expire, the slot is immediately rolled over to the next person waiting.

---

## 2. Key Workflow Breakdown

```
Appointment Cancelled
        │
        ▼
offer_freed_slot() ──► Finds first waiting patient who satisfies first_violation()
        │
        ├──► Status: OFFERED (offer_expires_at = now + 30m)
        ├──► Queues SMS notification to patient
        │
        ▼
Patient Action:
├── ACCEPT   ──► Converts to BOOKED appointment via place_booking()
├── DECLINE  ──► Keeps place in queue; slot offered to next patient
└── EXPIRED  ──► Background sweep marks EXPIRED; slot offered to next patient
```

### A. Joining the Waitlist: `join(...)` (Lines 86–129 in `waitlist_service.py`)
- Verifies date is within 60-day horizon and not in the past.
- Verifies doctor is accepting bookings.
- Checks if the patient already has an active booking with this doctor on that day (`ALREADY_BOOKED`).
- Checks if the patient is already on the waitlist for that day (`ALREADY_WAITING`).
- Inserts `WaitlistEntry` with `status: WAITING`.

### B. Triggering an Offer: `offer_freed_slot(...)` in `waitlist_offers.py`
Called directly inside the `cancel` and `reschedule` transactions:
1. Queries waiting patients for that doctor and date in FIFO order (`ORDER BY created_at ASC`).
2. Iterates through candidates: for each patient, it runs `first_violation()` to ensure:
   - The patient has no overlapping appointments with other doctors.
   - The slot length matches their required visit length (`offered_slots`).
   - The patient hasn't already declined this specific time slot earlier (`declined_start_at != freed_start_at`).
3. If an eligible candidate is found:
   - Sets `status = "OFFERED"`.
   - Sets `offered_start_at = freed_start_at`.
   - Sets `offer_expires_at = now + policy.offer_hold` (default 30 minutes).
   - Queues a notification message with the offer link.

### C. Accepting an Offer: `accept(...)` (Lines 163–216 in `waitlist_service.py`)
1. Checks that offer has not expired: `if now >= entry.offer_expires_at: raise OFFER_EXPIRED`.
2. Calls `place_booking()`, running all standard validation rules (including deposit rules).
3. Updates waitlist entry `status = "BOOKED"`.

### D. Declining an Offer: `decline(...)` (Lines 218–254 in `waitlist_service.py`)
- If a patient cannot make that specific time (e.g. 10:00 AM doesn't suit them, but they still want an afternoon slot), they can decline without losing their place in line!
- Sets `declined_start_at = entry.offered_start_at` and resets status back to `WAITING`.
- Immediately runs `offer_freed_slot()` so the slot goes to the next patient in line.

---

## 3. Interview Pitch (60-Second Explanation)

> *"Our waitlist operates on a FIFO model per doctor and date. When an appointment is cancelled or rescheduled, our `offer_freed_slot` service immediately evaluates the queue and offers the opening to the first waiting patient whose schedule passes all booking rules. The slot is held exclusively for 30 minutes, backed by an automated SMS notification. If the patient accepts, it converts into an active booking; if they decline, they retain their queue priority for other times that day while the slot is rolled forward to the next patient. A lightweight 30-second sweep task reclaims and reoffers any lapsed reservations."*

---

## 4. Trap Questions & Interviewer Gotchas

* **Q: Why does accepting a waitlist offer re-run `first_violation()`?**  
  * **A:** Between the moment the offer was made and the moment the patient clicked "Accept" (up to 30 minutes later), the patient might have booked an appointment with another doctor, or accrued a new deposit strike. Re-running the rules inside the acceptance transaction ensures absolute consistency.
* **Q: Can an undo-cancel steal a slot that was offered to a waitlist patient?**  
  * **A:** No! In [`booking_service.py:L311`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/services/booking_service.py#L311), `undo_cancel` checks `if repo.offer_open_for(session, doctor.id, start_at): raise UNDO_NOT_POSSIBLE`. Once an offer has been extended to a waiting patient, the cancellation cannot be undone; the original patient must book a new slot.
