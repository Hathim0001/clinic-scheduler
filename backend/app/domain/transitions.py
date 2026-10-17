"""Which status changes are allowed, and which buttons the UI may offer.

Only a BOOKED appointment can change. Before its start it can be cancelled or rescheduled; from its
start on it can be marked completed or no-show. The four other statuses are terminal (A-19).
"""

from __future__ import annotations

from datetime import datetime

from app.domain.model import Status


def allowed_actions(status: Status, start_at: datetime, now: datetime) -> list[str]:
    """cancel and reschedule before the start, complete and no-show from the start, else nothing."""
    raise NotImplementedError


def check_can_cancel(status: Status) -> None:
    """Raise INVALID_TRANSITION unless the appointment is BOOKED (also guards rescheduling)."""
    raise NotImplementedError


def check_can_mark(status: Status, start_at: datetime, now: datetime) -> None:
    """Raise INVALID_TRANSITION unless BOOKED, and TOO_EARLY_TO_MARK before the start (A-18)."""
    raise NotImplementedError
