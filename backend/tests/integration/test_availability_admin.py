"""Changing weekly hours and date overrides, and the conflict protocol (T-O01 to T-O04)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

import pytest

from app.domain.errors import ConflictError, DomainError, ErrorCode, NotFoundError, RuleViolation
from app.domain.model import Status, WeeklyWindow, Window
from app.services.views import BookCommand, OverrideChange
from tests.factories import add_appointment, add_override
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration

NEXT_MONDAY = date(2026, 11, 9)
SATURDAY = date(2026, 11, 7)


def booked_on(clinic: Clinic, start: datetime, patient: int | None = None) -> int:
    with clinic.factory() as session, session.begin():
        return add_appointment(session, clinic.rao, patient or clinic.asha, start).id


def weekly_of(clinic: Clinic) -> list[tuple[int, int, int]]:
    return [
        (w.weekday, w.start_min, w.end_min) for w in clinic.availability.weekly_windows(clinic.rao)
    ]


def put_leave(clinic: Clinic, day: date, *, acknowledge: bool = False) -> OverrideChange:
    return clinic.availability.put_override(clinic.rao, day, [], None, acknowledge, NOW)


# ---------------------------------------------------------------------- the conflict protocol


def test_a_leave_day_over_a_booking_is_refused_with_the_list(clinic: Clinic) -> None:
    """T-O01"""
    booked_on(clinic, at(10))
    with pytest.raises(ConflictError) as raised:
        put_leave(clinic, MONDAY)
    error = raised.value
    assert error.code is ErrorCode.AVAILABILITY_CONFLICTS
    assert error.details["date"] == "2026-11-02"
    assert error.details["appointments"] == [
        {
            "id": 1,
            "patient_name": "Asha Iyer",
            "patient_phone": "+919000000001",
            "start_at_ist": "2026-11-02T10:00:00+05:30",
        }
    ]
    assert (
        "1 future appointment would fall outside Dr. Rao's availability on 2026-11-02"
        in error.message
    )
    assert clinic.availability.overrides(clinic.rao, MONDAY, MONDAY) == []  # nothing was saved


def test_acknowledging_saves_the_change_and_flags_the_appointment(clinic: Clinic) -> None:
    """T-O02"""
    appointment_id = booked_on(clinic, at(10))
    change = put_leave(clinic, MONDAY, acknowledge=True)
    assert [a.id for a in change.needs_attention] == [appointment_id]
    assert change.needs_attention[0].needs_attention is True
    assert change.windows == ()
    assert clinic.appointment(appointment_id).status == "BOOKED"  # still booked, never cancelled
    with pytest.raises(DomainError) as raised:  # and the day is closed to new bookings
        clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(11), "Check-up"), NOW)
    assert raised.value.code is ErrorCode.OUTSIDE_AVAILABILITY


def test_weekly_hours_without_the_booked_morning_are_refused(clinic: Clinic) -> None:
    """T-O03: Monday 09:00 is booked and the new pattern starts at 10:00."""
    booked_on(clinic, at(9))
    afternoon_only = [WeeklyWindow(0, 600, 780)]
    with pytest.raises(ConflictError) as raised:
        clinic.availability.replace_weekly_windows(clinic.rao, afternoon_only, False, NOW)
    assert raised.value.code is ErrorCode.AVAILABILITY_CONFLICTS
    assert raised.value.details["date"] is None
    assert len(weekly_of(clinic)) == 5  # unchanged: Monday to Friday

    saved = clinic.availability.replace_weekly_windows(clinic.rao, afternoon_only, True, NOW)
    assert [a.start_at for a in saved.needs_attention] == [at(9)]
    assert weekly_of(clinic) == [(0, 600, 780)]


def test_removing_an_extra_day_with_a_booking_is_refused(clinic: Clinic) -> None:
    """T-O04"""
    clinic.availability.put_override(clinic.rao, SATURDAY, [Window(600, 720)], "Camp", False, NOW)
    booked_on(clinic, at(10, day=7))
    with pytest.raises(ConflictError) as raised:
        clinic.availability.delete_override(clinic.rao, SATURDAY, False, NOW)
    assert raised.value.code is ErrorCode.AVAILABILITY_CONFLICTS
    assert len(clinic.availability.overrides(clinic.rao, SATURDAY, SATURDAY)) == 1
    clinic.availability.delete_override(clinic.rao, SATURDAY, True, NOW)
    assert clinic.availability.overrides(clinic.rao, SATURDAY, SATURDAY) == []


def test_a_change_that_still_fits_every_booking_needs_no_acknowledgement(clinic: Clinic) -> None:
    booked_on(clinic, at(10))
    change = clinic.availability.put_override(
        clinic.rao, MONDAY, [Window(540, 660)], None, False, NOW
    )
    assert change.needs_attention == ()


def test_only_appointments_a_change_newly_orphans_block_it(clinic: Clinic) -> None:
    """An appointment already outside the hours (after an earlier acknowledgement) is not a new
    conflict, so unrelated edits are not held hostage by it."""
    booked_on(clinic, at(10, day=9))
    put_leave(clinic, NEXT_MONDAY, acknowledge=True)  # now an orphan, acknowledged
    other_day = date(2026, 11, 10)
    clinic.availability.put_override(clinic.rao, other_day, [Window(600, 660)], None, False, NOW)
    # a second leave on the same day orphans nothing new either
    assert put_leave(clinic, NEXT_MONDAY).needs_attention == ()


def test_only_booked_appointments_block_a_change(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(10), status=Status.CANCELLED)
        add_appointment(session, clinic.rao, clinic.ravi, at(9), status=Status.COMPLETED)
        add_appointment(session, clinic.rao, clinic.meena, at(11))
    with pytest.raises(ConflictError) as raised:
        put_leave(clinic, MONDAY)
    assert [a["id"] for a in raised.value.details["appointments"]] == [3]  # only the BOOKED one


# ------------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("windows", "code"),
    [
        (
            [Window(540, 780), Window(700, 900)],
            ErrorCode.WINDOW_OFF_GRID,
        ),  # 700 is not on a 30-grid
        ([Window(540, 780), Window(720, 900)], ErrorCode.WINDOW_OVERLAP),
        ([Window(545, 780)], ErrorCode.WINDOW_OFF_GRID),
        ([Window(600, 600)], ErrorCode.VALIDATION_ERROR),
        ([Window(600, 1500)], ErrorCode.VALIDATION_ERROR),
    ],
)
def test_bad_override_windows_are_refused_and_nothing_is_written(
    clinic: Clinic, windows: list[Window], code: ErrorCode
) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.availability.put_override(clinic.rao, MONDAY, windows, None, False, NOW)
    assert raised.value.code is code
    assert clinic.availability.overrides(clinic.rao, MONDAY, MONDAY) == []


@pytest.mark.parametrize(
    ("windows", "code"),
    [
        ([WeeklyWindow(0, 540, 780), WeeklyWindow(0, 720, 900)], ErrorCode.WINDOW_OVERLAP),
        ([WeeklyWindow(0, 540, 780), WeeklyWindow(1, 540, 790)], ErrorCode.WINDOW_OFF_GRID),
        ([WeeklyWindow(7, 540, 780)], ErrorCode.VALIDATION_ERROR),
    ],
)
def test_bad_weekly_windows_are_refused_and_the_old_hours_stay(
    clinic: Clinic, windows: list[WeeklyWindow], code: ErrorCode
) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.availability.replace_weekly_windows(clinic.rao, windows, False, NOW)
    assert raised.value.code is code
    assert len(weekly_of(clinic)) == 5


def test_the_same_clock_time_on_different_weekdays_is_not_an_overlap(clinic: Clinic) -> None:
    both = [WeeklyWindow(0, 540, 780), WeeklyWindow(1, 540, 780), WeeklyWindow(0, 780, 840)]
    saved = clinic.availability.replace_weekly_windows(clinic.rao, both, False, NOW)
    assert [(w.weekday, w.start_min) for w in saved.windows] == [(0, 540), (0, 780), (1, 540)]


# --------------------------------------------------------------------------- replacing rows


def test_replacing_the_weekly_hours_is_atomic_and_ordered(clinic: Clinic) -> None:
    new = [WeeklyWindow(2, 1020, 1140), WeeklyWindow(2, 540, 780), WeeklyWindow(4, 600, 720)]
    saved = clinic.availability.replace_weekly_windows(clinic.rao, new, False, NOW)
    assert [(w.weekday, w.start_min, w.end_min) for w in saved.windows] == [
        (2, 540, 780),
        (2, 1020, 1140),
        (4, 600, 720),
    ]
    assert weekly_of(clinic) == [(2, 540, 780), (2, 1020, 1140), (4, 600, 720)]
    clinic.availability.replace_weekly_windows(clinic.rao, [], False, NOW)
    assert weekly_of(clinic) == []


def test_an_override_can_be_replaced_by_one_that_overlaps_it(clinic: Clinic) -> None:
    """Delete-then-insert matters: the new window overlaps the one being replaced."""
    clinic.availability.put_override(clinic.rao, MONDAY, [Window(540, 780)], "first", False, NOW)
    clinic.availability.put_override(clinic.rao, MONDAY, [Window(540, 720)], "second", False, NOW)
    [only] = clinic.availability.overrides(clinic.rao, MONDAY, MONDAY)
    assert (only.note, only.windows) == ("second", (Window(540, 720),))


def test_overrides_are_listed_in_date_order_within_a_range(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_override(session, clinic.rao, date(2026, 11, 9), [(540, 600)])
        add_override(session, clinic.rao, date(2026, 11, 3), [])
        add_override(session, clinic.rao, date(2026, 12, 25), [])
    listed = clinic.availability.overrides(clinic.rao, date(2026, 11, 1), date(2026, 11, 30))
    assert [(o.on_date, o.windows) for o in listed] == [
        (date(2026, 11, 3), ()),
        (date(2026, 11, 9), (Window(540, 600),)),
    ]


def test_removing_an_override_that_is_not_there_does_nothing(clinic: Clinic) -> None:
    change = clinic.availability.delete_override(clinic.rao, MONDAY, False, NOW)
    assert change.needs_attention == ()


def test_unknown_doctors_are_not_found_by_every_operation(clinic: Clinic) -> None:
    operations: list[Callable[[], object]] = [
        lambda: clinic.availability.weekly_windows(999),
        lambda: clinic.availability.overrides(999, MONDAY, MONDAY),
        lambda: clinic.availability.replace_weekly_windows(999, [], False, NOW),
        lambda: clinic.availability.put_override(999, MONDAY, [], None, False, NOW),
        lambda: clinic.availability.delete_override(999, MONDAY, False, NOW),
        lambda: clinic.availability.day_schedule(999, MONDAY, None, NOW),
    ]
    for operation in operations:
        with pytest.raises(NotFoundError) as raised:
            operation()
        assert raised.value.code is ErrorCode.DOCTOR_NOT_FOUND
