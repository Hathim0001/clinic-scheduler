"""The slot rules for a visit that lasts more than one of the doctor's slots."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.errors import ErrorCode
from app.domain.model import Status
from app.domain.slots import (
    conflicting_appointment,
    first_violation,
    free_slots,
    overlapping_patient_appointment,
)
from tests.helpers import appt_facts, ist, slot_ctx

pytestmark = pytest.mark.unit

NOW = ist(2026, 11, 2, 8, 0)
DAY = NOW.date()


def at(hour: int, minute: int = 0) -> datetime:
    return ist(2026, 11, 2, hour, minute)


def test_a_one_slot_default_is_unchanged() -> None:
    ctx = slot_ctx(now=NOW)
    assert first_violation(at(10), ctx) is None
    assert first_violation(at(10), ctx, 1) is None


def test_the_whole_visit_must_fit_inside_a_window() -> None:
    ctx = slot_ctx(now=NOW, windows=[(540, 780)])  # 09:00 to 13:00, 30-minute slots
    assert first_violation(at(12), ctx, 2) is None  # ends exactly at 13:00
    assert first_violation(at(12, 30), ctx, 2) is ErrorCode.OUTSIDE_AVAILABILITY
    assert first_violation(at(12, 30), ctx, 1) is None


def test_a_visit_cannot_cross_the_gap_between_two_windows() -> None:
    ctx = slot_ctx(now=NOW, windows=[(540, 660), (720, 780)])  # 09-11 and 12-13
    assert first_violation(at(10), ctx, 2) is None
    assert first_violation(at(10, 30), ctx, 2) is ErrorCode.OUTSIDE_AVAILABILITY


@pytest.mark.parametrize(
    ("booked_start", "starts", "taken"),
    [
        (at(10), at(9, 30), True),  # 09:30-10:30 runs into 10:00
        (at(10), at(9), False),  # 09:00-10:00 stops where 10:00 begins
        (at(10), at(10), True),
        (at(10), at(10, 30), False),
    ],
)
def test_every_part_of_a_long_visit_is_checked_against_the_doctors_bookings(
    booked_start: datetime, starts: datetime, taken: bool
) -> None:
    ctx = slot_ctx(now=NOW, doctor_appts=[appt_facts(booked_start)])
    expected = ErrorCode.SLOT_TAKEN if taken else None
    assert first_violation(starts, ctx, 2) is expected


def test_a_booking_in_the_middle_of_a_long_visit_blocks_it() -> None:
    ctx = slot_ctx(now=NOW, doctor_appts=[appt_facts(at(10), minutes=15)])
    assert first_violation(at(9, 30), ctx, 2) is ErrorCode.SLOT_TAKEN
    assert conflicting_appointment(at(9, 30), ctx, 2) is not None
    assert conflicting_appointment(at(9, 30), ctx, 1) is None


def test_the_patients_other_appointments_block_a_long_visit_too() -> None:
    mine = appt_facts(at(10, 30), doctor=2, patient=7)
    ctx = slot_ctx(now=NOW, patient_appts=[mine])
    assert first_violation(at(10), ctx, 2) is ErrorCode.PATIENT_OVERLAP
    assert overlapping_patient_appointment(at(10), ctx, 2) is not None
    assert overlapping_patient_appointment(at(10), ctx, 1) is None


def test_a_cancelled_booking_does_not_block() -> None:
    ctx = slot_ctx(now=NOW, doctor_appts=[appt_facts(at(10), status=Status.CANCELLED)])
    assert first_violation(at(9, 30), ctx, 2) is None


def test_free_starts_for_a_long_visit() -> None:
    ctx = slot_ctx(now=NOW, windows=[(540, 660)], doctor_appts=[appt_facts(at(10))])  # 09:00-11:00
    assert free_slots(DAY, ctx, 1) == [at(9), at(9, 30), at(10, 30)]
    assert free_slots(DAY, ctx, 2) == [at(9)]  # only 09:00-10:00 fits around the 10:00 booking
    assert free_slots(DAY, ctx, 4) == []


def test_a_long_visit_is_still_one_appointment_for_the_cap() -> None:
    from tests.helpers import doctor_facts

    ctx = slot_ctx(now=NOW, doctor=doctor_facts(cap=1), doctor_appts=[])
    assert first_violation(at(10), ctx, 4) is None
    booked = slot_ctx(
        now=NOW,
        doctor=doctor_facts(cap=1),
        doctor_appts=[appt_facts(at(9), minutes=int(timedelta(hours=2).total_seconds() // 60))],
    )
    assert first_violation(at(12), booked, 1) is ErrorCode.DAILY_CAP_REACHED
