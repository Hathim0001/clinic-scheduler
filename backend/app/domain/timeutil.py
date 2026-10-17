"""Time helpers. Everything is stored in UTC and the clinic thinks in India Standard Time (IST).

India has no daylight saving, so IST is a constant +05:30 and a wall-clock time maps to exactly one
instant. The date and minute-of-day helpers below always convert to IST first: the 60-day limit and
the daily cap are about IST calendar days, not UTC days (00:30 IST is still the previous UTC date).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Inputs are bounded before any conversion: converting a year-9999 instant to IST raises
# OverflowError, which a naive API turns into a 500.
MIN_INSTANT = datetime(2000, 1, 1, tzinfo=UTC)
MAX_INSTANT = datetime(2100, 1, 1, tzinfo=UTC)  # exclusive
MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)

MINUTES_PER_DAY = 24 * 60


def ist_date(instant: datetime) -> date:
    """The IST calendar date of an instant."""
    return instant.astimezone(IST).date()


def ist_minute_of_day(instant: datetime) -> int:
    """Minutes since IST midnight, ignoring seconds (hour * 60 + minute)."""
    local = instant.astimezone(IST)
    return local.hour * 60 + local.minute


def ist_day_bounds(day: date) -> tuple[datetime, datetime]:
    """The half-open UTC interval [start, end) covered by one IST calendar day."""
    start = datetime.combine(day, time(0), IST)
    end = start + timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)


def at_ist(day: date, minute_of_day: int) -> datetime:
    """The UTC instant at `minute_of_day` minutes after IST midnight on `day` (may reach 24:00)."""
    midnight = datetime.combine(day, time(0), IST)
    return (midnight + timedelta(minutes=minute_of_day)).astimezone(UTC)


def format_minutes(minute_of_day: int) -> str:
    """Minutes since midnight as HH:MM: 570 is "09:30" and 1440 is "24:00"."""
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"
