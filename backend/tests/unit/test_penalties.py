"""Rule 5, second half: two strikes in the trailing 30 days flag a patient (T-D04 to T-D07)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.model import PenaltyEvent, Status
from app.domain.penalties import LOOKBACK, deposit_status
from tests.helpers import ist

pytestmark = pytest.mark.unit

NOW = ist(2026, 11, 20, 12, 0)


def strike(
    age: timedelta, *, kind: Status = Status.NO_SHOW, appointment_id: int = 1
) -> PenaltyEvent:
    """A strike that happened `age` before NOW (a negative age is in the future)."""
    return PenaltyEvent(appointment_id=appointment_id, kind=kind, at=NOW - age)


def test_a_patient_without_history_is_not_flagged() -> None:
    status = deposit_status([], NOW)
    assert status.required is False
    assert status.reasons == ()
    assert status.required_until is None


def test_one_strike_is_not_enough() -> None:
    """T-D01"""
    status = deposit_status([strike(timedelta(days=5))], NOW)
    assert status.required is False
    assert len(status.reasons) == 1  # still listed, so the UI can show the single strike


def test_two_strikes_flag_the_patient() -> None:
    """T-D02: a no-show and a late cancel within 30 days."""
    events = [
        strike(timedelta(days=5), kind=Status.NO_SHOW, appointment_id=1),
        strike(timedelta(days=9), kind=Status.LATE_CANCELLED, appointment_id=2),
    ]
    assert deposit_status(events, NOW).required is True


def test_three_strikes_also_flag_the_patient() -> None:
    events = [strike(timedelta(days=d), appointment_id=d) for d in (1, 2, 3)]
    assert deposit_status(events, NOW).required is True


def test_a_strike_exactly_thirty_days_old_still_counts() -> None:
    """T-D04 (A-22): the look-back is inclusive at both ends."""
    events = [strike(LOOKBACK), strike(timedelta(days=1), appointment_id=2)]
    assert deposit_status(events, NOW).required is True


def test_a_strike_thirty_days_and_a_second_old_no_longer_counts() -> None:
    """T-D05"""
    events = [strike(LOOKBACK + timedelta(seconds=1)), strike(timedelta(days=1), appointment_id=2)]
    status = deposit_status(events, NOW)
    assert status.required is False
    assert len(status.reasons) == 1


def test_a_strike_a_minute_inside_the_window_counts() -> None:
    events = [strike(LOOKBACK - timedelta(minutes=1)), strike(timedelta(days=1), appointment_id=2)]
    assert deposit_status(events, NOW).required is True


def test_a_strike_dated_in_the_future_is_ignored() -> None:
    """With a test clock moved back, a strike made 'later' has not happened yet."""
    events = [strike(-timedelta(hours=1)), strike(timedelta(days=1), appointment_id=2)]
    assert deposit_status(events, NOW).required is False


def test_reasons_are_listed_newest_first() -> None:
    older = strike(timedelta(days=9), kind=Status.LATE_CANCELLED, appointment_id=2)
    newer = strike(timedelta(days=5), kind=Status.NO_SHOW, appointment_id=1)
    status = deposit_status([older, newer], NOW)
    assert [e.appointment_id for e in status.reasons] == [1, 2]


def test_the_flag_lasts_until_the_second_most_recent_strike_is_thirty_days_old() -> None:
    """T-D06: strikes on 29 Oct 10:00 and 28 Oct 15:10 flag the patient through 27 Nov 15:10."""
    newer = PenaltyEvent(12, Status.NO_SHOW, ist(2026, 10, 29, 10, 0))
    older = PenaltyEvent(9, Status.LATE_CANCELLED, ist(2026, 10, 28, 15, 10))
    until = ist(2026, 11, 27, 15, 10)

    now = ist(2026, 11, 2, 9, 0)
    status = deposit_status([older, newer], now)
    assert status.required_until == until

    assert deposit_status([older, newer], until).required is True  # inclusive at that instant
    one_second_later = until + timedelta(seconds=1)
    assert deposit_status([older, newer], one_second_later).required is False


def test_with_three_strikes_the_flag_follows_the_second_newest() -> None:
    events = [strike(timedelta(days=d), appointment_id=d) for d in (2, 10, 25)]
    status = deposit_status(events, NOW)
    assert status.required_until == NOW - timedelta(days=10) + LOOKBACK


def test_an_unflagged_patient_has_no_end_date() -> None:
    assert deposit_status([strike(timedelta(days=5))], NOW).required_until is None


def test_any_iterable_of_events_is_accepted() -> None:
    generator = (strike(timedelta(days=d), appointment_id=d) for d in (1, 2))
    assert deposit_status(generator, NOW).required is True
