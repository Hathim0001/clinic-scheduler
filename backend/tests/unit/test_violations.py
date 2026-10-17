"""The wording and details of a refusal, and the helpers that find who is in the way."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.domain.errors import ConflictError, ErrorCode, RuleViolation
from app.domain.model import (
    AppointmentFacts,
    DoctorFacts,
    PenaltyEvent,
    SlotContext,
    Status,
    UnavailableReason,
)
from app.domain.penalties import deposit_status
from app.domain.slots import (
    conflicting_appointment,
    overlapping_patient_appointment,
    unavailable_reason,
)
from app.domain.violations import deposit_required_error, violation_error
from tests.helpers import appt_facts, doctor_facts, ist, slot_ctx

pytestmark = pytest.mark.unit

NOW = ist(2026, 11, 2, 8, 0)
START = ist(2026, 11, 2, 10, 0)


def ctx_with(
    *,
    doctor: DoctorFacts | None = None,
    windows: Sequence[tuple[int, int]] = ((540, 780),),
    doctor_appts: Sequence[AppointmentFacts] = (),
    patient_appts: Sequence[AppointmentFacts] = (),
) -> SlotContext:
    return slot_ctx(
        now=NOW,
        doctor=doctor,
        windows=windows,
        doctor_appts=doctor_appts,
        patient_appts=patient_appts,
    )


@pytest.mark.parametrize(
    ("code", "cls"),
    [
        (ErrorCode.BOOKING_IN_PAST, RuleViolation),
        (ErrorCode.BOOKING_TOO_FAR, RuleViolation),
        (ErrorCode.OFF_GRID, RuleViolation),
        (ErrorCode.OUTSIDE_AVAILABILITY, RuleViolation),
        (ErrorCode.DAILY_CAP_REACHED, ConflictError),
        (ErrorCode.SLOT_TAKEN, ConflictError),
        (ErrorCode.PATIENT_OVERLAP, ConflictError),
    ],
)
def test_every_slot_violation_becomes_the_matching_error(code: ErrorCode, cls: type) -> None:
    error = violation_error(code, START, ctx_with(doctor_appts=[appt_facts(START)]))
    assert type(error) is cls
    assert error.code is code
    assert error.message.endswith(".")


def test_a_code_that_is_not_a_slot_violation_is_refused() -> None:
    with pytest.raises(ValueError, match="not a slot violation"):
        violation_error(ErrorCode.DEPOSIT_REQUIRED, START, ctx_with())


def test_the_messages_name_the_time_in_india_not_utc() -> None:
    error = violation_error(ErrorCode.BOOKING_IN_PAST, START, ctx_with())
    assert "02 Nov 2026, 10:00" in error.message


def test_outside_availability_lists_the_working_hours() -> None:
    error = violation_error(ErrorCode.OUTSIDE_AVAILABILITY, ist(2026, 11, 2, 14, 0), ctx_with())
    assert error.details["windows"] == [{"start": "09:00", "end": "13:00"}]
    assert "09:00-13:00" in error.message


def test_outside_availability_on_a_leave_day_says_so() -> None:
    error = violation_error(ErrorCode.OUTSIDE_AVAILABILITY, START, ctx_with(windows=()))
    assert error.details["windows"] == []
    assert "not working that day" in error.message


def test_the_cap_error_names_the_cap() -> None:
    ctx = ctx_with(doctor=doctor_facts(cap=3))
    error = violation_error(ErrorCode.DAILY_CAP_REACHED, START, ctx)
    assert error.details == {"daily_cap": 3}
    assert "maximum of 3" in error.message


def test_a_slot_taken_by_someone_else_says_so() -> None:
    ctx = ctx_with(doctor_appts=[appt_facts(START, patient=8, appointment_id=41)])
    error = violation_error(ErrorCode.SLOT_TAKEN, START, ctx, patient_id=7)
    assert error.details == {"appointment_id": 41, "same_patient": False}
    assert "another booking" in error.message


def test_a_slot_taken_by_the_same_patient_is_a_double_click() -> None:
    ctx = ctx_with(doctor_appts=[appt_facts(START, patient=7, appointment_id=41)])
    error = violation_error(ErrorCode.SLOT_TAKEN, START, ctx, patient_id=7)
    assert error.details == {"appointment_id": 41, "same_patient": True}
    assert "already has an appointment" in error.message


def test_a_database_race_has_no_occupant_to_name() -> None:
    """The pre-check saw a free slot; only the constraint knows. The error still makes sense."""
    error = violation_error(ErrorCode.SLOT_TAKEN, START, ctx_with())
    assert error.details == {}


def test_a_patient_overlap_names_the_other_appointment() -> None:
    other = appt_facts(START, doctor=2, patient=7, appointment_id=55)
    error = violation_error(ErrorCode.PATIENT_OVERLAP, START, ctx_with(patient_appts=[other]))
    assert error.details == {"appointment_id": 55}


def test_the_deposit_error_matches_the_example_in_the_plan() -> None:
    """Strikes on 28 Oct 15:10 (late cancel) and 29 Oct 10:00 (no-show), looked at on 2 Nov."""
    events = [
        PenaltyEvent(9, Status.LATE_CANCELLED, ist(2026, 10, 28, 15, 10)),
        PenaltyEvent(12, Status.NO_SHOW, ist(2026, 10, 29, 10, 0)),
    ]
    error = deposit_required_error(deposit_status(events, ist(2026, 11, 2, 9, 0)))
    assert error.code is ErrorCode.DEPOSIT_REQUIRED
    assert isinstance(error, RuleViolation)
    assert "2 late cancellations or no-shows in the last 30 days" in error.message
    assert error.details == {
        "required_until": "2026-11-27T15:10:00+05:30",
        "reasons": [
            {"appointment_id": 12, "type": "NO_SHOW", "at": "2026-10-29T10:00:00+05:30"},
            {"appointment_id": 9, "type": "LATE_CANCELLED", "at": "2026-10-28T15:10:00+05:30"},
        ],
    }


def test_the_occupant_of_a_slot_is_found_among_active_appointments_only() -> None:
    cancelled = appt_facts(START, status=Status.CANCELLED, appointment_id=1)
    booked = appt_facts(START, patient=9, appointment_id=2)
    assert conflicting_appointment(START, ctx_with(doctor_appts=[cancelled, booked])) == booked
    assert conflicting_appointment(START, ctx_with(doctor_appts=[cancelled])) is None
    assert conflicting_appointment(ist(2026, 11, 2, 11, 0), ctx_with(doctor_appts=[booked])) is None


def test_the_patients_own_clash_is_found_among_active_appointments_only() -> None:
    cancelled = appt_facts(START, doctor=2, status=Status.LATE_CANCELLED, appointment_id=1)
    noshow = appt_facts(START, doctor=2, status=Status.NO_SHOW, appointment_id=2)
    ctx = ctx_with(patient_appts=[cancelled, noshow])
    assert overlapping_patient_appointment(START, ctx) == noshow
    assert overlapping_patient_appointment(ist(2026, 11, 2, 12, 0), ctx) is None


@pytest.mark.parametrize(
    ("violations", "expected"),
    [
        ([], UnavailableReason.NO_AVAILABILITY),
        ([None], None),
        ([ErrorCode.SLOT_TAKEN, None], None),
        ([ErrorCode.BOOKING_IN_PAST, ErrorCode.BOOKING_IN_PAST], UnavailableReason.DATE_IN_PAST),
        ([ErrorCode.BOOKING_TOO_FAR], UnavailableReason.DATE_TOO_FAR),
        (
            [ErrorCode.BOOKING_IN_PAST, ErrorCode.DAILY_CAP_REACHED, ErrorCode.DAILY_CAP_REACHED],
            UnavailableReason.DAILY_CAP_REACHED,
        ),
        ([ErrorCode.SLOT_TAKEN, ErrorCode.SLOT_TAKEN], UnavailableReason.FULLY_BOOKED),
        (
            [ErrorCode.BOOKING_IN_PAST, ErrorCode.SLOT_TAKEN, ErrorCode.PATIENT_OVERLAP],
            UnavailableReason.FULLY_BOOKED,
        ),
    ],
    ids=[
        "no grid starts",
        "one free",
        "one free among taken",
        "all in the past",
        "beyond the horizon",
        "cap beats past",
        "all taken",
        "past, taken and busy",
    ],
)
def test_the_reason_a_day_is_empty_comes_from_why_each_slot_failed(
    violations: list[ErrorCode | None], expected: UnavailableReason | None
) -> None:
    assert unavailable_reason(violations) is expected
