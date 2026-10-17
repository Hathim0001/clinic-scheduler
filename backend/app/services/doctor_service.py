"""Doctors: create, list, and change a doctor's details.

Changing the slot length is the one risky edit. Existing appointments and availability windows were
built on the old grid, so the change is refused while future bookings exist or while a window edge
would fall off the new grid (A-06). Lowering the daily cap never cancels anything (A-24): it only
stops further bookings on days that are already over the new cap.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ConflictError, ErrorCode, RuleViolation
from app.domain.timeutil import MAX_DATE, ist_date
from app.persistence import repositories as repo
from app.persistence.models import Doctor
from app.services.support import run
from app.services.views import DoctorView

SLOT_LENGTHS = (15, 30)
MAX_DAILY_CAP = 96  # 24 hours of 15-minute slots: more could never be booked


def _view(doctor: Doctor) -> DoctorView:
    return DoctorView(
        doctor.id, doctor.name, doctor.speciality, doctor.slot_length_min, doctor.daily_cap
    )


def _invalid(message: str, field: str) -> RuleViolation:
    return RuleViolation(ErrorCode.VALIDATION_ERROR, message, field=field)


def _check_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not 1 <= len(cleaned) <= 100:
        raise _invalid(f"The {field} must be 1 to 100 characters.", field)
    return cleaned


def _check_slot_length(value: int) -> int:
    if value not in SLOT_LENGTHS:
        raise _invalid("The slot length must be 15 or 30 minutes.", "slot_length_min")
    return value


def _check_cap(value: int) -> int:
    if not 1 <= value <= MAX_DAILY_CAP:
        raise _invalid(f"The daily cap must be between 1 and {MAX_DAILY_CAP}.", "daily_cap")
    return value


class DoctorService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list(self) -> list[DoctorView]:
        def work(session: Session) -> list[DoctorView]:
            return [_view(d) for d in session.scalars(select(Doctor).order_by(Doctor.id))]

        return run(self._factory, work)

    def get(self, doctor_id: int) -> DoctorView:
        return run(self._factory, lambda session: _view(repo.get_doctor(session, doctor_id)))

    def create(
        self, name: str, speciality: str, slot_length_min: int, daily_cap: int
    ) -> DoctorView:
        doctor = Doctor(
            name=_check_text(name, "name"),
            speciality=_check_text(speciality, "speciality"),
            slot_length_min=_check_slot_length(slot_length_min),
            daily_cap=_check_cap(daily_cap),
        )

        def work(session: Session) -> DoctorView:
            session.add(doctor)
            session.flush()
            return _view(doctor)

        return run(self._factory, work)

    def update(
        self,
        doctor_id: int,
        now: datetime,
        *,
        name: str | None = None,
        speciality: str | None = None,
        daily_cap: int | None = None,
        slot_length_min: int | None = None,
    ) -> DoctorView:
        """Change the given fields; None leaves a field as it is."""

        def work(session: Session) -> DoctorView:
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            if name is not None:
                doctor.name = _check_text(name, "name")
            if speciality is not None:
                doctor.speciality = _check_text(speciality, "speciality")
            if daily_cap is not None:
                doctor.daily_cap = _check_cap(daily_cap)
            if slot_length_min is not None and slot_length_min != doctor.slot_length_min:
                _check_slot_length(slot_length_min)
                _require_slot_length_change_is_safe(session, doctor, slot_length_min, now)
                doctor.slot_length_min = slot_length_min
            session.flush()
            return _view(doctor)

        return run(self._factory, work)


def _require_slot_length_change_is_safe(
    session: Session, doctor: Doctor, new_length: int, now: datetime
) -> None:
    future = repo.future_booked(session, doctor.id, now)
    if future:
        raise ConflictError(
            ErrorCode.SLOT_LENGTH_LOCKED,
            f"{doctor.name} has {len(future)} future booked appointment(s) made on the "
            f"{doctor.slot_length_min}-minute grid. Move or cancel them before changing the "
            "slot length.",
            reason="FUTURE_APPOINTMENTS",
            appointments=len(future),
        )
    edges = [(w.start_min, w.end_min) for w in repo.weekly_windows(session, doctor.id)]
    for override in repo.overrides_between(session, doctor.id, ist_date(now), MAX_DATE):
        edges.extend((w.start_min, w.end_min) for w in override.windows)
    if any(start % new_length or end % new_length for start, end in edges):
        raise ConflictError(
            ErrorCode.SLOT_LENGTH_LOCKED,
            f"Some of {doctor.name}'s availability windows do not fall on a {new_length}-minute "
            "grid. Adjust the windows first.",
            reason="WINDOWS_OFF_GRID",
        )
