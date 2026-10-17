"""Rule 1a: an appointment must lie entirely inside the doctor's effective availability.

A date's effective windows come from the date-specific override when there is one, otherwise from
the weekly pattern. An override replaces the weekly windows entirely (A-02); an empty override
means leave.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from itertools import pairwise

from app.domain.errors import ErrorCode, RuleViolation
from app.domain.model import AppointmentFacts, Status, WeeklyWindow, Window
from app.domain.timeutil import MINUTES_PER_DAY, at_ist, format_minutes, ist_date


def _in_time_order(windows: Iterable[Window]) -> tuple[Window, ...]:
    return tuple(sorted(windows, key=lambda window: (window.start_min, window.end_min)))


def _describe(window: Window) -> str:
    return f"{format_minutes(window.start_min)}-{format_minutes(window.end_min)}"


def resolve_windows(
    day: date,
    weekly: Sequence[WeeklyWindow],
    override: Sequence[Window] | None,
) -> tuple[tuple[Window, ...], str]:
    """The effective windows for `day`, sorted, and where they came from ("OVERRIDE" or "WEEKLY").

    `override` is None when the date has no override row, and an empty sequence for a leave day.
    """
    if override is not None:
        return _in_time_order(override), "OVERRIDE"
    todays = (Window(w.start_min, w.end_min) for w in weekly if w.weekday == day.weekday())
    return _in_time_order(todays), "WEEKLY"


def fits_in_windows(start_at: datetime, end_at: datetime, windows: Sequence[Window]) -> bool:
    """True when [start_at, end_at] lies inside ONE window (A-03).

    Both ends are inclusive: 12:30-13:00 fits a 09:00-13:00 window. A slot ending exactly at IST
    midnight counts as minute 1440.
    """
    midnight = at_ist(ist_date(start_at), 0)
    begin, finish = start_at - midnight, end_at - midnight
    return any(
        timedelta(minutes=window.start_min) <= begin and finish <= timedelta(minutes=window.end_min)
        for window in windows
    )


def validate_windows(windows: Sequence[Window], slot_length_min: int) -> None:
    """Raise WINDOW_OFF_GRID or WINDOW_OVERLAP for a set of windows that belong to one day.

    Every edge must lie on the doctor's slot grid (A-26) and no two windows may overlap. Adjacent
    windows (09:00-13:00 and 13:00-17:00) are fine. The database has the same checks as a backstop.
    Each window is checked on its own first (shape, then grid), then the windows against each other.
    """
    for window in windows:
        if not 0 <= window.start_min < window.end_min <= MINUTES_PER_DAY:
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR,
                "A window must start before it ends, between 00:00 and 24:00.",
                start_min=window.start_min,
                end_min=window.end_min,
            )
    for window in windows:
        if window.start_min % slot_length_min or window.end_min % slot_length_min:
            raise RuleViolation(
                ErrorCode.WINDOW_OFF_GRID,
                f"The window {_describe(window)} does not fall on the {slot_length_min}-minute "
                "slot grid.",
                start_min=window.start_min,
                end_min=window.end_min,
                slot_length_min=slot_length_min,
            )
    for earlier, later in pairwise(_in_time_order(windows)):
        if later.start_min < earlier.end_min:
            raise RuleViolation(
                ErrorCode.WINDOW_OVERLAP,
                f"The windows {_describe(earlier)} and {_describe(later)} overlap.",
            )


def needs_attention(appt: AppointmentFacts, now: datetime, windows: Sequence[Window]) -> bool:
    """True for a BOOKED future appointment that no longer fits the effective windows (A-27).

    Derived, never stored: it appears when an availability change leaves bookings outside the new
    windows and goes away when they fit again.
    """
    return (
        appt.status is Status.BOOKED
        and appt.start_at >= now
        and not fits_in_windows(appt.start_at, appt.end_at, windows)
    )
