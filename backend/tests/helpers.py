"""Small builders shared by unit, integration and API tests."""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic.config import Config
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.domain.errors import DomainError
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


def doctor_facts(
    *, doctor_id: int = 1, slot: int = 30, cap: int = 10, accepting: bool = True
) -> DoctorFacts:
    return DoctorFacts(
        id=doctor_id,
        name="Dr. Test",
        slot_length_min=slot,
        daily_cap=cap,
        accepting_bookings=accepting,
    )


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


def burst[T](jobs: Sequence[Callable[[], T]]) -> list[T | Exception]:
    """Run the jobs at the same instant on separate threads; exceptions are returned, not raised."""
    barrier = threading.Barrier(len(jobs))

    def run(job: Callable[[], T]) -> T | Exception:
        barrier.wait(timeout=10)
        try:
            return job()
        except Exception as exc:  # the test inspects every failure
            return exc

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(run, jobs))


def outcomes(results: Sequence[object]) -> Counter[str]:
    """OK for a success, the error code for a domain error, the class name for anything else."""
    return Counter(
        r.code.value
        if isinstance(r, DomainError)
        else type(r).__name__
        if isinstance(r, Exception)
        else "OK"
        for r in results
    )


class FakeDiag:
    def __init__(self, constraint: str | None) -> None:
        self.constraint_name = constraint


class FakeDriverError(Exception):
    """What psycopg raises: a `sqlstate` and a `diag.constraint_name`."""

    def __init__(self, state: str | None, constraint: str | None = None, text: str = "") -> None:
        super().__init__(text or f"driver error {state}")
        self.sqlstate = state
        self.diag = FakeDiag(constraint)


def db_error(
    state: str | None,
    constraint: str | None = None,
    cls: type[DBAPIError] = IntegrityError,
    params: dict[str, object] | None = None,
) -> DBAPIError:
    """A SQLAlchemy error wrapping a stand-in driver error with the given SQLSTATE."""
    return cls("INSERT INTO patients ...", params or {}, FakeDriverError(state, constraint))
