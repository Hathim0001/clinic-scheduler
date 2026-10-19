"""Rule 7: an appointment cannot be in the past, nor more than 60 days ahead (a clinic may change
the 60; the policy supplies it)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.errors import ErrorCode
from app.domain.timeutil import ist_date

HORIZON_DAYS = 60


def check_booking_window(
    start_at: datetime, now: datetime, horizon_days: int = HORIZON_DAYS
) -> ErrorCode | None:
    """Return BOOKING_IN_PAST, BOOKING_TOO_FAR or None.

    "Past" is strict: a start equal to `now` is already past (A-07). The 60-day limit compares IST
    calendar dates, never UTC dates and never 60 x 24 hours (A-05): today + 60 days is allowed,
    today + 61 is not.

    Instants must already be inside the supported range (see `timeutil.MIN_INSTANT`); the API
    edge rejects anything else before it gets here.
    """
    if start_at <= now:
        return ErrorCode.BOOKING_IN_PAST
    if ist_date(start_at) > ist_date(now) + timedelta(days=horizon_days):
        return ErrorCode.BOOKING_TOO_FAR
    return None
