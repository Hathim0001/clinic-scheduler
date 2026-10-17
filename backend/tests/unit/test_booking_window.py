"""Rule 7: not in the past, not more than 60 days ahead (T-W01 to T-W06)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.booking_window import check_booking_window
from app.domain.errors import ErrorCode
from tests.helpers import ist

pytestmark = pytest.mark.unit

NOW = ist(2026, 10, 17, 10, 0)


def test_a_start_a_minute_before_now_is_in_the_past() -> None:
    """T-W01"""
    result = check_booking_window(NOW - timedelta(minutes=1), NOW)
    assert result is ErrorCode.BOOKING_IN_PAST


def test_a_start_equal_to_now_is_already_in_the_past() -> None:
    """A-07: the check is strict, so you cannot book the minute that is happening now."""
    assert check_booking_window(NOW, NOW) is ErrorCode.BOOKING_IN_PAST


def test_a_start_a_minute_from_now_is_allowed() -> None:
    """T-W02"""
    assert check_booking_window(NOW + timedelta(minutes=1), NOW) is None


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        (ist(2026, 12, 16, 23, 59), None),  # today + 60 days, last minute of the day
        (ist(2026, 12, 17, 0, 0), ErrorCode.BOOKING_TOO_FAR),  # today + 61 days, first minute
        (ist(2026, 12, 16, 0, 30), None),  # 00:30 IST on day 60 is the previous UTC date
        (ist(2026, 12, 17, 0, 30), ErrorCode.BOOKING_TOO_FAR),
    ],
    ids=["day 60 late", "day 61 early", "day 60 UTC trap", "day 61 UTC trap"],
)
def test_the_horizon_is_sixty_ist_calendar_days(
    start: datetime, expected: ErrorCode | None
) -> None:
    assert check_booking_window(start, NOW) is expected


def test_sixty_days_means_dates_not_sixty_times_twenty_four_hours() -> None:
    """A-05: 23:59 on day 60 is more than 60 x 24 hours away but is still allowed."""
    start = ist(2026, 12, 16, 23, 59)
    assert start - NOW > timedelta(days=60)
    assert check_booking_window(start, NOW) is None


def test_the_window_crosses_a_month_and_year_boundary() -> None:
    """T-W03 and T-W04: 31 Dec 2026 + 60 days is 1 March 2027."""
    now = ist(2026, 12, 31, 9, 0)
    assert check_booking_window(ist(2027, 3, 1, 10), now) is None
    assert check_booking_window(ist(2027, 3, 2, 10), now) is ErrorCode.BOOKING_TOO_FAR


def test_the_window_crosses_a_leap_day() -> None:
    """T-W06: 1 Jan 2028 + 60 days is 1 March 2028, because February has 29 days."""
    now = ist(2028, 1, 1, 9, 0)
    assert check_booking_window(ist(2028, 3, 1, 10), now) is None
    assert check_booking_window(ist(2028, 3, 2, 10), now) is ErrorCode.BOOKING_TOO_FAR
