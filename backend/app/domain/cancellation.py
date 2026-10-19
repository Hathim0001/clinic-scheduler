"""Rule 5, first half: a cancellation at least 2 hours before the start is a normal Cancel; later
than that it is a Late-Cancel."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import CancelledBy, Status

LATE_THRESHOLD = timedelta(hours=2)


def classify_cancellation(
    start_at: datetime,
    now: datetime,
    by: CancelledBy,
    late_threshold: timedelta = LATE_THRESHOLD,
) -> Status:
    """CANCELLED or LATE_CANCELLED for a cancellation requested at `now`.

    Exactly 2h00m before the start is still a normal Cancel; 1h59m is late, and so is anything
    after the start: the statement says "later than that it is a Late-Cancel" (A-08). A cancellation
    by the clinic is always a normal Cancel and never counts against the patient (A-09).
    """
    if by is CancelledBy.CLINIC:
        return Status.CANCELLED
    return Status.CANCELLED if start_at - now >= late_threshold else Status.LATE_CANCELLED


def check_can_reschedule(start_at: datetime, now: datetime) -> None:
    """An appointment that has started cannot be moved: raises APPOINTMENT_ALREADY_STARTED."""
    if now >= start_at:
        raise ConflictError(
            ErrorCode.APPOINTMENT_ALREADY_STARTED,
            "The appointment has already started, so it can no longer be moved.",
        )
