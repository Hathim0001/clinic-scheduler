"""Rule 5, first half: cancelling at least 2 hours ahead is a normal Cancel, later is a Late-Cancel
(T-C01 to T-C05)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.cancellation import classify_cancellation
from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import CancelledBy, Status
from tests.helpers import ist

pytestmark = pytest.mark.unit

START = ist(2026, 11, 2, 12, 0)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (ist(2026, 11, 2, 10, 0, 0), Status.CANCELLED),  # T-C01: exactly 2h00m00s before
        (ist(2026, 11, 2, 10, 0, 1), Status.LATE_CANCELLED),  # 1h59m59s before
        (ist(2026, 11, 2, 10, 1), Status.LATE_CANCELLED),  # T-C02: 1h59m before
        (ist(2026, 11, 2, 9, 59), Status.CANCELLED),  # T-C03: 2h01m before
        (ist(2026, 11, 2, 11, 59, 59), Status.LATE_CANCELLED),  # one second before the start
        (ist(2026, 11, 1, 12, 0), Status.CANCELLED),  # a day before
    ],
    ids=["2h00m00s", "1h59m59s", "1h59m", "2h01m", "1s before start", "1 day before"],
)
def test_a_patient_cancellation_is_normal_or_late_around_the_two_hour_line(
    now: datetime, expected: Status
) -> None:
    assert classify_cancellation(START, now, CancelledBy.PATIENT) is expected


@pytest.mark.parametrize(
    "now",
    [ist(2026, 11, 2, 11, 30), ist(2026, 11, 2, 11, 59, 59)],
    ids=["30 minutes before", "1 second before"],
)
def test_a_cancellation_by_the_clinic_is_always_a_normal_cancel(now: datetime) -> None:
    """T-C05 (A-09): the clinic's own changes must never count against a patient."""
    assert classify_cancellation(START, now, CancelledBy.CLINIC) is Status.CANCELLED


@pytest.mark.parametrize(
    "now",
    [START, START + timedelta(minutes=1), START + timedelta(days=1)],
    ids=["at the start", "1 minute after", "1 day after"],
)
def test_an_appointment_cannot_be_cancelled_at_or_after_its_start(now: datetime) -> None:
    """T-C04 (A-08)"""
    with pytest.raises(ConflictError) as raised:
        classify_cancellation(START, now, CancelledBy.PATIENT)
    assert raised.value.code is ErrorCode.APPOINTMENT_ALREADY_STARTED


def test_the_clinic_cannot_cancel_after_the_start_either() -> None:
    with pytest.raises(ConflictError) as raised:
        classify_cancellation(START, START, CancelledBy.CLINIC)
    assert raised.value.code is ErrorCode.APPOINTMENT_ALREADY_STARTED
