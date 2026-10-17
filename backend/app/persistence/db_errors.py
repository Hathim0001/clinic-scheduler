"""Turning database errors into the errors a client should see.

Services check every rule before they write, so a constraint violation normally means a race that
slipped past the check (two requests for the same slot) or a validator that was missed. Either way
the client gets the same answer it would have got from the pre-check, not a 500.

Errors are recognised by SQLSTATE and constraint name, never by message text, which depends on the
server version and locale (plan ADR-12). One exception: a NUL byte in a text value is rejected by
the psycopg driver before it reaches the server, so it has no SQLSTATE and is matched by class.
"""

from __future__ import annotations

from sqlalchemy.exc import DataError, DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.domain.errors import (
    ConflictError,
    DomainError,
    ErrorCode,
    NotFoundError,
    RuleViolation,
)

# Deadlock detected and serialization failure: the transaction was rolled back and can be re-run.
RETRYABLE_SQLSTATES = frozenset({"40P01", "40001"})

_OVERLAP_CONSTRAINTS = {
    "no_doctor_overlap": (
        ErrorCode.SLOT_TAKEN,
        "The doctor already has an appointment in that slot.",
    ),
    "no_patient_overlap": (
        ErrorCode.PATIENT_OVERLAP,
        "The patient already has an appointment that overlaps that time.",
    ),
}
_WINDOW_OVERLAP_CONSTRAINTS = frozenset(
    {"weekly_windows_no_overlap", "override_windows_no_overlap"}
)


def sqlstate(exc: BaseException) -> str | None:
    """The five-character SQLSTATE of a database error, or None when it has none."""
    return getattr(getattr(exc, "orig", exc), "sqlstate", None)


def constraint_name(exc: BaseException) -> str | None:
    """The name of the constraint a database error refers to, when the server reports one."""
    diag = getattr(getattr(exc, "orig", exc), "diag", None)
    return getattr(diag, "constraint_name", None)


def is_retryable(exc: BaseException) -> bool:
    return sqlstate(exc) in RETRYABLE_SQLSTATES


def is_unavailable(exc: BaseException) -> bool:
    """True when the database was busy or unreachable rather than the request being wrong.

    Covers lock and statement timeouts, a killed or lost connection, a deadlock that survived its
    retry, and pool exhaustion. The API answers all of these with 503.
    """
    return isinstance(exc, OperationalError | PoolTimeoutError)


def translate_db_error(exc: DBAPIError) -> DomainError | None:
    """The domain error for a constraint or data error, or None when the error is not recognised."""
    state = sqlstate(exc)
    name = constraint_name(exc)

    if state == "23P01":  # exclusion_violation
        if name in _OVERLAP_CONSTRAINTS:
            code, message = _OVERLAP_CONSTRAINTS[name]
            return ConflictError(code, message)
        if name in _WINDOW_OVERLAP_CONSTRAINTS:
            return RuleViolation(ErrorCode.WINDOW_OVERLAP, "Availability windows must not overlap.")
        return ConflictError(ErrorCode.CONFLICT, "The change conflicts with existing data.")
    if state == "23505":  # unique_violation
        if name == "patients_phone_key":
            return ConflictError(
                ErrorCode.PHONE_TAKEN, "A patient with that phone number already exists."
            )
        return ConflictError(ErrorCode.CONFLICT, "The change conflicts with existing data.")
    if state == "23503":  # foreign_key_violation
        return NotFoundError(ErrorCode.REFERENCE_NOT_FOUND, "A referenced record does not exist.")
    if state == "23514" or isinstance(exc, DataError):  # check_violation, or any data exception
        return RuleViolation(ErrorCode.VALIDATION_ERROR, "A value was rejected by the database.")
    return None
