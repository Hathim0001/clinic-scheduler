"""The clinic's editable rules: the defaults are the assignment's numbers, and every setting moves
the rule it names (and only that one) when it is passed to the pure functions."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.api.routers.policy import PolicyPatch
from app.domain.booking_window import HORIZON_DAYS, check_booking_window
from app.domain.cancellation import LATE_THRESHOLD, classify_cancellation
from app.domain.errors import ErrorCode
from app.domain.model import CancelledBy, PenaltyEvent, Status
from app.domain.penalties import LOOKBACK, STRIKES, deposit_status
from app.domain.policy import BOUNDS, DEFAULT_POLICY, FIELD_NAMES, Policy, problems
from app.domain.transitions import UNDO_WINDOW, can_undo_cancel
from tests.helpers import ist

pytestmark = pytest.mark.unit

NOW = ist(2026, 11, 2, 8, 0)


def test_the_defaults_are_the_assignments_numbers() -> None:
    assert DEFAULT_POLICY.horizon_days == HORIZON_DAYS == 60
    assert DEFAULT_POLICY.late_threshold == LATE_THRESHOLD == timedelta(hours=2)
    assert DEFAULT_POLICY.lookback == LOOKBACK == timedelta(days=30)
    assert DEFAULT_POLICY.strikes == STRIKES == 2
    assert DEFAULT_POLICY.undo_window == UNDO_WINDOW == timedelta(minutes=10)
    assert DEFAULT_POLICY.offer_hold == timedelta(minutes=30)


def test_every_default_is_inside_its_own_range() -> None:
    assert problems(DEFAULT_POLICY) == {}
    assert set(BOUNDS) == set(FIELD_NAMES)


@pytest.mark.parametrize("name", sorted(BOUNDS))
def test_each_setting_refuses_a_value_just_outside_its_range(name: str) -> None:
    low, high = BOUNDS[name]
    for value in (low - 1, high + 1):
        assert name in problems(Policy(**{name: value}))
    for value in (low, high):
        assert name not in problems(Policy(**{name: value}))


@pytest.mark.parametrize("name", sorted(BOUNDS))
def test_the_request_schema_uses_the_same_ranges_as_the_domain(name: str) -> None:
    low, high = BOUNDS[name]
    PolicyPatch(**{name: low})
    PolicyPatch(**{name: high})
    for value in (low - 1, high + 1):
        with pytest.raises(ValueError, match=name):
            PolicyPatch(**{name: value})


def test_two_equal_reminders_are_refused_but_one_may_be_off() -> None:
    assert "reminder_second_hours" in problems(
        Policy(reminder_first_hours=4, reminder_second_hours=4)
    )
    assert problems(Policy(reminder_first_hours=0, reminder_second_hours=0)) == {}
    assert problems(Policy(reminder_first_hours=24, reminder_second_hours=0)) == {}


def test_a_longer_late_cancel_window_makes_a_three_hour_cancellation_late() -> None:
    start = NOW + timedelta(hours=3)
    assert classify_cancellation(start, NOW, CancelledBy.PATIENT) is Status.CANCELLED
    four = Policy(late_cancel_hours=4).late_threshold
    assert classify_cancellation(start, NOW, CancelledBy.PATIENT, four) is Status.LATE_CANCELLED
    # the clinic's own cancellation is never late, whatever the window
    assert classify_cancellation(start, NOW, CancelledBy.CLINIC, four) is Status.CANCELLED


def test_a_zero_hour_window_makes_only_a_cancellation_after_the_start_late() -> None:
    zero = Policy(late_cancel_hours=0).late_threshold
    start = NOW + timedelta(minutes=1)
    assert classify_cancellation(start, NOW, CancelledBy.PATIENT, zero) is Status.CANCELLED
    assert classify_cancellation(NOW, NOW, CancelledBy.PATIENT, zero) is Status.CANCELLED
    assert (
        classify_cancellation(NOW - timedelta(seconds=1), NOW, CancelledBy.PATIENT, zero)
        is Status.LATE_CANCELLED
    )


def test_a_shorter_horizon_refuses_a_date_the_default_allows() -> None:
    start = ist(2026, 11, 12, 10, 0)  # ten days ahead
    assert check_booking_window(start, NOW) is None
    assert check_booking_window(start, NOW, 9) is ErrorCode.BOOKING_TOO_FAR
    assert check_booking_window(start, NOW, 10) is None


def _strikes(count: int, days_ago: int = 3) -> list[PenaltyEvent]:
    return [
        PenaltyEvent(i + 1, Status.NO_SHOW, NOW - timedelta(days=days_ago, hours=i))
        for i in range(count)
    ]


def test_a_single_strike_flags_a_patient_when_the_clinic_sets_one_strike() -> None:
    assert deposit_status(_strikes(1), NOW).required is False
    flagged = deposit_status(_strikes(1), NOW, Policy(strikes=1))
    assert flagged.required is True


def test_three_strikes_are_needed_when_the_clinic_sets_three() -> None:
    policy = Policy(strikes=3)
    assert deposit_status(_strikes(2), NOW, policy).required is False
    assert deposit_status(_strikes(3), NOW, policy).required is True


def test_a_shorter_look_back_forgets_older_strikes_and_says_how_long() -> None:
    events = _strikes(2, days_ago=10)
    assert deposit_status(events, NOW).required is True
    week = deposit_status(events, NOW, Policy(strike_lookback_days=7))
    assert week.required is False
    assert week.lookback_days == 7


def test_the_flag_lasts_as_long_as_the_clinics_look_back() -> None:
    events = _strikes(2, days_ago=1)
    status = deposit_status(events, NOW, Policy(strike_lookback_days=60))
    assert status.required_until == events[1].at + timedelta(days=60)


def test_a_zero_minute_undo_window_turns_undo_off() -> None:
    cancelled_at = NOW
    start = NOW + timedelta(hours=5)
    assert can_undo_cancel(Status.CANCELLED, cancelled_at, start, NOW, False) is True
    off = timedelta(0)
    assert can_undo_cancel(Status.CANCELLED, cancelled_at, start, NOW, False, off) is False


def test_a_longer_undo_window_keeps_undo_available_longer() -> None:
    cancelled_at = NOW
    start = NOW + timedelta(hours=5)
    twenty = NOW + timedelta(minutes=20)
    assert can_undo_cancel(Status.CANCELLED, cancelled_at, start, twenty, False) is False
    assert (
        can_undo_cancel(Status.CANCELLED, cancelled_at, start, twenty, False, timedelta(minutes=30))
        is True
    )
