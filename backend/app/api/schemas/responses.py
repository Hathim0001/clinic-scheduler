"""Response bodies. Every instant is given twice, `..._utc` and `..._ist`, so nothing downstream
has to convert."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class WindowOut(BaseModel):
    start: str
    end: str


class WeeklyWindowOut(WindowOut):
    weekday: int


class DoctorOut(BaseModel):
    id: int
    name: str
    speciality: str
    slot_length_min: int
    daily_cap: int
    accepting_bookings: bool


class StrikeOut(BaseModel):
    appointment_id: int
    type: Literal["NO_SHOW", "LATE_CANCELLED"]
    at_utc: str
    at_ist: str


class DepositOut(BaseModel):
    required: bool
    required_until_utc: str | None
    required_until_ist: str | None
    reasons: list[StrikeOut]


class PatientOut(BaseModel):
    id: int
    name: str
    phone: str
    date_of_birth: str
    created_at_utc: str
    deposit_required: bool | None  # same as deposit.required; null in search results
    deposit: DepositOut | None


class AppointmentOut(BaseModel):
    id: int
    doctor_id: int
    doctor_name: str
    patient_id: int
    patient_name: str
    patient_phone: str
    status: str
    start_at_utc: str
    start_at_ist: str
    end_at_utc: str
    end_at_ist: str
    reason: str
    deposit_required_at_booking: bool
    deposit_confirmed: bool
    cancelled_at_utc: str | None
    cancelled_at_ist: str | None
    cancelled_by: str | None
    status_changed_at_utc: str | None
    status_changed_at_ist: str | None
    rescheduled_to_id: int | None
    needs_attention: bool
    allowed_actions: list[str]
    checked_in_at_utc: str | None
    checked_in_at_ist: str | None
    urgent_symptoms: bool  # the reason mentions symptoms that may need emergency care


class PageOut[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class SeriesOut(BaseModel):
    appointments: list[AppointmentOut]


class WaitlistOut(BaseModel):
    id: int
    doctor_id: int
    doctor_name: str
    patient_id: int
    patient_name: str
    patient_phone: str
    date: str
    status: Literal["WAITING", "OFFERED", "BOOKED", "CANCELLED", "EXPIRED"]
    position: int | None
    offered_start_at_utc: str | None
    offered_start_at_ist: str | None
    offer_expires_at_utc: str | None
    offer_expires_at_ist: str | None
    appointment_id: int | None


class WaitlistAcceptOut(BaseModel):
    entry: WaitlistOut
    appointment: AppointmentOut


class CancelOut(BaseModel):
    appointment: AppointmentOut
    late: bool
    deposit: DepositOut


class RescheduleOut(BaseModel):
    old: AppointmentOut
    new: AppointmentOut


class SlotOut(BaseModel):
    start_at_utc: str
    start_at_ist: str
    end_at_utc: str
    end_at_ist: str


class SlotsOut(BaseModel):
    doctor_id: int
    date: str
    slot_length_min: int
    source: Literal["WEEKLY", "OVERRIDE"]
    windows: list[WindowOut]
    slots: list[SlotOut]
    unavailable_reason: str | None


class ScheduleSlotOut(SlotOut):
    state: str
    appointment: AppointmentOut | None


class ScheduleOut(BaseModel):
    doctor_id: int
    date: str
    slot_length_min: int
    source: Literal["WEEKLY", "OVERRIDE"]
    windows: list[WindowOut]
    slots: list[ScheduleSlotOut]
    outside_availability: list[AppointmentOut]
    unavailable_reason: str | None


class WeeklyOut(BaseModel):
    windows: list[WeeklyWindowOut]
    needs_attention: list[AppointmentOut]


class OverrideOut(BaseModel):
    date: str
    note: str | None
    windows: list[WindowOut]
    needs_attention: list[AppointmentOut]


class ClockOut(BaseModel):
    now_utc: str
    now_ist: str
    source: Literal["REAL", "HEADER"]
    test_clock_enabled: bool
    seed_anchor_date: str | None
    seed_queue_day: str | None


class HealthOut(BaseModel):
    status: str


class EventOut(BaseModel):
    id: int
    appointment_id: int
    patient_id: int
    kind: str
    at_utc: str
    at_ist: str
    detail: dict[str, object]
    actor: str  # who did it: the staff name when login is on, else "anonymous" or "system"


class PatientExportOut(BaseModel):
    patient: PatientOut
    appointments: list[AppointmentOut]
    events: list[EventOut]


class TriageOut(BaseModel):
    urgent: bool
    message: str | None


class DoctorReportOut(BaseModel):
    doctor_id: int
    doctor_name: str
    capacity_slots: int
    appointments: int
    new_bookings: int
    booked: int
    completed: int
    no_show: int
    cancelled: int
    late_cancelled: int
    rescheduled: int
    checked_in: int
    utilisation: float | None
    no_show_rate: float | None


class ReportOut(BaseModel):
    start: str
    end: str
    doctors: list[DoctorReportOut]
    total: DoctorReportOut
