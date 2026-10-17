"""Insert helpers for integration tests: rows go straight into the database, bypassing the services,
so a test can arrange any state (including ones the rules would refuse to create)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.domain.model import Status
from app.persistence.models import (
    Appointment,
    Doctor,
    OverrideRow,
    OverrideWindowRow,
    Patient,
    WeeklyWindowRow,
)


def add_doctor(
    session: Session, *, name: str = "Dr. Test", slot: int = 30, cap: int = 10
) -> Doctor:
    doctor = Doctor(name=name, speciality="General", slot_length_min=slot, daily_cap=cap)
    session.add(doctor)
    session.flush()
    return doctor


def add_weekly(
    session: Session, doctor_id: int, weekday: int, start_min: int, end_min: int
) -> WeeklyWindowRow:
    row = WeeklyWindowRow(
        doctor_id=doctor_id, weekday=weekday, start_min=start_min, end_min=end_min
    )
    session.add(row)
    session.flush()
    return row


def add_override(
    session: Session,
    doctor_id: int,
    day: date,
    windows: list[tuple[int, int]],
    note: str | None = None,
) -> OverrideRow:
    """An override for `day`; an empty list of windows is a leave day."""
    row = OverrideRow(doctor_id=doctor_id, on_date=day, note=note)
    row.windows = [OverrideWindowRow(start_min=s, end_min=e) for s, e in windows]
    session.add(row)
    session.flush()
    return row


def add_patient(session: Session, n: int = 1, *, name: str | None = None) -> Patient:
    patient = Patient(
        name=name or f"Patient {n}", phone=f"+9190000000{n:02d}", date_of_birth=date(1990, 1, 1)
    )
    session.add(patient)
    session.flush()
    return patient


def add_appointment(
    session: Session,
    doctor_id: int,
    patient_id: int,
    start: datetime,
    *,
    minutes: int = 30,
    status: Status = Status.BOOKED,
    reason: str = "Check-up",
    **extra: object,
) -> Appointment:
    """An appointment in any status, with the timestamps the database constraints require."""
    fields: dict[str, object] = {
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "start_at": start,
        "end_at": start + timedelta(minutes=minutes),
        "status": status.value,
        "reason": reason,
    }
    if status in (Status.CANCELLED, Status.LATE_CANCELLED):
        fields["cancelled_at"] = start - timedelta(hours=5)
        fields["cancelled_by"] = "PATIENT"
        fields["status_changed_at"] = start - timedelta(hours=5)
    elif status is not Status.BOOKED:
        fields["status_changed_at"] = start + timedelta(minutes=minutes)
    fields.update(extra)
    appointment = Appointment(**fields)
    session.add(appointment)
    session.flush()
    return appointment
