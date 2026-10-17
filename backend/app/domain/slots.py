"""One definition of "this slot is bookable", used for offering slots and for accepting bookings.

`first_violation` is the only place the booking rules are combined. The free-slot list, the day
schedule and the booking endpoint all call it, so the UI can never offer a slot that the API then
refuses (plan ADR-11).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date, datetime

from app.domain.errors import ErrorCode
from app.domain.model import SlotContext, Window


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open interval overlap: 10:00-10:30 and 10:30-11:00 do not overlap."""
    raise NotImplementedError


def is_on_grid(start_at: datetime, slot_length_min: int) -> bool:
    """Rule 1b: the IST start has zero seconds and its minute-of-day divides by the slot length.

    The grid is anchored at IST midnight (A-01), so a 30-minute doctor cannot be booked at 09:15
    and 09:00:30 is off the grid of every doctor (A-31).
    """
    raise NotImplementedError


def first_violation(start_at: datetime, ctx: SlotContext) -> ErrorCode | None:
    """The first rule the slot breaks, or None when it is bookable (before the deposit check).

    Checked in a fixed order, cheapest and most basic first:
    BOOKING_IN_PAST / BOOKING_TOO_FAR, OFF_GRID, OUTSIDE_AVAILABILITY, DAILY_CAP_REACHED,
    SLOT_TAKEN, PATIENT_OVERLAP. The cap comes before the overlap checks because a full day makes
    every slot unavailable and "fully booked" is the most useful message.
    """
    raise NotImplementedError


def candidate_starts(
    day: date, windows: Sequence[Window], slot_length_min: int
) -> Iterator[datetime]:
    """Every grid start inside the windows of `day`, as UTC instants, in time order."""
    raise NotImplementedError


def free_slots(day: date, ctx: SlotContext) -> list[datetime]:
    """The starts of `day` that `first_violation` accepts."""
    raise NotImplementedError
