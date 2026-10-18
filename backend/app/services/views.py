"""What the services take in and hand back: plain data, no ORM objects, ready to be serialised.

Instants are timezone-aware UTC datetimes. The API layer adds the IST rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.domain.model import (
    CancelledBy,
    DepositStatus,
    Status,
    UnavailableReason,
    WeeklyWindow,
    Window,
)


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class AppointmentView:
    id: int
    doctor_id: int
    doctor_name: str
    patient_id: int
    patient_name: str
    patient_phone: str
    status: Status
    start_at: datetime
    end_at: datetime
    reason: str
    deposit_required_at_booking: bool
    deposit_confirmed: bool
    cancelled_at: datetime | None
    cancelled_by: CancelledBy | None
    status_changed_at: datetime | None
    rescheduled_to_id: int | None
    needs_attention: bool
    allowed_actions: tuple[str, ...]
    checked_in_at: datetime | None = None
    urgent_symptoms: bool = False
    slots: int = 1


@dataclass(frozen=True, slots=True)
class BookCommand:
    doctor_id: int
    patient_id: int
    start_at: datetime
    reason: str
    deposit_confirmed: bool = False
    slots: int = 1  # how many of the doctor's slots the visit lasts


@dataclass(frozen=True, slots=True)
class EventView:
    id: int
    appointment_id: int
    patient_id: int
    kind: str
    at: datetime
    detail: dict[str, object]
    actor: str = "system"


@dataclass(frozen=True, slots=True)
class CancelResult:
    appointment: AppointmentView
    late: bool
    deposit: DepositStatus  # the patient's status after this cancellation


@dataclass(frozen=True, slots=True)
class RescheduleResult:
    old: AppointmentView
    new: AppointmentView


@dataclass(frozen=True, slots=True)
class DoctorView:
    id: int
    name: str
    speciality: str
    slot_length_min: int
    daily_cap: int
    accepting_bookings: bool = True


@dataclass(frozen=True, slots=True)
class PatientView:
    id: int
    name: str
    phone: str
    date_of_birth: date
    created_at: datetime
    deposit: DepositStatus | None  # None in search results, which do not compute it


@dataclass(frozen=True, slots=True)
class OverrideView:
    on_date: date
    note: str | None
    windows: tuple[Window, ...]  # empty means the doctor is on leave


@dataclass(frozen=True, slots=True)
class WeeklyView:
    windows: tuple[WeeklyWindow, ...]
    needs_attention: tuple[AppointmentView, ...] = ()


@dataclass(frozen=True, slots=True)
class OverrideChange:
    """The result of saving or removing an override."""

    on_date: date
    note: str | None
    windows: tuple[Window, ...]
    needs_attention: tuple[AppointmentView, ...]


@dataclass(frozen=True, slots=True)
class WaitlistView:
    id: int
    doctor_id: int
    doctor_name: str
    patient_id: int
    patient_name: str
    patient_phone: str
    day: date
    status: str  # WAITING, OFFERED, BOOKED, CANCELLED or EXPIRED
    position: int | None  # 1 for the next patient to be offered a slot; None unless WAITING
    offered_start_at: datetime | None
    offer_expires_at: datetime | None
    appointment_id: int | None


@dataclass(frozen=True, slots=True)
class WaitlistAcceptance:
    entry: WaitlistView
    appointment: AppointmentView


@dataclass(frozen=True, slots=True)
class SlotsView:
    doctor_id: int
    day: date
    slot_length_min: int
    source: str  # "WEEKLY" or "OVERRIDE"
    windows: tuple[Window, ...]
    slots: tuple[datetime, ...]  # starts; each visit lasts duration_min
    unavailable_reason: UnavailableReason | None
    duration_min: int = 0  # the visit length these starts are free for


class SlotState(StrEnum):
    FREE = "FREE"
    BOOKED = "BOOKED"
    PAST = "PAST"
    CAPPED = "CAPPED"
    CLOSED = "CLOSED"  # beyond the 60 day horizon
    BUSY = "BUSY"  # the chosen patient is elsewhere


@dataclass(frozen=True, slots=True)
class ScheduleSlot:
    start_at: datetime
    end_at: datetime
    state: SlotState
    appointment: AppointmentView | None = None


@dataclass(frozen=True, slots=True)
class ScheduleView:
    doctor_id: int
    day: date
    slot_length_min: int
    source: str
    windows: tuple[Window, ...]
    slots: tuple[ScheduleSlot, ...]
    outside_availability: tuple[AppointmentView, ...]
    unavailable_reason: UnavailableReason | None
