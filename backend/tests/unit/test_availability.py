"""Rule 1a: effective availability, where an override beats the weekly pattern."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.domain.availability import (
    fits_in_windows,
    needs_attention,
    resolve_windows,
    validate_windows,
)
from app.domain.errors import ErrorCode, RuleViolation
from app.domain.model import Status, WeeklyWindow, Window
from tests.helpers import appt_facts, ist

pytestmark = pytest.mark.unit

MONDAY = date(2026, 11, 2)
# Monday has two windows (listed out of order on purpose), Wednesday and Friday one each.
WEEKLY = [
    WeeklyWindow(0, 1020, 1140),
    WeeklyWindow(0, 600, 840),
    WeeklyWindow(2, 600, 840),
    WeeklyWindow(4, 600, 840),
]


def test_the_weekly_windows_apply_when_there_is_no_override() -> None:
    windows, source = resolve_windows(MONDAY, WEEKLY, None)
    assert windows == (Window(600, 840), Window(1020, 1140))  # sorted
    assert source == "WEEKLY"


def test_a_day_without_a_weekly_pattern_has_no_windows() -> None:
    tuesday = date(2026, 11, 3)
    assert resolve_windows(tuesday, WEEKLY, None) == ((), "WEEKLY")


def test_an_override_replaces_the_weekly_windows_entirely() -> None:
    """A-02: the weekly 10:00-14:00 and 17:00-19:00 are gone, not merged."""
    windows, source = resolve_windows(MONDAY, WEEKLY, [Window(660, 780)])
    assert windows == (Window(660, 780),)
    assert source == "OVERRIDE"


def test_an_override_with_no_windows_is_a_leave_day() -> None:
    assert resolve_windows(MONDAY, WEEKLY, []) == ((), "OVERRIDE")


def test_an_override_on_a_day_with_no_weekly_pattern_adds_a_working_day() -> None:
    saturday = date(2026, 11, 7)
    assert resolve_windows(saturday, WEEKLY, [Window(600, 780)]) == (
        (Window(600, 780),),
        "OVERRIDE",
    )


def test_override_windows_come_back_sorted() -> None:
    windows, _ = resolve_windows(MONDAY, WEEKLY, [Window(1020, 1140), Window(600, 720)])
    assert windows == (Window(600, 720), Window(1020, 1140))


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (
            ist(2026, 11, 2, 9, 0),
            ist(2026, 11, 2, 9, 30),
            True,
        ),  # starts exactly at the window start
        (ist(2026, 11, 2, 12, 30), ist(2026, 11, 2, 13, 0), True),  # T-B02 ends exactly at the end
        (ist(2026, 11, 2, 13, 0), ist(2026, 11, 2, 13, 30), False),  # T-B03 starts at the end
        (ist(2026, 11, 2, 8, 30), ist(2026, 11, 2, 9, 0), False),  # T-B04 ends at the start
        (ist(2026, 11, 2, 12, 45), ist(2026, 11, 2, 13, 15), False),  # runs past the end
    ],
    ids=["start edge", "end edge", "after the window", "before the window", "overruns the end"],
)
def test_a_slot_must_lie_entirely_inside_a_window(
    start: datetime, end: datetime, expected: bool
) -> None:
    assert fits_in_windows(start, end, [Window(540, 780)]) is expected


def test_a_slot_cannot_straddle_two_adjacent_windows() -> None:
    """A-03: even with no gap between 09:00-13:00 and 13:00-17:00, one slot needs one window."""
    windows = [Window(540, 780), Window(780, 1020)]
    assert fits_in_windows(ist(2026, 11, 2, 12, 45), ist(2026, 11, 2, 13, 15), windows) is False


def test_the_gap_between_two_windows_is_not_available() -> None:
    windows = [Window(540, 780), Window(1020, 1140)]
    assert fits_in_windows(ist(2026, 11, 2, 13, 30), ist(2026, 11, 2, 14, 0), windows) is False
    assert fits_in_windows(ist(2026, 11, 2, 17, 0), ist(2026, 11, 2, 17, 30), windows) is True


def test_a_slot_ending_at_midnight_fits_a_window_that_ends_at_24_00() -> None:
    assert (
        fits_in_windows(ist(2026, 11, 2, 23, 30), ist(2026, 11, 3, 0, 0), [Window(1380, 1440)])
        is True
    )


def test_no_windows_means_nothing_fits() -> None:
    assert fits_in_windows(ist(2026, 11, 2, 9, 0), ist(2026, 11, 2, 9, 30), []) is False


def test_valid_windows_pass_validation() -> None:
    validate_windows([Window(540, 780), Window(1020, 1140)], 15)
    validate_windows([Window(540, 780), Window(780, 1020)], 30)  # adjacent windows are fine


@pytest.mark.parametrize(
    "windows",
    [
        [Window(540, 780), Window(700, 900)],  # partial overlap
        [Window(540, 780), Window(540, 780)],  # identical
        [Window(540, 900), Window(600, 660)],  # one inside the other
    ],
    ids=["partial", "identical", "nested"],
)
def test_overlapping_windows_are_rejected(windows: list[Window]) -> None:
    with pytest.raises(RuleViolation) as raised:
        validate_windows(windows, 15)
    assert raised.value.code is ErrorCode.WINDOW_OVERLAP


@pytest.mark.parametrize(
    ("window", "slot"),
    [
        (Window(545, 780), 30),  # starts at 09:05, off the 30-minute grid
        (Window(540, 790), 30),  # ends at 13:10
        (Window(541, 780), 15),
        (Window(540, 781), 15),
    ],
)
def test_window_edges_must_lie_on_the_slot_grid(window: Window, slot: int) -> None:
    """A-26: otherwise a partial slot would appear at the edge of the window."""
    with pytest.raises(RuleViolation) as raised:
        validate_windows([window], slot)
    assert raised.value.code is ErrorCode.WINDOW_OFF_GRID


@pytest.mark.parametrize(
    "window", [Window(600, 600), Window(700, 600), Window(-15, 60), Window(1380, 1455)]
)
def test_a_window_must_be_a_forward_range_inside_one_day(window: Window) -> None:
    with pytest.raises(RuleViolation) as raised:
        validate_windows([window], 15)
    assert raised.value.code is ErrorCode.VALIDATION_ERROR


NOW = ist(2026, 11, 2, 8, 0)
BOOKING = appt_facts(ist(2026, 11, 9, 10, 0))


def test_a_future_booking_outside_the_windows_needs_attention() -> None:
    """A-27: it was valid when booked; a leave day made it an orphan."""
    assert needs_attention(BOOKING, NOW, []) is True


def test_a_booking_inside_the_windows_does_not_need_attention() -> None:
    assert needs_attention(BOOKING, NOW, [Window(540, 780)]) is False


@pytest.mark.parametrize(
    "status", [Status.COMPLETED, Status.CANCELLED, Status.LATE_CANCELLED, Status.NO_SHOW]
)
def test_only_booked_appointments_can_need_attention(status: Status) -> None:
    orphan = appt_facts(ist(2026, 11, 9, 10, 0), status=status)
    assert needs_attention(orphan, NOW, []) is False


def test_a_past_booking_never_needs_attention() -> None:
    assert needs_attention(BOOKING, ist(2026, 11, 10, 8, 0), []) is False
