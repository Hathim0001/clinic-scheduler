"""One definition of "this slot is bookable", used for offering slots and for accepting bookings.

`first_violation` is the only place the booking rules are combined. The free-slot list, the day
schedule and the booking endpoint all call it, so the UI can never offer a slot that the API then
refuses (plan ADR-11).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date, datetime, timedelta

from app.domain.availability import fits_in_windows
from app.domain.booking_window import check_booking_window
from app.domain.errors import ErrorCode
from app.domain.model import (
    ACTIVE_STATUSES,
    AppointmentFacts,
    SlotContext,
    UnavailableReason,
    Window,
)
from app.domain.timeutil import IST, at_ist, ist_date


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open interval overlap: 10:00-10:30 and 10:30-11:00 do not overlap."""
    return a_start < b_end and b_start < a_end


def is_on_grid(start_at: datetime, slot_length_min: int) -> bool:
    """Rule 1b: the IST start has zero seconds and its minute-of-day divides by the slot length.

    The grid is anchored at IST midnight (A-01), so a 30-minute doctor cannot be booked at 09:15
    and 09:00:30 is off the grid of every doctor (A-31).
    """
    local = start_at.astimezone(IST)
    minute_of_day = local.hour * 60 + local.minute
    return local.second == 0 and local.microsecond == 0 and minute_of_day % slot_length_min == 0


def first_violation(start_at: datetime, ctx: SlotContext, slots: int = 1) -> ErrorCode | None:
    """The first rule the slot breaks, or None when it is bookable (before the deposit check).

    Checked in a fixed order, cheapest and most basic first:
    DOCTOR_NOT_ACCEPTING, BOOKING_IN_PAST / BOOKING_TOO_FAR, OFF_GRID, OUTSIDE_AVAILABILITY,
    DAILY_CAP_REACHED, SLOT_TAKEN, PATIENT_OVERLAP. The cap comes before the overlap checks because
    a full day makes every slot unavailable and "fully booked" is the most useful message.

    `slots` is how many of the doctor's slots the visit lasts. The start must be on the grid, the
    whole visit must fit inside one window, and nothing of the doctor's or the patient's may overlap
    any part of it.
    """
    length = ctx.doctor.slot_length_min
    end_at = start_at + timedelta(minutes=length * slots)

    if not ctx.doctor.accepting_bookings:
        return ErrorCode.DOCTOR_NOT_ACCEPTING
    window_problem = check_booking_window(start_at, ctx.now, ctx.policy.horizon_days)
    if window_problem is not None:
        return window_problem
    if not is_on_grid(start_at, length):
        return ErrorCode.OFF_GRID
    if not fits_in_windows(start_at, end_at, ctx.windows):
        return ErrorCode.OUTSIDE_AVAILABILITY

    day = ist_date(start_at)
    doctor_active = [a for a in ctx.doctor_appts if a.status in ACTIVE_STATUSES]
    if sum(1 for a in doctor_active if ist_date(a.start_at) == day) >= ctx.doctor.daily_cap:
        return ErrorCode.DAILY_CAP_REACHED
    if any(overlaps(start_at, end_at, a.start_at, a.end_at) for a in doctor_active):
        return ErrorCode.SLOT_TAKEN
    if any(
        a.status in ACTIVE_STATUSES and overlaps(start_at, end_at, a.start_at, a.end_at)
        for a in ctx.patient_appts
    ):
        return ErrorCode.PATIENT_OVERLAP
    return None


def candidate_starts(
    day: date, windows: Sequence[Window], slot_length_min: int
) -> Iterator[datetime]:
    """Every grid start inside the windows of `day`, as UTC instants, in time order."""
    for window in sorted(windows, key=lambda w: (w.start_min, w.end_min)):
        # The first grid point at or after the window start (a window edge may be off the grid).
        minute = -(-window.start_min // slot_length_min) * slot_length_min
        while minute + slot_length_min <= window.end_min:
            yield at_ist(day, minute)
            minute += slot_length_min


def free_slots(day: date, ctx: SlotContext, slots: int = 1) -> list[datetime]:
    """The starts of `day` where a visit of `slots` slots is accepted by `first_violation`."""
    return [
        start
        for start in candidate_starts(day, ctx.windows, ctx.doctor.slot_length_min)
        if first_violation(start, ctx, slots) is None
    ]


def conflicting_appointment(
    start_at: datetime, ctx: SlotContext, slots: int = 1
) -> AppointmentFacts | None:
    """The doctor's active appointment that overlaps a visit of `slots` slots from `start_at`."""
    end_at = start_at + timedelta(minutes=ctx.doctor.slot_length_min * slots)
    return next(
        (
            a
            for a in ctx.doctor_appts
            if a.status in ACTIVE_STATUSES and overlaps(start_at, end_at, a.start_at, a.end_at)
        ),
        None,
    )


def overlapping_patient_appointment(
    start_at: datetime, ctx: SlotContext, slots: int = 1
) -> AppointmentFacts | None:
    """The patient's active appointment (with any doctor) that overlaps the visit, if any."""
    end_at = start_at + timedelta(minutes=ctx.doctor.slot_length_min * slots)
    return next(
        (
            a
            for a in ctx.patient_appts
            if a.status in ACTIVE_STATUSES and overlaps(start_at, end_at, a.start_at, a.end_at)
        ),
        None,
    )


def unavailable_reason(violations: Sequence[ErrorCode | None]) -> UnavailableReason | None:
    """Why a day has no free slot, from the first violation of each of its grid starts.

    None means at least one start is free. Otherwise: no grid starts at all is NO_AVAILABILITY;
    all in the past or all beyond the horizon name the date; a reached cap beats "fully booked".
    """
    if any(violation is None for violation in violations):
        return None
    if not violations:
        return UnavailableReason.NO_AVAILABILITY
    if all(violation is ErrorCode.DOCTOR_NOT_ACCEPTING for violation in violations):
        return UnavailableReason.NOT_ACCEPTING
    if all(violation is ErrorCode.BOOKING_IN_PAST for violation in violations):
        return UnavailableReason.DATE_IN_PAST
    if all(violation is ErrorCode.BOOKING_TOO_FAR for violation in violations):
        return UnavailableReason.DATE_TOO_FAR
    if ErrorCode.DAILY_CAP_REACHED in violations:
        return UnavailableReason.DAILY_CAP_REACHED
    return UnavailableReason.FULLY_BOOKED
