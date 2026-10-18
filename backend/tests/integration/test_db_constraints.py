"""T-S02: every constraint in the schema rejects its bad row, and names itself when it does.

The services check the rules before they write. These tests prove the database would refuse the same
rows anyway, which is what keeps the invariants true under concurrency and against bugs in the
application code. Each statement runs in its own transaction so the error can be inspected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.model import Status
from app.persistence.db_errors import constraint_name, sqlstate
from tests.factories import (
    add_appointment,
    add_doctor,
    add_override,
    add_patient,
    add_weekly,
)
from tests.helpers import ist

pytestmark = pytest.mark.integration

START = ist(2026, 11, 2, 11, 0)  # Monday 11:00 IST: the slot that is already booked in `world`
LATER = START + timedelta(hours=3)
HALF_HOUR = timedelta(minutes=30)

APPOINTMENT_INSERT = """
INSERT INTO appointments (doctor_id, patient_id, start_at, end_at, status, reason,
                          deposit_required_at_booking, deposit_confirmed,
                          cancelled_at, cancelled_by, status_changed_at, rescheduled_to_id, slots)
VALUES (:doctor, :patient, :start, :end, :status, :reason, :dep_required, :dep_confirmed,
        :cancelled_at, :cancelled_by, :changed_at, :moved_to, :slots)
"""


@dataclass(frozen=True)
class World:
    d15: int  # 15-minute doctor with a Monday window and an override on 9 Nov
    d30: int  # 30-minute doctor, booked 11:00-11:30 by p1
    p1: int
    p2: int
    booked: int  # id of p1's appointment


@pytest.fixture
def world(session_factory: sessionmaker[Session]) -> World:
    with session_factory() as session, session.begin():
        d15 = add_doctor(session, name="Dr. Fifteen", slot=15, cap=20)
        d30 = add_doctor(session, name="Dr. Thirty", slot=30, cap=10)
        p1 = add_patient(session, 1)
        p2 = add_patient(session, 2)
        booked = add_appointment(session, d30.id, p1.id, START)
        add_weekly(session, d15.id, 0, 540, 780)
        add_override(session, d15.id, date(2026, 11, 9), [(600, 720)])
        return World(d15.id, d30.id, p1.id, p2.id, booked.id)


def run(engine: Engine, sql: str, **params: Any) -> tuple[str | None, str | None]:
    """Execute one statement in its own transaction; return (sqlstate, constraint) of its error."""
    try:
        with engine.begin() as connection:
            connection.execute(text(sql), params)
    except DBAPIError as exc:
        return sqlstate(exc), constraint_name(exc)
    return None, None


def appointment(world: World, **override: Any) -> dict[str, Any]:
    """Parameters for APPOINTMENT_INSERT: a valid BOOKED 30-minute appointment, then overrides."""
    params: dict[str, Any] = {
        "doctor": world.d30,
        "patient": world.p2,
        "start": LATER,
        "end": LATER + HALF_HOUR,
        "status": "BOOKED",
        "reason": "Fever",
        "dep_required": False,
        "dep_confirmed": False,
        "cancelled_at": None,
        "cancelled_by": None,
        "changed_at": None,
        "moved_to": None,
        "slots": 1,
    }
    params.update(override)
    return params


# (sql, parameters, expected SQLSTATE, expected constraint name or None when it is auto-named)
Case = tuple[str, Callable[[World], dict[str, Any]], str, str | None]

WINDOW_AND_PEOPLE_CASES: dict[str, Case] = {
    "weekly window overlapping another": (
        "INSERT INTO weekly_windows (doctor_id, weekday, start_min, end_min) "
        "VALUES (:d, 0, 600, 660)",
        lambda w: {"d": w.d15},
        "23P01",
        "weekly_windows_no_overlap",
    ),
    "weekly window ending before it starts": (
        "INSERT INTO weekly_windows (doctor_id, weekday, start_min, end_min) "
        "VALUES (:d, 1, 600, 600)",
        lambda w: {"d": w.d15},
        "23514",
        None,
    ),
    "weekly window ending after 24:00": (
        "INSERT INTO weekly_windows (doctor_id, weekday, start_min, end_min) "
        "VALUES (:d, 1, 1380, 1441)",
        lambda w: {"d": w.d15},
        "23514",
        None,
    ),
    "second override for the same date": (
        "INSERT INTO availability_overrides (doctor_id, on_date) VALUES (:d, '2026-11-09')",
        lambda w: {"d": w.d15},
        "23505",
        "overrides_doctor_date_key",
    ),
    "override date before 2000": (
        "INSERT INTO availability_overrides (doctor_id, on_date) VALUES (:d, '1999-01-01')",
        lambda w: {"d": w.d15},
        "23514",
        None,
    ),
    "override windows overlapping each other": (
        "INSERT INTO override_windows (override_id, start_min, end_min) "
        "SELECT id, 700, 800 FROM availability_overrides LIMIT 1",
        lambda w: {},
        "23P01",
        "override_windows_no_overlap",
    ),
    "phone that does not start with 6 to 9": (
        "INSERT INTO patients (name, phone, date_of_birth) "
        "VALUES ('Bad', '+911234567890', '2000-01-01')",
        lambda w: {},
        "23514",
        "patients_phone_check",
    ),
    "phone written in Arabic-Indic digits": (
        "INSERT INTO patients (name, phone, date_of_birth) "
        "VALUES ('Bad', '+91' || chr(1641) || chr(1640) || chr(1639) || chr(1638) || chr(1637) "
        "|| chr(1636) || chr(1635) || chr(1634) || chr(1633) || chr(1632), '2000-01-01')",
        lambda w: {},
        "23514",
        "patients_phone_check",
    ),
    "date of birth in 1800": (
        "INSERT INTO patients (name, phone, date_of_birth) "
        "VALUES ('Old', '+917000000001', '1800-01-01')",
        lambda w: {},
        "23514",
        "patients_date_of_birth_check",
    ),
    "empty patient name": (
        "INSERT INTO patients (name, phone, date_of_birth) "
        "VALUES ('', '+917000000002', '2000-01-01')",
        lambda w: {},
        "23514",
        "patients_name_check",
    ),
    "doctor with a 20-minute slot": (
        "INSERT INTO doctors (name, speciality, slot_length_min, daily_cap) "
        "VALUES ('x', 'y', 20, 5)",
        lambda w: {},
        "23514",
        "doctors_slot_length_min_check",
    ),
    "doctor with a daily cap of 0": (
        "INSERT INTO doctors (name, speciality, slot_length_min, daily_cap) "
        "VALUES ('x', 'y', 15, 0)",
        lambda w: {},
        "23514",
        "doctors_daily_cap_check",
    ),
    "doctor with a daily cap of 97": (
        "INSERT INTO doctors (name, speciality, slot_length_min, daily_cap) "
        "VALUES ('x', 'y', 15, 97)",
        lambda w: {},
        "23514",
        "doctors_daily_cap_check",
    ),
}


@pytest.mark.parametrize(
    "case", WINDOW_AND_PEOPLE_CASES.values(), ids=WINDOW_AND_PEOPLE_CASES.keys()
)
def test_bad_window_patient_and_doctor_rows_are_rejected(
    engine: Engine, world: World, case: Case
) -> None:
    """T-S02"""
    sql, make_params, state, constraint = case
    got_state, got_constraint = run(engine, sql, **make_params(world))
    assert got_state == state
    if constraint is not None:
        assert got_constraint == constraint


APPOINTMENT_CASES: dict[str, tuple[Callable[[World], dict[str, Any]], str, str | None]] = {
    "45-minute appointment": (
        lambda w: appointment(w, end=LATER + timedelta(minutes=45)),
        "23514",
        "appt_whole_slots",
    ),
    "a one-slot visit that lasts an hour": (
        lambda w: appointment(w, end=LATER + timedelta(hours=1)),
        "23514",
        "appt_whole_slots",
    ),
    "a two-slot visit of an odd length": (
        lambda w: appointment(w, slots=2, end=LATER + timedelta(minutes=45)),
        "23514",
        "appt_whole_slots",
    ),
    "zero slots": (lambda w: appointment(w, slots=0), "23514", "appointments_slots_check"),
    "five slots": (
        lambda w: appointment(w, slots=5, end=LATER + timedelta(minutes=150)),
        "23514",
        "appointments_slots_check",
    ),
    "unknown status": (
        lambda w: appointment(w, status="MAYBE", changed_at=LATER),
        "23514",
        "appt_status_valid",
    ),
    "booked row that carries a cancellation time": (
        lambda w: appointment(w, cancelled_at=LATER, cancelled_by="PATIENT"),
        "23514",
        "appt_cancel_stamp",
    ),
    "cancelled row without a cancellation time": (
        lambda w: appointment(w, status="CANCELLED", changed_at=LATER),
        "23514",
        "appt_cancel_stamp",
    ),
    "cancellation time without who cancelled": (
        lambda w: appointment(w, status="CANCELLED", cancelled_at=LATER, changed_at=LATER),
        "23514",
        "appt_cancel_actor",
    ),
    "cancelled by somebody other than patient or clinic": (
        lambda w: appointment(
            w, status="CANCELLED", cancelled_at=LATER, cancelled_by="NOBODY", changed_at=LATER
        ),
        "23514",
        "appt_cancel_actor_val",
    ),
    "late cancellation by the clinic": (
        lambda w: appointment(
            w, status="LATE_CANCELLED", cancelled_at=LATER, cancelled_by="CLINIC", changed_at=LATER
        ),
        "23514",
        "appt_late_is_patient",
    ),
    "no-show without a status change time": (
        lambda w: appointment(w, status="NO_SHOW"),
        "23514",
        "appt_changed_stamp",
    ),
    "deposit required at booking but not confirmed": (
        lambda w: appointment(w, dep_required=True, dep_confirmed=False),
        "23514",
        "appt_deposit_ack",
    ),
    "start before the year 2000": (
        lambda w: appointment(w, start=ist(1999, 1, 4, 11), end=ist(1999, 1, 4, 11, 30)),
        "23514",
        "appt_time_bounds",
    ),
    "reason longer than 500 characters": (
        lambda w: appointment(w, reason="x" * 501),
        "23514",
        None,
    ),
    "unknown doctor": (
        lambda w: appointment(w, doctor=999_999),
        "23503",
        "appointments_doctor_id_fkey",
    ),
    "booked row pointing at a reschedule target": (
        lambda w: appointment(w, moved_to=w.booked),
        "23514",
        "appt_moved_only_if_cancelled",
    ),
    "same doctor, overlapping slot (rule 2)": (
        lambda w: appointment(
            w, start=START + timedelta(minutes=15), end=START + timedelta(minutes=45)
        ),
        "23P01",
        "no_doctor_overlap",
    ),
    "same patient, other doctor, overlapping slot (rule 3)": (
        lambda w: appointment(
            w,
            doctor=w.d15,
            patient=w.p1,
            start=START + timedelta(minutes=15),
            end=START + timedelta(minutes=30),
        ),
        "23P01",
        "no_patient_overlap",
    ),
}


@pytest.mark.parametrize("case", APPOINTMENT_CASES.values(), ids=APPOINTMENT_CASES.keys())
def test_bad_appointment_rows_are_rejected(
    engine: Engine,
    world: World,
    case: tuple[Callable[[World], dict[str, Any]], str, str | None],
) -> None:
    """T-S02"""
    make_params, state, constraint = case
    got_state, got_constraint = run(engine, APPOINTMENT_INSERT, **make_params(world))
    assert got_state == state
    if constraint is not None:
        assert got_constraint == constraint


def test_a_valid_appointment_is_accepted(engine: Engine, world: World) -> None:
    assert run(engine, APPOINTMENT_INSERT, **appointment(world)) == (None, None)


@pytest.mark.parametrize(
    ("slots", "minutes"), [(2, 30), (2, 60), (3, 45), (3, 90), (4, 60), (4, 120)]
)
def test_a_visit_of_several_slots_is_accepted(
    engine: Engine, world: World, slots: int, minutes: int
) -> None:
    params = appointment(world, slots=slots, end=LATER + timedelta(minutes=minutes))
    assert run(engine, APPOINTMENT_INSERT, **params) == (None, None)


def test_two_patients_may_share_a_phone_number(engine: Engine, world: World) -> None:
    sql = (
        "INSERT INTO patients (name, phone, date_of_birth) "
        "VALUES ('Sibling', '+919000000001', '2001-02-03')"
    )
    assert run(engine, sql) == (None, None)


def test_adjacent_appointments_do_not_overlap(engine: Engine, world: World) -> None:
    """Ranges are half-open: 11:30-12:00 may follow the booked 11:00-11:30."""
    params = appointment(world, start=START + HALF_HOUR, end=START + 2 * HALF_HOUR)
    assert run(engine, APPOINTMENT_INSERT, **params) == (None, None)


def test_a_cancelled_slot_can_be_booked_again(
    engine: Engine, world: World, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE appointments SET status = 'CANCELLED', cancelled_at = :at, "
                "cancelled_by = 'PATIENT', status_changed_at = :at WHERE id = :id"
            ),
            {"at": START - timedelta(hours=3), "id": world.booked},
        )
    params = appointment(world, start=START, end=START + HALF_HOUR)
    assert run(engine, APPOINTMENT_INSERT, **params) == (None, None)


def test_a_no_show_still_blocks_its_slot(
    engine: Engine, world: World, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session, session.begin():
        add_appointment(session, world.d30, world.p2, LATER, status=Status.NO_SHOW)
    params = appointment(world, patient=world.p1, start=LATER, end=LATER + HALF_HOUR)
    assert run(engine, APPOINTMENT_INSERT, **params) == ("23P01", "no_doctor_overlap")


def test_two_cancelled_rows_cannot_point_at_the_same_reschedule_target(
    engine: Engine, world: World, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session, session.begin():
        add_appointment(
            session,
            world.d30,
            world.p2,
            LATER,
            status=Status.CANCELLED,
            rescheduled_to_id=world.booked,
        )
    second = appointment(
        world,
        patient=world.p1,
        start=LATER + timedelta(hours=1),
        end=LATER + timedelta(hours=1, minutes=30),
        status="CANCELLED",
        cancelled_at=LATER,
        cancelled_by="PATIENT",
        changed_at=LATER,
        moved_to=world.booked,
    )
    assert run(engine, APPOINTMENT_INSERT, **second) == ("23505", "appt_moved_target_unique")


def test_cancel_first_then_insert_commits_but_insert_first_fails(
    engine: Engine, world: World
) -> None:
    """Rescheduling must cancel the old row before inserting the new one.

    Moving the patient from the doctor's 11:00-11:30 slot to an overlapping 11:15-11:45 slot is only
    legal once the old row has stopped being active; inserting first hits the patient constraint.
    """
    overlapping = appointment(
        world,
        doctor=world.d15,
        patient=world.p1,
        start=START + timedelta(minutes=15),
        end=START + timedelta(minutes=30),
    )
    # insert first: refused
    assert run(engine, APPOINTMENT_INSERT, **overlapping) == ("23P01", "no_patient_overlap")

    # cancel first, then insert, in one transaction: accepted
    cancel_then_insert(engine, world.booked, overlapping)


def cancel_then_insert(engine: Engine, appointment_id: int, insert_params: dict[str, Any]) -> None:
    """The shape of a reschedule: cancel the old row and insert the new one in ONE transaction."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE appointments SET status = 'CANCELLED', cancelled_at = :at, "
                "cancelled_by = 'PATIENT', status_changed_at = :at WHERE id = :id"
            ),
            {"at": START - timedelta(hours=3), "id": appointment_id},
        )
        connection.execute(text(APPOINTMENT_INSERT), insert_params)


def test_a_failed_reschedule_leaves_the_old_row_untouched(
    engine: Engine, world: World, session_factory: sessionmaker[Session]
) -> None:
    """The cancel and the insert share a transaction, so a refused insert undoes the cancel."""
    with session_factory() as session, session.begin():
        add_appointment(session, world.d30, world.p2, START + HALF_HOUR)  # occupies the target
    clash = appointment(world, patient=world.p1, start=START + HALF_HOUR, end=START + 2 * HALF_HOUR)
    with pytest.raises(DBAPIError):
        cancel_then_insert(engine, world.booked, clash)
    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status FROM appointments WHERE id = :id"), {"id": world.booked}
        ).scalar_one()
    assert status == "BOOKED"


def test_a_window_may_end_at_midnight(engine: Engine, world: World) -> None:
    sql = (
        "INSERT INTO weekly_windows (doctor_id, weekday, start_min, end_min) "
        "VALUES (:d, 3, 1380, 1440)"
    )
    assert run(engine, sql, d=world.d15) == (None, None)


def test_adjacent_weekly_windows_are_allowed(engine: Engine, world: World) -> None:
    sql = (
        "INSERT INTO weekly_windows (doctor_id, weekday, start_min, end_min) "
        "VALUES (:d, 0, 780, 840)"
    )
    assert run(engine, sql, d=world.d15) == (None, None)
