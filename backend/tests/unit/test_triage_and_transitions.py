"""The urgent-symptom check, check-in and correction rules, and a doctor who is not accepting."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import Status, UnavailableReason
from app.domain.slots import first_violation, unavailable_reason
from app.domain.transitions import CORRECTIONS, check_can_check_in, check_correction
from app.domain.triage import looks_urgent
from tests.helpers import doctor_facts, ist, slot_ctx

pytestmark = pytest.mark.unit

START = ist(2026, 11, 2, 12, 0)


@pytest.mark.parametrize(
    "text",
    [
        "Severe chest pain since morning",
        "my father has chest tightness",
        "cannot breathe properly",
        "Can't breathe at night",
        "shortness of breath on stairs",
        "suspected STROKE, face drooping",
        "he passed out twice",
        "had a seizure last night",
        "coughing blood",
        "thinking about suicide",
        "took an overdose",
        "child is choking",
        "heavy bleeding after surgery",
    ],
)
def test_serious_symptoms_are_flagged(text: str) -> None:
    assert looks_urgent(text)


@pytest.mark.parametrize(
    "text",
    [
        "Fever, 3 days",
        "Routine check-up",
        "Knee pain when walking",
        "Follow-up for blood pressure",
        "Chest x-ray report review",
        "Strokes of the paintbrush",  # a word that merely starts like a symptom
        "",
    ],
)
def test_ordinary_reasons_are_not_flagged(text: str) -> None:
    assert not looks_urgent(text)


def test_check_in_opens_on_the_day_and_not_before() -> None:
    check_can_check_in(Status.BOOKED, START, START - timedelta(hours=2))
    check_can_check_in(Status.BOOKED, START, START + timedelta(hours=1))
    with pytest.raises(ConflictError) as raised:
        check_can_check_in(Status.BOOKED, START, START - timedelta(days=1))
    assert raised.value.code is ErrorCode.TOO_EARLY_TO_MARK


@pytest.mark.parametrize("status", [Status.COMPLETED, Status.CANCELLED, Status.NO_SHOW])
def test_only_a_booked_appointment_can_check_in(status: Status) -> None:
    with pytest.raises(ConflictError) as raised:
        check_can_check_in(status, START, START)
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_the_allowed_corrections() -> None:
    for current, targets in CORRECTIONS.items():
        for target in targets:
            check_correction(current, target)


@pytest.mark.parametrize("current", list(Status))
@pytest.mark.parametrize("target", list(Status))
def test_every_other_pair_is_refused(current: Status, target: Status) -> None:
    if target in CORRECTIONS.get(current, frozenset()):
        return
    with pytest.raises(ConflictError) as raised:
        check_correction(current, target)
    assert raised.value.code is ErrorCode.INVALID_CORRECTION
    assert raised.value.details["status"] == current.value


def test_a_doctor_who_is_not_accepting_refuses_every_slot_first() -> None:
    now = ist(2026, 11, 2, 8, 0)
    ctx = slot_ctx(now=now, doctor=doctor_facts(accepting=False), windows=[(540, 780)])
    assert first_violation(ist(2026, 11, 2, 10, 0), ctx) is ErrorCode.DOCTOR_NOT_ACCEPTING
    # even a slot that would also be off the grid or in the past gives this answer
    assert first_violation(ist(2026, 11, 2, 7, 5), ctx) is ErrorCode.DOCTOR_NOT_ACCEPTING


def test_a_day_of_refusals_for_that_reason_is_named() -> None:
    violations = [ErrorCode.DOCTOR_NOT_ACCEPTING] * 4
    assert unavailable_reason(violations) is UnavailableReason.NOT_ACCEPTING
