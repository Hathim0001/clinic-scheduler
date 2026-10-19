# Backend Business Rules: Interview Preparation Master Index

This directory contains standalone, deep-dive interview preparation documents for each core backend file governing business rules, concurrency safeguards, state machines, and persistence.

---

## 📚 Study Guides by File

| # | Topic & Focus | Source File in Codebase | Dedicated Interview Guide |
|---|---|---|---|
| **01** | **The Central Slot Engine**<br>Rule checks, half-open intervals, grid alignment, single decision maker | [`backend/app/domain/slots.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/slots.py) | [**`01_slots_engine.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/01_slots_engine.md) |
| **02** | **Working Hours & Shifts**<br>Weekly patterns, date overrides, leave days, orphaned booking alerts | [`backend/app/domain/availability.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/availability.py) | [**`02_availability_windows.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/02_availability_windows.md) |
| **03** | **Cancellation Rules**<br>2-hour threshold, patient vs clinic actor, reschedule start guard | [`backend/app/domain/cancellation.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/cancellation.py) | [**`03_cancellation_rules.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/03_cancellation_rules.md) |
| **04** | **Penalties & Deposits**<br>2 strikes in 30 days, rolling window, derived runtime status | [`backend/app/domain/penalties.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/penalties.py) | [**`04_penalties_and_deposits.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/04_penalties_and_deposits.md) |
| **05** | **Booking Window**<br>Strict past guard (`start <= now`), 60-day calendar horizon in IST | [`backend/app/domain/booking_window.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/booking_window.py) | [**`05_booking_window.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/05_booking_window.md) |
| **06** | **State Transitions**<br>Appointment FSM, 10-minute undo cancellation, outcome corrections | [`backend/app/domain/transitions.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/transitions.py) | [**`06_state_transitions.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/06_state_transitions.md) |
| **07** | **Clinic Policy Configuration**<br>Dynamic parameters, bounds validation, zero-downtime policy changes | [`backend/app/domain/policy.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/policy.py) | [**`07_clinic_policy.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/07_clinic_policy.md) |
| **08** | **Phone Normalization**<br>E.164 +91 format, ASCII validation, database uniqueness, privacy guard | [`backend/app/domain/phone.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/domain/phone.py) | [**`08_phone_normalization.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/08_phone_normalization.md) |
| **09** | **Booking Orchestration**<br>Pessimistic locking hierarchy, atomic reschedule, idempotency | [`backend/app/services/booking_service.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/services/booking_service.py) | [**`09_booking_service_orchestration.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/09_booking_service_orchestration.md) |
| **10** | **Automated Waitlist**<br>FIFO queueing, cancellation triggers, 30-minute reservation hold, sweeps | [`backend/app/services/waitlist_service.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/services/waitlist_service.py) | [**`10_waitlist_system.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/10_waitlist_system.md) |
| **11** | **Database Constraints**<br>Postgres GiST exclusion, `tstzrange`, partial penalty indexes, audit chain | [`backend/app/persistence/models.py`](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/backend/app/persistence/models.py) | [**`11_database_constraints_and_models.md`**](file:///f:/KJBN%20Labs%20Hackathon/clinic-scheduler/docs/interview-prep/11_database_constraints_and_models.md) |

---

## 🎯 How to Use These in an Interview

Each document follows a consistent, high-yield structure:
1. **Plain English Purpose**: What the file does and why the business needs it.
2. **Code Breakdown**: Exact line ranges and functions with no boilerplate.
3. **The 60-Second Interview Pitch**: Word-for-word scripts you can speak aloud when asked *"How does file X work?"*.
4. **Live Coding Drills**: Step-by-step modification recipes when an interviewer says *"Change rule X to Y"*.
5. **Trap Questions & Gotchas**: Subtle edge cases (concurrency races, calendar math, lock ordering) that prove senior-level understanding.
