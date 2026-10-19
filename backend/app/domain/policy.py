"""The clinic's own rules: the numbers a manager may change without a developer.

The statement fixes these numbers for the assignment (60 days ahead, a 2-hour cancellation
window, two strikes in 30 days); a real clinic wants its own. They live in one row of the
`clinic_policy` table, read by the services and handed to the pure rule functions as an argument,
so the domain still touches no database and no clock. A clinic that never edits them gets exactly
the defaults below, which are the assignment's numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import timedelta

# (smallest, largest) allowed for each setting. The database CHECK constraints repeat these.
BOUNDS: dict[str, tuple[int, int]] = {
    "horizon_days": (1, 365),
    "late_cancel_hours": (0, 72),
    "strike_lookback_days": (1, 180),
    "strikes": (1, 10),
    "undo_minutes": (0, 60),
    "offer_hold_minutes": (5, 240),
    "reminder_first_hours": (0, 168),
    "reminder_second_hours": (0, 48),
}


@dataclass(frozen=True, slots=True)
class Policy:
    horizon_days: int = 60  # how far ahead a visit may be booked
    late_cancel_hours: int = 2  # a cancellation closer than this to the start is a late cancel
    strike_lookback_days: int = 30  # how far back late cancels and no-shows are counted
    strikes: int = 2  # this many in that period require a deposit acknowledgement
    undo_minutes: int = 10  # how long a cancellation can be taken back (0 turns undo off)
    offer_hold_minutes: int = 30  # how long a freed slot is held for the next person waiting
    reminder_first_hours: int = 24  # the first reminder this long before the visit (0 is off)
    reminder_second_hours: int = 2  # the second reminder (0 is off)

    @property
    def late_threshold(self) -> timedelta:
        return timedelta(hours=self.late_cancel_hours)

    @property
    def lookback(self) -> timedelta:
        return timedelta(days=self.strike_lookback_days)

    @property
    def undo_window(self) -> timedelta:
        return timedelta(minutes=self.undo_minutes)

    @property
    def offer_hold(self) -> timedelta:
        return timedelta(minutes=self.offer_hold_minutes)


DEFAULT_POLICY = Policy()
FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in fields(Policy))


def problems(policy: Policy) -> dict[str, str]:
    """What is wrong with `policy`, by field name; empty when it is acceptable."""
    found: dict[str, str] = {}
    for name, (low, high) in BOUNDS.items():
        value = getattr(policy, name)
        if not low <= value <= high:
            found[name] = f"must be between {low} and {high}"
    first, second = policy.reminder_first_hours, policy.reminder_second_hours
    if first and second and first == second:
        found["reminder_second_hours"] = "must differ from the first reminder"
    return found
