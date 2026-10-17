"""Free slots and the day schedule: both are built on the booking predicate (T-O06, T-P02)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.errors import ErrorCode, NotFoundError
from app.domain.model import CancelledBy, Status, UnavailableReason
from app.services.views import BookCommand, SlotState
from tests.factories import add_appointment, add_doctor, add_override, add_patient, add_weekly
from tests.helpers import ist
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def test_the_free_slots_of_the_worked_example(clinic: Clinic) -> None:
    """Plan 21.3: an override of 11:00-13:00, a booking at 11:30, and the clock at 10:05."""
    with clinic.factory() as session, session.begin():
        add_override(session, clinic.rao, MONDAY, [(660, 780)])
        add_appointment(session, clinic.rao, clinic.ravi, at(11, 30))
    view = clinic.availability.free_slots(clinic.rao, MONDAY, None, at(10, 5))
    assert view.slots == (at(11), at(12), at(12, 30))
    assert view.source == "OVERRIDE"
    assert [(w.start_min, w.end_min) for w in view.windows] == [(660, 780)]
    assert view.slot_length_min == 30
    assert view.unavailable_reason is None


def test_a_normal_day_lists_every_slot_of_the_weekly_window(clinic: Clinic) -> None:
    view = clinic.availability.free_slots(clinic.rao, MONDAY, None, NOW)
    assert len(view.slots) == 8
    assert (view.slots[0], view.slots[-1]) == (at(9), at(12, 30))
    assert view.source == "WEEKLY"


def test_slots_that_have_started_are_not_offered(clinic: Clinic) -> None:
    view = clinic.availability.free_slots(clinic.rao, MONDAY, None, at(10, 45))
    assert view.slots == (at(11), at(11, 30), at(12), at(12, 30))


def test_a_leave_day_has_no_slots_and_says_why(clinic: Clinic) -> None:
    """T-O06"""
    with clinic.factory() as session, session.begin():
        add_override(session, clinic.rao, MONDAY, [])
    view = clinic.availability.free_slots(clinic.rao, MONDAY, None, NOW)
    assert view.slots == ()
    assert (view.source, view.unavailable_reason) == ("OVERRIDE", UnavailableReason.NO_AVAILABILITY)


def test_a_day_without_working_hours_says_so(clinic: Clinic) -> None:
    saturday = date(2026, 11, 7)
    view = clinic.availability.free_slots(clinic.rao, saturday, None, NOW)
    assert (view.source, view.slots) == ("WEEKLY", ())
    assert view.unavailable_reason is UnavailableReason.NO_AVAILABILITY


def test_a_full_day_says_fully_booked_or_capped(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        roomy = add_doctor(session, name="Dr. Roomy", slot=30, cap=96)
        add_weekly(session, roomy.id, 0, 540, 600)  # two slots
        for start in (at(9), at(9, 30)):
            add_appointment(session, roomy.id, clinic.ravi, start)
        patients = [add_patient(session, 20 + n).id for n in range(7)]
        for index in range(6):  # Dr. Rao has a cap of 6
            start = at(9) + timedelta(minutes=30 * index)
            add_appointment(session, clinic.rao, patients[index], start)
        add_appointment(session, clinic.rao, patients[6], at(12), status=Status.CANCELLED)
    assert (
        clinic.availability.free_slots(roomy.id, MONDAY, None, NOW).unavailable_reason
        is UnavailableReason.FULLY_BOOKED
    )
    capped = clinic.availability.free_slots(clinic.rao, MONDAY, None, NOW)
    assert (capped.slots, capped.unavailable_reason) == ((), UnavailableReason.DAILY_CAP_REACHED)


@pytest.mark.parametrize(
    ("day", "reason"),
    [
        (date(2026, 10, 30), UnavailableReason.DATE_IN_PAST),
        (date(2027, 1, 4), UnavailableReason.DATE_TOO_FAR),
    ],
)
def test_dates_outside_the_booking_window_say_so(
    clinic: Clinic, day: date, reason: UnavailableReason
) -> None:
    view = clinic.availability.free_slots(clinic.rao, day, None, NOW)
    assert (view.slots, view.unavailable_reason) == ((), reason)


def test_a_patient_is_not_offered_times_they_are_already_busy(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.menon, clinic.asha, at(10, 15), minutes=15)
    for_asha = clinic.availability.free_slots(clinic.rao, MONDAY, clinic.asha, NOW)
    for_ravi = clinic.availability.free_slots(clinic.rao, MONDAY, clinic.ravi, NOW)
    assert at(10) not in for_asha.slots
    assert at(10) in for_ravi.slots
    assert len(for_asha.slots) == len(for_ravi.slots) - 1


def test_unknown_doctors_and_patients_are_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError) as raised:
        clinic.availability.free_slots(999, MONDAY, None, NOW)
    assert raised.value.code is ErrorCode.DOCTOR_NOT_FOUND
    with pytest.raises(NotFoundError) as raised:
        clinic.availability.free_slots(clinic.rao, MONDAY, 999, NOW)
    assert raised.value.code is ErrorCode.PATIENT_NOT_FOUND


def test_every_offered_slot_is_accepted_by_booking(clinic: Clinic) -> None:
    """T-P02: offer and accept cannot disagree. Each booking is undone before the next."""
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.ravi, at(10))
        add_appointment(session, clinic.rao, clinic.ravi, at(11), status=Status.NO_SHOW)
        add_appointment(session, clinic.menon, clinic.asha, at(12, 15), minutes=15)
    now = at(9, 10)
    offered = clinic.availability.free_slots(clinic.rao, MONDAY, clinic.asha, now).slots
    assert offered  # 09:30, 10:30, 11:30, 12:00 (12:30 overlaps nothing)
    for start in offered:
        booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, start, "Check"), now)
        clinic.booking.cancel(booked.id, CancelledBy.CLINIC, now)


def test_the_schedule_shows_every_slot_with_its_state(clinic: Clinic) -> None:
    now = at(10, 5)
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.ravi, at(9, 30), status=Status.COMPLETED)
        add_appointment(session, clinic.rao, clinic.asha, at(11))
    view = clinic.availability.day_schedule(clinic.rao, MONDAY, None, now)
    assert [(s.start_at, s.state) for s in view.slots] == [
        (at(9), SlotState.PAST),
        (at(9, 30), SlotState.BOOKED),  # a past appointment still shows as booked
        (at(10), SlotState.PAST),
        (at(10, 30), SlotState.FREE),
        (at(11), SlotState.BOOKED),
        (at(11, 30), SlotState.FREE),
        (at(12), SlotState.FREE),
        (at(12, 30), SlotState.FREE),
    ]
    booked = {s.start_at: s.appointment for s in view.slots if s.appointment}
    assert [(a.patient_name, a.status) for a in booked.values()] == [
        ("Ravi Kumar", Status.COMPLETED),
        ("Asha Iyer", Status.BOOKED),
    ]
    assert view.outside_availability == ()
    assert view.unavailable_reason is None


def test_a_reached_cap_shows_the_remaining_slots_as_capped(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        capped = add_doctor(session, name="Dr. Two", slot=30, cap=2)
        add_weekly(session, capped.id, 0, 540, 780)
        for start in (at(9), at(9, 30)):
            add_appointment(session, capped.id, clinic.ravi, start)
    view = clinic.availability.day_schedule(capped.id, MONDAY, None, NOW)
    states = [s.state for s in view.slots]
    assert states == [SlotState.BOOKED, SlotState.BOOKED] + [SlotState.CAPPED] * 6
    assert view.unavailable_reason is UnavailableReason.DAILY_CAP_REACHED


def test_the_schedule_marks_times_the_chosen_patient_is_busy(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.menon, clinic.asha, at(10), minutes=15)
    view = clinic.availability.day_schedule(clinic.rao, MONDAY, clinic.asha, NOW)
    assert {s.start_at: s.state for s in view.slots}[at(10)] is SlotState.BUSY
    view = clinic.availability.day_schedule(clinic.rao, MONDAY, None, NOW)
    assert {s.start_at: s.state for s in view.slots}[at(10)] is SlotState.FREE


def test_a_day_beyond_the_horizon_is_closed(clinic: Clinic) -> None:
    view = clinic.availability.day_schedule(clinic.rao, date(2027, 1, 4), None, NOW)
    assert {s.state for s in view.slots} == {SlotState.CLOSED}
    assert view.unavailable_reason is UnavailableReason.DATE_TOO_FAR


def test_bookings_outside_the_hours_are_listed_separately(clinic: Clinic) -> None:
    """A leave day that still has a booking must not look empty."""
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(10))
        add_appointment(session, clinic.rao, clinic.ravi, at(10, 30), status=Status.CANCELLED)
        add_override(session, clinic.rao, MONDAY, [])
    view = clinic.availability.day_schedule(clinic.rao, MONDAY, None, NOW)
    assert view.slots == ()
    assert [a.patient_name for a in view.outside_availability] == ["Asha Iyer"]
    assert view.outside_availability[0].needs_attention is True
    assert view.unavailable_reason is UnavailableReason.NO_AVAILABILITY


def test_the_overlap_between_two_utc_days_is_handled(clinic: Clinic) -> None:
    """A slot late on an India evening is still the same India date, whatever UTC says."""
    with clinic.factory() as session, session.begin():
        night = add_doctor(session, name="Dr. Night", slot=30, cap=10)
        add_weekly(session, night.id, 0, 1380, 1440)  # 23:00-24:00
    view = clinic.availability.free_slots(night.id, MONDAY, None, NOW)
    assert view.slots == (ist(2026, 11, 2, 23, 0), ist(2026, 11, 2, 23, 30))
