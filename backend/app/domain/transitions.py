"""Which status changes are allowed, and which buttons the UI may offer.

Only a BOOKED appointment can change. Before its start it can be cancelled or rescheduled; from its
start on it can be marked completed or no-show. The four other statuses are terminal (A-19).
"""

from __future__ import annotations

from datetime import datetime

from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import Status

_SO_FAR = {
    Status.COMPLETED: "completed",
    Status.CANCELLED: "cancelled",
    Status.LATE_CANCELLED: "cancelled late",
    Status.NO_SHOW: "marked as a no-show",
}


def allowed_actions(status: Status, start_at: datetime, now: datetime) -> list[str]:
    """cancel and reschedule before the start; from it complete, no-show and (late) cancel."""
    if status is not Status.BOOKED:
        return []
    return ["cancel", "reschedule"] if now < start_at else ["complete", "no-show", "cancel"]


def _require_booked(status: Status) -> None:
    if status is not Status.BOOKED:
        raise ConflictError(
            ErrorCode.INVALID_TRANSITION,
            f"This appointment is already {_SO_FAR[status]}, so it cannot be changed.",
            status=status.value,
        )


def check_can_cancel(status: Status) -> None:
    """Raise INVALID_TRANSITION unless the appointment is BOOKED (also guards rescheduling)."""
    _require_booked(status)


def check_can_mark(status: Status, start_at: datetime, now: datetime) -> None:
    """Raise INVALID_TRANSITION unless BOOKED, and TOO_EARLY_TO_MARK before the start (A-18)."""
    _require_booked(status)
    if now < start_at:
        raise ConflictError(
            ErrorCode.TOO_EARLY_TO_MARK,
            "An appointment can only be marked completed or no-show once it has started.",
        )
