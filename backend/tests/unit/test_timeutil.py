"""Time helpers: India has no daylight saving, and every date the rules use is an IST date."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.timeutil import IST, at_ist, ist_date, ist_day_bounds, ist_minute_of_day
from tests.helpers import ist

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("month", [1, 4, 7, 10])
def test_ist_is_a_constant_offset_of_five_and_a_half_hours(month: int) -> None:
    assert ist(2026, month, 15, 12).astimezone(IST).utcoffset() == timedelta(hours=5, minutes=30)


def test_the_ist_date_flips_at_midnight_ist_not_at_midnight_utc() -> None:
    """T-W05: 2026-10-31 19:00 UTC is already 1 November, 00:30 in India."""
    instant = datetime(2026, 10, 31, 19, 0, tzinfo=UTC)
    assert ist_date(instant) == date(2026, 11, 1)
    assert instant.astimezone(IST).strftime("%H:%M") == "00:30"


def test_half_past_midnight_ist_is_still_the_previous_utc_date() -> None:
    """The trap behind the 60-day rule: comparing UTC dates would be off by one here."""
    instant = ist(2026, 12, 16, 0, 30)
    assert instant.astimezone(UTC).date() == date(2026, 12, 15)
    assert ist_date(instant) == date(2026, 12, 16)


def test_minute_of_day_ignores_seconds() -> None:
    assert ist_minute_of_day(ist(2026, 11, 2, 9, 15, 59)) == 9 * 60 + 15


def test_day_bounds_cover_exactly_one_ist_day() -> None:
    low, high = ist_day_bounds(date(2026, 11, 2))
    assert low == ist(2026, 11, 2)
    assert high == ist(2026, 11, 3)
    assert high - low == timedelta(hours=24)


def test_at_ist_places_a_minute_of_the_day_on_the_timeline() -> None:
    day = date(2026, 11, 2)
    assert at_ist(day, 9 * 60) == ist(2026, 11, 2, 9, 0)
    assert at_ist(day, 24 * 60) == ist(2026, 11, 3, 0, 0)  # 24:00 is the next midnight
