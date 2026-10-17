"""The appointment state machine: which buttons are offered, which changes are accepted
(T-M01 to T-M03, T-C06)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest

from app.domain.cancellation import classify_cancellation
from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import CancelledBy, Status
from app.domain.transitions import allowed_actions, check_can_cancel, check_can_mark
from tests.helpers import ist

pytestmark = pytest.mark.unit

START = ist(2026, 11, 2, 12, 0)
TERMINAL = [Status.COMPLETED, Status.CANCELLED, Status.LATE_CANCELLED, Status.NO_SHOW]


def test_a_booked_appointment_can_be_cancelled_or_rescheduled_before_it_starts() -> None:
    """T-M03, first half."""
    one_minute_before = START - timedelta(minutes=1)
    assert allowed_actions(Status.BOOKED, START, one_minute_before) == ["cancel", "reschedule"]
    assert allowed_actions(Status.BOOKED, START, START - timedelta(days=30)) == [
        "cancel",
        "reschedule",
    ]


def test_a_booked_appointment_can_be_marked_from_its_start_on() -> None:
    """T-M03, second half: complete and no-show appear at the start, never before (A-18)."""
    assert allowed_actions(Status.BOOKED, START, START) == ["complete", "no-show"]
    assert allowed_actions(Status.BOOKED, START, START + timedelta(days=3)) == [
        "complete",
        "no-show",
    ]


@pytest.mark.parametrize("status", TERMINAL)
@pytest.mark.parametrize(
    "offset",
    [timedelta(days=-1), timedelta(0), timedelta(days=1)],
    ids=["a day before", "at the start", "a day after"],
)
def test_a_finished_appointment_offers_no_actions(status: Status, offset: timedelta) -> None:
    """A-19: the four other statuses are terminal."""
    assert allowed_actions(status, START, START + offset) == []


def test_a_booked_appointment_can_be_cancelled() -> None:
    check_can_cancel(Status.BOOKED)


@pytest.mark.parametrize("status", TERMINAL)
def test_only_a_booked_appointment_can_be_cancelled(status: Status) -> None:
    """T-C06: cancelling twice, or cancelling something already finished, is a conflict."""
    with pytest.raises(ConflictError) as raised:
        check_can_cancel(status)
    assert raised.value.code is ErrorCode.INVALID_TRANSITION
    assert raised.value.details["status"] == status.value  # so the UI can say which status


@pytest.mark.parametrize(
    "now",
    [START, START + timedelta(minutes=1), START + timedelta(days=2)],
    ids=["at the start", "a minute after", "two days after"],
)
def test_a_booked_appointment_can_be_marked_once_it_has_started(now: datetime) -> None:
    check_can_mark(Status.BOOKED, START, now)


@pytest.mark.parametrize(
    "now",
    [START - timedelta(minutes=1), START - timedelta(seconds=1), START - timedelta(days=1)],
    ids=["a minute early", "a second early", "a day early"],
)
def test_marking_before_the_start_is_too_early(now: datetime) -> None:
    """T-M01: a no-show at 11:59 for a 12:00 appointment."""
    with pytest.raises(ConflictError) as raised:
        check_can_mark(Status.BOOKED, START, now)
    assert raised.value.code is ErrorCode.TOO_EARLY_TO_MARK


@pytest.mark.parametrize("status", TERMINAL)
def test_only_a_booked_appointment_can_be_marked(status: Status) -> None:
    """T-M02: complete on a cancelled appointment."""
    with pytest.raises(ConflictError) as raised:
        check_can_mark(status, START, START + timedelta(hours=1))
    assert raised.value.code is ErrorCode.INVALID_TRANSITION
    assert raised.value.details["status"] == status.value


def test_the_status_is_checked_before_the_time() -> None:
    """A cancelled appointment in the future is an invalid transition, not 'too early'."""
    with pytest.raises(ConflictError) as raised:
        check_can_mark(Status.CANCELLED, START, START - timedelta(hours=1))
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def accepts(action: Callable[[], object]) -> bool:
    try:
        action()
    except ConflictError:
        return False
    return True


@pytest.mark.parametrize("status", list(Status))
@pytest.mark.parametrize(
    "now",
    [START - timedelta(hours=1), START, START + timedelta(hours=1)],
    ids=["before", "at start", "after"],
)
def test_the_offered_actions_are_exactly_the_ones_the_rules_accept(
    status: Status, now: datetime
) -> None:
    """The UI enables a button only for an offered action, so offered and accepted must agree."""
    offered = allowed_actions(status, START, now)

    def cancel() -> None:
        check_can_cancel(status)
        classify_cancellation(START, now, CancelledBy.PATIENT)

    assert accepts(cancel) == ("cancel" in offered)
    assert accepts(lambda: check_can_mark(status, START, now)) == ("complete" in offered)
    assert ("no-show" in offered) == ("complete" in offered)
    assert ("reschedule" in offered) == ("cancel" in offered)
