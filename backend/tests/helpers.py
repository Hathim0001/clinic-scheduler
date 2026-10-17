"""Small builders shared by unit, integration and API tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic.config import Config

from app.domain.model import AppointmentFacts, DoctorFacts, SlotContext, Status, Window
from app.domain.timeutil import IST

BACKEND_DIR = Path(__file__).resolve().parent.parent


def ist(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0, micro: int = 0
) -> datetime:
    """An India wall-clock time as an aware UTC instant: ist(2026, 11, 2, 9, 0) is 09:00 IST."""
    return datetime(year, month, day, hour, minute, second, micro, tzinfo=IST).astimezone(UTC)


def hm(text: str) -> int:
    """'09:30' -> 570 minutes since midnight ('24:00' -> 1440)."""
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def doctor_facts(*, doctor_id: int = 1, slot: int = 30, cap: int = 10) -> DoctorFacts:
    return DoctorFacts(id=doctor_id, name="Dr. Test", slot_length_min=slot, daily_cap=cap)


def appt_facts(
    start: datetime,
    *,
    doctor: int = 1,
    patient: int = 1,
    minutes: int = 30,
    status: Status = Status.BOOKED,
    appointment_id: int = 0,
) -> AppointmentFacts:
    return AppointmentFacts(
        id=appointment_id,
        doctor_id=doctor,
        patient_id=patient,
        start_at=start,
        end_at=start + timedelta(minutes=minutes),
        status=status,
    )


def slot_ctx(
    *,
    now: datetime,
    doctor: DoctorFacts | None = None,
    windows: Sequence[tuple[int, int]] = ((540, 780),),
    doctor_appts: Sequence[AppointmentFacts] = (),
    patient_appts: Sequence[AppointmentFacts] = (),
) -> SlotContext:
    """A slot context. The default is a 30-minute doctor working 09:00-13:00."""
    return SlotContext(
        doctor=doctor or doctor_facts(),
        windows=tuple(Window(start, end) for start, end in windows),
        doctor_appts=tuple(doctor_appts),
        patient_appts=tuple(patient_appts),
        now=now,
    )


def alembic_config(database_url: str) -> Config:
    """Alembic config pointing at an explicit database (the tests never read DATABASE_URL)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config
