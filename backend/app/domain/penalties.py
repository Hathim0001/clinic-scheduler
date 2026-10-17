"""Rule 5, second half: two or more Late-Cancels or No-Shows in the trailing 30 days flag a patient,
and bookings for a flagged patient must carry a deposit acknowledgement.

The flag is derived at request time from the patient's history, never stored. It cannot go stale,
needs no scheduled job, and follows the reviewer's test clock.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from app.domain.model import DepositStatus, PenaltyEvent

LOOKBACK = timedelta(days=30)
STRIKES = 2


def deposit_status(events: Iterable[PenaltyEvent], now: datetime) -> DepositStatus:
    """Whether a deposit acknowledgement is required at `now`.

    An event counts when `now - 30 days <= event.at <= now` (both ends inclusive, A-22). The flag is
    on from the second strike and lasts through the instant the second-most-recent strike turns 30
    days old: `required_until`. One second later the patient is no longer flagged.
    """
    raise NotImplementedError
