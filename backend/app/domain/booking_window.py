"""Rule 7: an appointment cannot be in the past, nor more than 60 days ahead."""

from __future__ import annotations

from datetime import datetime

from app.domain.errors import ErrorCode

HORIZON_DAYS = 60


def check_booking_window(start_at: datetime, now: datetime) -> ErrorCode | None:
    """Return BOOKING_IN_PAST, BOOKING_TOO_FAR or None.

    "Past" is strict: a start equal to `now` is already past (A-07). The 60-day limit compares IST
    calendar dates, never UTC dates and never 60 x 24 hours (A-05): today + 60 days is allowed,
    today + 61 is not.
    """
    raise NotImplementedError
