"""Rule 1a: an appointment must lie entirely inside the doctor's effective availability.

A date's effective windows come from the date-specific override when there is one, otherwise from
the weekly pattern. An override replaces the weekly windows entirely (A-02); an empty override
means leave.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from app.domain.model import AppointmentFacts, WeeklyWindow, Window


def resolve_windows(
    day: date,
    weekly: Sequence[WeeklyWindow],
    override: Sequence[Window] | None,
) -> tuple[tuple[Window, ...], str]:
    """The effective windows for `day`, sorted, and where they came from ("OVERRIDE" or "WEEKLY").

    `override` is None when the date has no override row, and an empty sequence for a leave day.
    """
    raise NotImplementedError


def fits_in_windows(start_at: datetime, end_at: datetime, windows: Sequence[Window]) -> bool:
    """True when [start_at, end_at] lies inside ONE window (A-03).

    Both ends are inclusive: 12:30-13:00 fits a 09:00-13:00 window. A slot ending exactly at IST
    midnight counts as minute 1440.
    """
    raise NotImplementedError


def validate_windows(windows: Sequence[Window], slot_length_min: int) -> None:
    """Raise WINDOW_OFF_GRID or WINDOW_OVERLAP for a set of windows that belong to one day.

    Every edge must lie on the doctor's slot grid (A-26) and no two windows may overlap. Adjacent
    windows (09:00-13:00 and 13:00-17:00) are fine. The database has the same checks as a backstop.
    """
    raise NotImplementedError


def needs_attention(appt: AppointmentFacts, now: datetime, windows: Sequence[Window]) -> bool:
    """True for a BOOKED future appointment that no longer fits the effective windows (A-27).

    Derived, never stored: it appears when an availability change leaves bookings outside the new
    windows and goes away when they fit again.
    """
    raise NotImplementedError
