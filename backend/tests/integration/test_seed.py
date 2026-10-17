"""T-S03: the seed works on every weekday, is idempotent, and builds the scripted scenarios.

The scenario dates are all relative to an anchor, so a clash between two of them would only show on
some weekdays. Seeding once per weekday proves none of them collide (the exclusion constraints would
raise if two did).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.domain.model import Status
from app.domain.timeutil import ist_day_bounds
from app.persistence.models import (
    Appointment,
    Doctor,
    OverrideRow,
    Patient,
    WeeklyWindowRow,
)
from scripts.migrate_and_seed import main
from scripts.seed import ScenarioDates, scenario_dates, seed_database

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 22, 5, 0, tzinfo=UTC)
THURSDAY = date(2026, 10, 22)
WEEK = [date(2026, 10, 19) + timedelta(days=n) for n in range(7)]  # Monday to Sunday
TABLES = [
    "doctors",
    "weekly_windows",
    "availability_overrides",
    "override_windows",
    "patients",
    "appointments",
    "app_meta",
]


def counts(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as session:
        return {
            table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608
            for table in TABLES
        }


def booked_on(session: Session, doctor_name: str, day: date) -> int:
    low, high = ist_day_bounds(day)
    doctor_id = session.scalar(select(Doctor.id).where(Doctor.name == doctor_name))
    return (
        session.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.status == Status.BOOKED.value,
                Appointment.start_at >= low,
                Appointment.start_at < high,
            )
        )
        or 0
    )


@pytest.mark.parametrize("anchor", WEEK, ids=[d.strftime("%a") for d in WEEK])
def test_seed_succeeds_on_every_weekday(
    session_factory: sessionmaker[Session], anchor: date
) -> None:
    with session_factory() as session, session.begin():
        seed_database(session, anchor, NOW)
    found = counts(session_factory)
    assert found["doctors"] == 2
    assert found["patients"] == 15
    assert found["appointments"] > 40
    assert found["app_meta"] == 3


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> ScenarioDates:
    with session_factory() as session, session.begin():
        return seed_database(session, THURSDAY, NOW)


def test_conflict_day_has_three_bookings_and_no_override(
    session_factory: sessionmaker[Session], seeded: ScenarioDates
) -> None:
    with session_factory() as session:
        assert booked_on(session, "Dr. Ananya Rao", seeded.conflict_day) == 3
        override = session.scalar(
            select(OverrideRow).where(OverrideRow.on_date == seeded.conflict_day)
        )
        assert override is None


def test_leave_day_is_an_override_with_one_orphaned_booking(
    session_factory: sessionmaker[Session], seeded: ScenarioDates
) -> None:
    with session_factory() as session:
        override = session.scalar(
            select(OverrideRow).where(OverrideRow.on_date == seeded.leave_day)
        )
        assert override is not None
        assert override.windows == []  # an override with no windows is a leave day
        assert booked_on(session, "Dr. Ananya Rao", seeded.leave_day) == 1


def test_extra_saturday_adds_a_day_the_weekly_pattern_does_not_have(
    session_factory: sessionmaker[Session], seeded: ScenarioDates
) -> None:
    with session_factory() as session:
        menon_id = session.scalar(select(Doctor.id).where(Doctor.name == "Dr. Vikram Menon"))
        weekly_saturdays = session.scalar(
            select(func.count())
            .select_from(WeeklyWindowRow)
            .where(WeeklyWindowRow.doctor_id == menon_id, WeeklyWindowRow.weekday == 5)
        )
        override = session.scalar(
            select(OverrideRow).where(OverrideRow.on_date == seeded.extra_saturday)
        )
    assert weekly_saturdays == 0
    assert override is not None
    assert [(w.start_min, w.end_min) for w in override.windows] == [(600, 780)]


def test_cap_day_has_five_of_six_and_three_free_slots(
    session_factory: sessionmaker[Session], seeded: ScenarioDates
) -> None:
    with session_factory() as session:
        menon = session.scalar(select(Doctor).where(Doctor.name == "Dr. Vikram Menon"))
        assert menon is not None
        assert menon.daily_cap == 6
        assert booked_on(session, "Dr. Vikram Menon", seeded.cap_day) == 5


def test_queue_day_has_the_eight_boundary_appointments(
    session_factory: sessionmaker[Session], seeded: ScenarioDates
) -> None:
    with session_factory() as session:
        assert booked_on(session, "Dr. Ananya Rao", seeded.queue_day) == 8


def test_kavita_is_flagged_and_rohan_is_not(
    session_factory: sessionmaker[Session], seeded: ScenarioDates
) -> None:
    window_start = NOW - timedelta(days=30)

    def strikes(phone: str) -> list[str]:
        with session_factory() as session:
            patient_id = session.scalar(select(Patient.id).where(Patient.phone == phone))
            rows = session.scalars(
                select(Appointment).where(
                    Appointment.patient_id == patient_id,
                    Appointment.status.in_([Status.NO_SHOW.value, Status.LATE_CANCELLED.value]),
                    Appointment.start_at >= window_start,
                )
            ).all()
            return sorted(row.status for row in rows)

    assert strikes("+919000000001") == ["LATE_CANCELLED", "NO_SHOW"]
    assert strikes("+919000000002") == ["NO_SHOW"]


@pytest.mark.parametrize("anchor", WEEK, ids=[d.strftime("%a") for d in WEEK])
def test_scenario_dates_follow_the_stated_weekdays(anchor: date) -> None:
    dates = scenario_dates(anchor)
    # (date, expected weekday with Monday = 0, the date must fall strictly after this one)
    expected = [
        (dates.conflict_day, 1, anchor),
        (dates.leave_day, 2, anchor + timedelta(days=7)),
        (dates.cap_day, 4, anchor),
        (dates.extra_saturday, 5, anchor),
        (dates.busy_monday, 0, anchor),
    ]
    for day, weekday, after in expected:
        assert day.weekday() == weekday
        assert day > after
    assert dates.queue_day.weekday() < 5
    assert dates.queue_day >= anchor


def test_if_empty_seeds_once_and_reset_restores(
    session_factory: sessionmaker[Session],
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T-S03: running --if-empty twice changes nothing; --reset brings back a wiped database."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ANCHOR_DATE", THURSDAY.isoformat())
    get_settings.cache_clear()
    try:
        assert main(["--if-empty"]) == 0
        first = counts(session_factory)
        assert first["doctors"] == 2

        assert main(["--if-empty"]) == 0
        assert counts(session_factory) == first
        assert "left untouched" in capsys.readouterr().out

        with session_factory() as session, session.begin():
            session.execute(text("DELETE FROM appointments"))
        assert main(["--if-empty"]) == 0  # not empty (doctors exist), so nothing is re-seeded
        assert counts(session_factory)["appointments"] == 0

        assert main(["--reset", "--print-scenarios"]) == 0
        assert counts(session_factory) == first
        assert "flagged patient" in capsys.readouterr().out
    finally:
        get_settings.cache_clear()
