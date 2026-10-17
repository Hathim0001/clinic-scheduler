"""The error catalogue: every code is listed once, classified, and maps to one HTTP status
(plan section 22.3)."""

from __future__ import annotations

import pytest

from app.domain.errors import (
    ConflictError,
    DomainError,
    ErrorCode,
    NotFoundError,
    RuleViolation,
    domain_error,
)

pytestmark = pytest.mark.unit

HTTP_STATUS = {
    "MALFORMED_JSON": 400,
    "VALIDATION_ERROR": 422,
    "INVALID_TEST_CLOCK": 400,
    "PAYLOAD_TOO_LARGE": 413,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "DOCTOR_NOT_FOUND": 404,
    "PATIENT_NOT_FOUND": 404,
    "APPOINTMENT_NOT_FOUND": 404,
    "REFERENCE_NOT_FOUND": 404,
    "WAITLIST_ENTRY_NOT_FOUND": 404,
    "DOCTOR_NOT_ACCEPTING": 409,
    "POSSIBLE_DUPLICATE": 409,
    "ALREADY_CHECKED_IN": 409,
    "IDEMPOTENCY_KEY_REUSED": 409,
    "INVALID_CORRECTION": 409,
    "BOOKING_IN_PAST": 422,
    "BOOKING_TOO_FAR": 422,
    "OFF_GRID": 422,
    "OUTSIDE_AVAILABILITY": 422,
    "DEPOSIT_REQUIRED": 422,
    "RESCHEDULE_NO_CHANGE": 422,
    "WINDOW_OVERLAP": 422,
    "WINDOW_OFF_GRID": 422,
    "DAILY_CAP_REACHED": 409,
    "SLOT_TAKEN": 409,
    "PATIENT_OVERLAP": 409,
    "INVALID_TRANSITION": 409,
    "APPOINTMENT_ALREADY_STARTED": 409,
    "TOO_EARLY_TO_MARK": 409,
    "AVAILABILITY_CONFLICTS": 409,
    "PHONE_TAKEN": 409,
    "SLOT_LENGTH_LOCKED": 409,
    "DOCTOR_HAS_APPOINTMENTS": 409,
    "ALREADY_WAITING": 409,
    "OFFER_EXPIRED": 409,
    "CONFLICT": 409,
    "RATE_LIMITED": 429,
    "SERVICE_UNAVAILABLE": 503,
    "INTERNAL_ERROR": 500,
}
KIND_STATUS = {"not_found": 404, "rule": 422, "conflict": 409}
# Raised only at the HTTP edge or by infrastructure code, never built by the domain.
EDGE_ONLY = {
    ErrorCode.MALFORMED_JSON,
    ErrorCode.INVALID_TEST_CLOCK,
    ErrorCode.PAYLOAD_TOO_LARGE,
    ErrorCode.NOT_FOUND,
    ErrorCode.METHOD_NOT_ALLOWED,
    ErrorCode.RATE_LIMITED,
    ErrorCode.SERVICE_UNAVAILABLE,
    ErrorCode.INTERNAL_ERROR,
}
DOMAIN_CODES = [code for code in ErrorCode if code not in EDGE_ONLY]


def test_the_catalogue_holds_exactly_the_31_codes_of_the_catalogue() -> None:
    assert {code.value for code in ErrorCode} == set(HTTP_STATUS)
    assert len(ErrorCode) == 40


def test_each_code_is_spelled_like_its_name() -> None:
    """Clients match on the string, so a typo in a value would silently change the contract."""
    assert all(code.value == code.name for code in ErrorCode)


@pytest.mark.parametrize("code", DOMAIN_CODES)
def test_a_domain_code_builds_the_exception_class_with_the_right_status(code: ErrorCode) -> None:
    error = domain_error(code, "A sentence.", doctor_id=3)
    assert isinstance(error, DomainError)
    assert error.code is code
    assert error.message == "A sentence."
    assert error.details == {"doctor_id": 3}
    assert str(error) == "A sentence."
    assert KIND_STATUS[error.kind] == HTTP_STATUS[code.value]


@pytest.mark.parametrize("code", sorted(EDGE_ONLY))
def test_edge_and_infrastructure_codes_are_not_domain_errors(code: ErrorCode) -> None:
    with pytest.raises(ValueError, match="not a domain error code"):
        domain_error(code, "Not for the domain.")


@pytest.mark.parametrize(
    ("cls", "kind"),
    [(NotFoundError, "not_found"), (RuleViolation, "rule"), (ConflictError, "conflict")],
)
def test_each_exception_class_names_its_kind(cls: type[DomainError], kind: str) -> None:
    assert cls(ErrorCode.CONFLICT, "x").kind == kind
    assert issubclass(cls, DomainError)


def test_details_default_to_an_empty_dict_that_is_not_shared() -> None:
    first, second = (
        ConflictError(ErrorCode.SLOT_TAKEN, "a"),
        ConflictError(ErrorCode.SLOT_TAKEN, "b"),
    )
    assert first.details == {}
    first.details["x"] = 1
    assert second.details == {}
