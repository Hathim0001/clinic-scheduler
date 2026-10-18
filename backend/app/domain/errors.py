"""The error catalogue and the domain exception types.

Every response the API can give is identified by one ErrorCode. The domain raises only the codes
in the "rule", "conflict" and "not found" groups (plus VALIDATION_ERROR, which it shares with
the HTTP edge); the edge adds the other request codes and the infrastructure codes.

A DomainError carries its code, a human sentence and a details dict, and its class says what
kind of failure it is so the API can pick the HTTP status (rule 422, conflict 409, not found 404).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar


class ErrorCode(StrEnum):
    # Request level: raised by the HTTP edge. VALIDATION_ERROR is also raised for malformed
    # windows and as the safety net for a database CHECK or data error.
    MALFORMED_JSON = "MALFORMED_JSON"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_TEST_CLOCK = "INVALID_TEST_CLOCK"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    # Something asked for does not exist.
    DOCTOR_NOT_FOUND = "DOCTOR_NOT_FOUND"
    PATIENT_NOT_FOUND = "PATIENT_NOT_FOUND"
    APPOINTMENT_NOT_FOUND = "APPOINTMENT_NOT_FOUND"
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
    WAITLIST_ENTRY_NOT_FOUND = "WAITLIST_ENTRY_NOT_FOUND"
    # The request itself breaks a business rule (422).
    BOOKING_IN_PAST = "BOOKING_IN_PAST"
    BOOKING_TOO_FAR = "BOOKING_TOO_FAR"
    OFF_GRID = "OFF_GRID"
    OUTSIDE_AVAILABILITY = "OUTSIDE_AVAILABILITY"
    DEPOSIT_REQUIRED = "DEPOSIT_REQUIRED"
    RESCHEDULE_NO_CHANGE = "RESCHEDULE_NO_CHANGE"
    WINDOW_OVERLAP = "WINDOW_OVERLAP"
    WINDOW_OFF_GRID = "WINDOW_OFF_GRID"
    # The request conflicts with the current state (409).
    DAILY_CAP_REACHED = "DAILY_CAP_REACHED"
    SLOT_TAKEN = "SLOT_TAKEN"
    PATIENT_OVERLAP = "PATIENT_OVERLAP"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    APPOINTMENT_ALREADY_STARTED = "APPOINTMENT_ALREADY_STARTED"
    TOO_EARLY_TO_MARK = "TOO_EARLY_TO_MARK"
    AVAILABILITY_CONFLICTS = "AVAILABILITY_CONFLICTS"
    PHONE_TAKEN = "PHONE_TAKEN"
    PATIENT_HAS_UPCOMING = "PATIENT_HAS_UPCOMING"
    PATIENT_ERASED = "PATIENT_ERASED"
    SLOT_LENGTH_LOCKED = "SLOT_LENGTH_LOCKED"
    DOCTOR_HAS_APPOINTMENTS = "DOCTOR_HAS_APPOINTMENTS"
    ALREADY_WAITING = "ALREADY_WAITING"
    OFFER_EXPIRED = "OFFER_EXPIRED"
    DOCTOR_NOT_ACCEPTING = "DOCTOR_NOT_ACCEPTING"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    ALREADY_CHECKED_IN = "ALREADY_CHECKED_IN"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    INVALID_CORRECTION = "INVALID_CORRECTION"
    LATE_RESCHEDULE_NEEDS_CONFIRMATION = "LATE_RESCHEDULE_NEEDS_CONFIRMATION"
    CONFLICT = "CONFLICT"
    # Infrastructure.
    UNAUTHENTICATED = "UNAUTHENTICATED"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_NOT_FOUND_CODES = frozenset(
    {
        ErrorCode.DOCTOR_NOT_FOUND,
        ErrorCode.PATIENT_NOT_FOUND,
        ErrorCode.APPOINTMENT_NOT_FOUND,
        ErrorCode.REFERENCE_NOT_FOUND,
        ErrorCode.WAITLIST_ENTRY_NOT_FOUND,
    }
)
_RULE_CODES = frozenset(
    {
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.BOOKING_IN_PAST,
        ErrorCode.BOOKING_TOO_FAR,
        ErrorCode.OFF_GRID,
        ErrorCode.OUTSIDE_AVAILABILITY,
        ErrorCode.DEPOSIT_REQUIRED,
        ErrorCode.RESCHEDULE_NO_CHANGE,
        ErrorCode.WINDOW_OVERLAP,
        ErrorCode.WINDOW_OFF_GRID,
    }
)
_CONFLICT_CODES = frozenset(
    {
        ErrorCode.DAILY_CAP_REACHED,
        ErrorCode.SLOT_TAKEN,
        ErrorCode.PATIENT_OVERLAP,
        ErrorCode.INVALID_TRANSITION,
        ErrorCode.APPOINTMENT_ALREADY_STARTED,
        ErrorCode.TOO_EARLY_TO_MARK,
        ErrorCode.AVAILABILITY_CONFLICTS,
        ErrorCode.PHONE_TAKEN,
        ErrorCode.PATIENT_HAS_UPCOMING,
        ErrorCode.PATIENT_ERASED,
        ErrorCode.SLOT_LENGTH_LOCKED,
        ErrorCode.DOCTOR_HAS_APPOINTMENTS,
        ErrorCode.ALREADY_WAITING,
        ErrorCode.OFFER_EXPIRED,
        ErrorCode.DOCTOR_NOT_ACCEPTING,
        ErrorCode.POSSIBLE_DUPLICATE,
        ErrorCode.ALREADY_CHECKED_IN,
        ErrorCode.IDEMPOTENCY_KEY_REUSED,
        ErrorCode.INVALID_CORRECTION,
        ErrorCode.LATE_RESCHEDULE_NEEDS_CONFIRMATION,
        ErrorCode.CONFLICT,
    }
)


class DomainError(Exception):
    """Base class. `kind` tells the API which HTTP status family applies."""

    kind: ClassVar[str] = "error"

    def __init__(self, code: ErrorCode, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details


class NotFoundError(DomainError):
    kind = "not_found"


class RuleViolation(DomainError):
    kind = "rule"


class ConflictError(DomainError):
    kind = "conflict"


def domain_error(code: ErrorCode, message: str, **details: Any) -> DomainError:
    """Build the right DomainError subclass for a code (so callers never pick the class by hand)."""
    if code in _NOT_FOUND_CODES:
        return NotFoundError(code, message, **details)
    if code in _RULE_CODES:
        return RuleViolation(code, message, **details)
    if code in _CONFLICT_CODES:
        return ConflictError(code, message, **details)
    raise ValueError(f"{code} is not a domain error code")
