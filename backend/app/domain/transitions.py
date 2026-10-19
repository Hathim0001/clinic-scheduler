"""Which status changes are allowed, and which buttons the UI may offer.

Only a BOOKED appointment can change. Before its start it can be cancelled or rescheduled; from its
start on it can be marked completed or no-show. The four other statuses are final, except that a
wrongly recorded outcome can be corrected (A-19, A-48): a no-show and a completion swap, and a late
cancellation can be waived to an ordinary one. Reception can check a booked patient in on the day.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import Status
from app.domain.timeutil import ist_date

_SO_FAR = {
    Status.COMPLETED: "completed",
    Status.CANCELLED: "cancelled",
    Status.LATE_CANCELLED: "cancelled late",
    Status.NO_SHOW: "marked as a no-show",
}


# A cancellation can be taken back for this long, while the visit is still ahead.
UNDO_WINDOW = timedelta(minutes=10)
CANCELLED_STATUSES = frozenset({Status.CANCELLED, Status.LATE_CANCELLED})


def can_undo_cancel(
    status: Status,
    cancelled_at: datetime | None,
    start_at: datetime,
    now: datetime,
    rescheduled: bool,
    undo_window: timedelta = UNDO_WINDOW,
) -> bool:
    """A plain cancellation, made minutes ago, of a visit that has not started."""
    return (
        status in CANCELLED_STATUSES
        and not rescheduled
        and cancelled_at is not None
        and undo_window > timedelta(0)  # 0 minutes turns undo off
        and timedelta(0) <= now - cancelled_at <= undo_window
        and now < start_at
    )


# Outcome corrections: what a final status may be changed to.
CORRECTIONS: dict[Status, frozenset[Status]] = {
    Status.COMPLETED: frozenset({Status.NO_SHOW}),
    Status.NO_SHOW: frozenset({Status.COMPLETED}),
    Status.LATE_CANCELLED: frozenset({Status.CANCELLED}),
}


def allowed_actions(
    status: Status,
    start_at: datetime,
    now: datetime,
    checked_in: bool = False,
    cancelled_at: datetime | None = None,
    rescheduled: bool = False,
    undo_window: timedelta = UNDO_WINDOW,
) -> list[str]:
    """cancel and reschedule before the start; from it complete, no-show and (late) cancel.

    A booked patient can also be checked in on the day, once. A final status offers `correct` when
    a correction exists for it.
    """
    if status is not Status.BOOKED:
        actions = ["correct"] if status in CORRECTIONS else []
        if can_undo_cancel(status, cancelled_at, start_at, now, rescheduled, undo_window):
            actions.append("undo-cancel")
        return actions
    actions = ["cancel", "reschedule"] if now < start_at else ["complete", "no-show", "cancel"]
    if not checked_in and ist_date(now) == ist_date(start_at):
        actions.insert(0, "check-in")
    return actions


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


def check_can_check_in(status: Status, start_at: datetime, now: datetime) -> None:
    """Raise unless the appointment is BOOKED and today (India date) is the day of the visit."""
    _require_booked(status)
    if ist_date(now) != ist_date(start_at):
        raise ConflictError(
            ErrorCode.TOO_EARLY_TO_MARK,
            "Check-in opens on the day of the appointment.",
        )


def check_correction(current: Status, target: Status) -> None:
    """Raise INVALID_CORRECTION unless `current` may be corrected to `target`."""
    if target not in CORRECTIONS.get(current, frozenset()):
        allowed = sorted(s.value for s in CORRECTIONS.get(current, frozenset()))
        raise ConflictError(
            ErrorCode.INVALID_CORRECTION,
            f"A {current.value} appointment cannot be corrected to {target.value}."
            + (f" It can be corrected to {', '.join(allowed)}." if allowed else ""),
            status=current.value,
            target=target.value,
            allowed=allowed,
        )
