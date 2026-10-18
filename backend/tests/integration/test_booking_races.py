"""Races between real database connections (T-B12, T-X14 style bursts for bookings).

Each burst releases all its threads at once through a barrier, so the transactions genuinely
overlap. The services must give one deterministic outcome per race, never a 5xx-shaped exception
such as a deadlock, and the database invariants must hold afterwards.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.domain.errors import DomainError, ErrorCode
from app.domain.model import CancelledBy, Status
from app.services.views import BookCommand
from tests.factories import add_appointment, add_doctor, add_patient, add_weekly
from tests.helpers import burst, ist, outcomes
from tests.integration.conftest import NOW, Clinic, at

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]

THREADS = 10  # the connection pool holds 5 + 5 overflow


def add_patients(clinic: Clinic, count: int) -> list[int]:
    with clinic.factory() as session, session.begin():
        return [add_patient(session, 10 + n).id for n in range(count)]


def assert_invariants(clinic: Clinic) -> None:
    """No two active appointments of a doctor or patient overlap; no day is over the cap."""
    with clinic.factory() as session:
        for column in ("doctor_id", "patient_id"):
            overlapping = session.execute(
                text(
                    f"""
                    SELECT a.id, b.id FROM appointments a JOIN appointments b
                      ON a.{column} = b.{column} AND a.id < b.id
                     AND tstzrange(a.start_at, a.end_at) && tstzrange(b.start_at, b.end_at)
                    WHERE a.status IN ('BOOKED','COMPLETED','NO_SHOW')
                      AND b.status IN ('BOOKED','COMPLETED','NO_SHOW')
                    """  # noqa: S608 - the column name is one of two literals above
                )
            ).all()
            assert overlapping == [], f"overlapping appointments by {column}: {overlapping}"
        over_cap = session.execute(
            text(
                """
                SELECT d.id, count(*) FROM appointments a JOIN doctors d ON d.id = a.doctor_id
                WHERE a.status IN ('BOOKED','COMPLETED','NO_SHOW')
                GROUP BY d.id, d.daily_cap, (a.start_at AT TIME ZONE 'Asia/Kolkata')::date
                HAVING count(*) > d.daily_cap
                """
            )
        ).all()
        assert over_cap == [], f"doctor days over the cap: {over_cap}"


def book_job(clinic: Clinic, doctor: int, patient: int, start: datetime) -> Callable[[], object]:
    command = BookCommand(doctor, patient, start, "Check-up")
    return lambda: clinic.booking.book(command, NOW)


def leave_job(clinic: Clinic, day: date) -> Callable[[], object]:
    return lambda: clinic.availability.put_override(clinic.rao, day, [], None, False, NOW)


def reschedule_job(clinic: Clinic, appointment_id: int, start: datetime) -> Callable[[], object]:
    return lambda: clinic.booking.reschedule(appointment_id, start, None, None, NOW)


def test_ten_patients_racing_for_one_slot_give_exactly_one_booking(clinic: Clinic) -> None:
    """T-B12: the losers are told SLOT_TAKEN, none of them gets a deadlock."""
    patients = add_patients(clinic, THREADS)
    for round_number in range(5):
        start = at(9) + timedelta(minutes=30 * round_number)
        results = burst([book_job(clinic, clinic.rao, p, start) for p in patients])
        assert outcomes(results) == {"OK": 1, "SLOT_TAKEN": THREADS - 1}
    assert len(clinic.appointments()) == 5
    assert_invariants(clinic)


def test_the_daily_cap_holds_when_many_book_different_slots_at_once(clinic: Clinic) -> None:
    """Without the doctor-row lock all ten got through a cap of three (plan 21.4)."""
    with clinic.factory() as session, session.begin():
        capped = add_doctor(session, name="Dr. Capped", slot=15, cap=3)
        add_weekly(session, capped.id, 0, 540, 780)
    patients = add_patients(clinic, THREADS)
    starts = [at(9) + timedelta(minutes=15 * n) for n in range(THREADS)]
    results = burst(
        [book_job(clinic, capped.id, p, s) for p, s in zip(patients, starts, strict=True)]
    )
    assert outcomes(results) == {"OK": 3, "DAILY_CAP_REACHED": THREADS - 3}
    assert_invariants(clinic)


def test_one_patient_cannot_win_two_doctors_at_the_same_time(clinic: Clinic) -> None:
    """Two doctors are locked in turn, then the same patient row: no deadlock, one winner."""
    jobs = [
        book_job(clinic, doctor, clinic.asha, at(10))
        for doctor in (clinic.rao, clinic.menon) * (THREADS // 2)
    ]
    results = burst(jobs)
    counts = outcomes(results)
    assert counts["OK"] == 1
    assert set(counts) <= {"OK", "PATIENT_OVERLAP", "SLOT_TAKEN"}
    assert_invariants(clinic)


def test_only_one_of_several_cancellations_of_an_appointment_wins(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        appointment_id = add_appointment(session, clinic.rao, clinic.asha, at(12)).id
    results = burst(
        [lambda: clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, NOW)] * THREADS
    )
    assert outcomes(results) == {"OK": 1, "INVALID_TRANSITION": THREADS - 1}
    assert clinic.appointment(appointment_id).status == Status.CANCELLED.value


def test_a_cancel_racing_a_complete_has_one_winner(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        appointment_id = add_appointment(session, clinic.rao, clinic.asha, at(9)).id
    now = at(9, 5)  # already started: all three are allowed, but only the first one can win
    results = burst(
        [
            lambda: clinic.booking.complete(appointment_id, now),
            lambda: clinic.booking.no_show(appointment_id, now),
            lambda: clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, now),
        ]
    )
    assert outcomes(results)["OK"] == 1
    assert clinic.appointment(appointment_id).status in {"COMPLETED", "NO_SHOW", "LATE_CANCELLED"}


def test_reschedules_into_one_slot_let_one_through_and_roll_the_rest_back(clinic: Clinic) -> None:
    patients = add_patients(clinic, 5)
    with clinic.factory() as session, session.begin():
        # all two hours or more ahead of NOW (08:00), so none of them is a late move that would be
        # asked about first; the answers then depend only on who wins the race for the target
        olds = [
            add_appointment(session, clinic.rao, patient, at(10) + timedelta(minutes=30 * n)).id
            for n, patient in enumerate(patients)
        ]
    target = at(12, 30)
    results = burst([reschedule_job(clinic, old_id, target) for old_id in olds])
    assert outcomes(results) == {"OK": 1, "SLOT_TAKEN": len(olds) - 1}
    booked = [a for a in clinic.appointments() if a.status == "BOOKED" and a.start_at == target]
    assert len(booked) == 1
    still_booked_old = [a for a in clinic.appointments() if a.id in olds and a.status == "BOOKED"]
    assert len(still_booked_old) == len(olds) - 1  # the losers were rolled back, not cancelled
    assert_invariants(clinic)


def test_two_patients_swapping_slots_never_deadlock_or_overlap(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        first = add_appointment(session, clinic.rao, clinic.asha, at(10)).id
        second = add_appointment(session, clinic.rao, clinic.ravi, at(10, 30)).id
    results = burst(
        [reschedule_job(clinic, first, at(10, 30)), reschedule_job(clinic, second, at(10))]
    )
    # Each wants the other's slot. Whichever runs second finds the first one's result in place.
    assert set(outcomes(results)) <= {"OK", "SLOT_TAKEN", "INVALID_TRANSITION"}
    assert_invariants(clinic)


def test_booking_a_slot_while_it_is_being_cancelled_is_consistent(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        appointment_id = add_appointment(session, clinic.rao, clinic.asha, at(12)).id
    results = burst(
        [
            lambda: clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, NOW),
            book_job(clinic, clinic.rao, clinic.ravi, at(12)),
        ]
    )
    counts = outcomes(results)
    # Either the booking ran after the cancellation commit (both succeed) or before it (it is
    # told the slot is taken); both are correct. Anything else would be a bug.
    assert counts in ({"OK": 2}, {"OK": 1, "SLOT_TAKEN": 1})
    assert_invariants(clinic)


def test_a_booking_racing_a_leave_day_never_leaves_an_unflagged_orphan(clinic: Clinic) -> None:
    """T-O05: both change Dr. Rao's day, so they queue on the doctor row. Exactly one wins: either
    the booking commits and the leave day is refused with the list, or the leave day commits and
    the booking is told the doctor is not available."""
    mondays_to_fridays = [date(2026, 11, 9) + timedelta(days=n) for n in range(28)]
    days = [day for day in mondays_to_fridays if day.weekday() < 5][:20]
    for day in days:
        start = ist(day.year, day.month, day.day, 10)
        booked, left = burst(
            [book_job(clinic, clinic.rao, clinic.asha, start), leave_job(clinic, day)]
        )
        assert isinstance(booked, Exception) != isinstance(left, Exception), (day, booked, left)
        if isinstance(left, DomainError):
            assert left.code is ErrorCode.AVAILABILITY_CONFLICTS
        else:
            assert isinstance(booked, DomainError)
            assert booked.code is ErrorCode.OUTSIDE_AVAILABILITY
    for day in days:  # nothing was left outside the doctor's hours
        assert (
            clinic.availability.day_schedule(clinic.rao, day, None, NOW).outside_availability == ()
        )
    assert_invariants(clinic)


def register_job(clinic: Clinic, name: str, phone: str) -> Callable[[], object]:
    return lambda: clinic.patients.create(name, phone, date(1990, 1, 1), NOW)


def test_ten_simultaneous_registrations_of_one_phone_give_one_patient(clinic: Clinic) -> None:
    """T-X14: the losers get PHONE_TAKEN whether they lose at the check or at the constraint."""
    formats = ["98765 43210", "+91-98765-43210", "09876543210", "919876543210", "9876543210"]
    results = burst(
        [register_job(clinic, f"Patient {n}", formats[n % len(formats)]) for n in range(THREADS)]
    )
    assert outcomes(results) == {"OK": 1, "PHONE_TAKEN": THREADS - 1}
