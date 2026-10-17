"""Plain data the rules work on: statuses, windows and snapshots of rows.

The domain never touches the database. Services load rows, turn them into these frozen
dataclasses and hand them to the pure rule functions, together with "now" as an argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Status(StrEnum):
    BOOKED = "BOOKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    LATE_CANCELLED = "LATE_CANCELLED"
    NO_SHOW = "NO_SHOW"


class CancelledBy(StrEnum):
    PATIENT = "PATIENT"
    CLINIC = "CLINIC"


# Statuses that occupy a slot and count toward a doctor's daily cap. A cancelled or late-cancelled
# appointment frees its slot (assumption A-16); a no-show still occupied the slot.
ACTIVE_STATUSES: frozenset[Status] = frozenset({Status.BOOKED, Status.COMPLETED, Status.NO_SHOW})
CANCELLED_STATUSES: frozenset[Status] = frozenset({Status.CANCELLED, Status.LATE_CANCELLED})


@dataclass(frozen=True, slots=True)
class Window:
    """A stretch of working time on one day: minutes since IST midnight, half-open [start, end)."""

    start_min: int
    end_min: int


@dataclass(frozen=True, slots=True)
class WeeklyWindow:
    """A recurring window. weekday follows Python: Monday is 0."""

    weekday: int
    start_min: int
    end_min: int


@dataclass(frozen=True, slots=True)
class DoctorFacts:
    id: int
    name: str
    slot_length_min: int
    daily_cap: int


@dataclass(frozen=True, slots=True)
class AppointmentFacts:
    id: int
    doctor_id: int
    patient_id: int
    start_at: datetime
    end_at: datetime
    status: Status


@dataclass(frozen=True, slots=True)
class SlotContext:
    """Everything needed to decide whether one slot is bookable.

    doctor_appts: that doctor's appointments (all statuses) around the day of the slot.
    patient_appts: the patient's appointments (all statuses); empty when no patient is involved.
    """

    doctor: DoctorFacts
    windows: tuple[Window, ...]
    doctor_appts: tuple[AppointmentFacts, ...]
    patient_appts: tuple[AppointmentFacts, ...]
    now: datetime


@dataclass(frozen=True, slots=True)
class PenaltyEvent:
    """One strike: a late cancellation (at its cancellation time) or a no-show (at its start)."""

    appointment_id: int
    kind: Status  # LATE_CANCELLED or NO_SHOW
    at: datetime


@dataclass(frozen=True, slots=True)
class DepositStatus:
    """Whether a patient must acknowledge a deposit, why, and until when (inclusive)."""

    required: bool
    reasons: tuple[PenaltyEvent, ...]  # newest first
    required_until: datetime | None
