"""Mapping database errors to what a client should see, using stand-ins for the driver's errors.

The real driver errors are exercised against PostgreSQL in the integration tests; here the point
is the decision table: which SQLSTATE and constraint name give which code.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import (
    DataError,
    DBAPIError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
)
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.domain.errors import (
    ConflictError,
    DomainError,
    ErrorCode,
    NotFoundError,
    RuleViolation,
)
from app.persistence.db_errors import (
    constraint_name,
    is_retryable,
    is_unavailable,
    sqlstate,
    translate_db_error,
)

pytestmark = pytest.mark.unit

SECRET = "+919876543210"  # a value that must never be echoed to a client


class FakeDiag:
    def __init__(self, constraint: str | None) -> None:
        self.constraint_name = constraint


class FakeDriverError(Exception):
    """What psycopg raises: a `sqlstate` and a `diag.constraint_name`."""

    def __init__(self, state: str | None, constraint: str | None = None) -> None:
        super().__init__(f"duplicate key value violates unique constraint ({SECRET})")
        self.sqlstate = state
        self.diag = FakeDiag(constraint)


def wrap(
    state: str | None, constraint: str | None = None, cls: type[DBAPIError] = IntegrityError
) -> DBAPIError:
    return cls("INSERT INTO patients ...", {"phone": SECRET}, FakeDriverError(state, constraint))


@pytest.mark.parametrize(
    ("state", "constraint", "cls", "code"),
    [
        ("23P01", "no_doctor_overlap", ConflictError, ErrorCode.SLOT_TAKEN),
        ("23P01", "no_patient_overlap", ConflictError, ErrorCode.PATIENT_OVERLAP),
        ("23P01", "weekly_windows_no_overlap", RuleViolation, ErrorCode.WINDOW_OVERLAP),
        ("23P01", "override_windows_no_overlap", RuleViolation, ErrorCode.WINDOW_OVERLAP),
        ("23P01", "some_future_constraint", ConflictError, ErrorCode.CONFLICT),
        ("23505", "patients_phone_key", ConflictError, ErrorCode.PHONE_TAKEN),
        ("23505", "some_other_unique", ConflictError, ErrorCode.CONFLICT),
        ("23505", None, ConflictError, ErrorCode.CONFLICT),
        ("23503", "appointments_doctor_id_fkey", NotFoundError, ErrorCode.REFERENCE_NOT_FOUND),
        ("23514", "doctors_slot_length_ok", RuleViolation, ErrorCode.VALIDATION_ERROR),
    ],
)
def test_constraint_violations_map_to_the_code_the_precheck_would_have_given(
    state: str, constraint: str | None, cls: type[DomainError], code: ErrorCode
) -> None:
    error = translate_db_error(wrap(state, constraint))
    assert type(error) is cls
    assert error is not None
    assert error.code is code


@pytest.mark.parametrize("state", [None, "22001", "22P02", "22003", "22021"])
def test_any_data_error_is_a_validation_error(state: str | None) -> None:
    """A NUL byte has no SQLSTATE at all (the driver refuses it), so the class decides."""
    error = translate_db_error(wrap(state, cls=DataError))
    assert isinstance(error, RuleViolation)
    assert error.code is ErrorCode.VALIDATION_ERROR


@pytest.mark.parametrize(
    "exc",
    [
        wrap("42P01", cls=ProgrammingError),  # undefined table: our bug, not the client's
        wrap("57014", cls=OperationalError),  # statement timeout
        wrap("40P01", cls=OperationalError),  # deadlock
        wrap(None, cls=OperationalError),  # connection lost
    ],
    ids=["programming error", "statement timeout", "deadlock", "no sqlstate"],
)
def test_other_errors_are_not_translated(exc: DBAPIError) -> None:
    assert translate_db_error(exc) is None


@pytest.mark.parametrize("state", ["23P01", "23505", "23503", "23514"])
def test_the_client_message_never_contains_sql_or_values(state: str) -> None:
    error = translate_db_error(wrap(state, "patients_phone_key"))
    assert error is not None
    text = error.message + repr(error.details)
    assert SECRET not in text
    assert "INSERT" not in text
    assert "violates" not in text


@pytest.mark.parametrize(
    ("state", "expected"),
    [("40P01", True), ("40001", True), ("23505", False), ("55P03", False), (None, False)],
)
def test_only_deadlocks_and_serialization_failures_are_retried(
    state: str | None, expected: bool
) -> None:
    assert is_retryable(wrap(state, cls=OperationalError)) is expected


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (wrap("55P03", cls=OperationalError), True),  # lock timeout
        (wrap("57014", cls=OperationalError), True),  # statement timeout
        (wrap("40P01", cls=OperationalError), True),  # a deadlock that survived its retry
        (wrap(None, cls=OperationalError), True),  # server gone
        (PoolTimeoutError("QueuePool limit reached"), True),
        (wrap("23505"), False),
        (ValueError("not a database error"), False),
    ],
)
def test_a_busy_or_unreachable_database_is_reported_as_unavailable(
    exc: BaseException, expected: bool
) -> None:
    assert is_unavailable(exc) is expected


def test_sqlstate_and_constraint_name_tolerate_exceptions_without_them() -> None:
    plain = ValueError("nothing here")
    assert sqlstate(plain) is None
    assert constraint_name(plain) is None
    assert sqlstate(wrap("23505", "patients_phone_key")) == "23505"
    assert constraint_name(wrap("23505", "patients_phone_key")) == "patients_phone_key"
    assert constraint_name(wrap("23505")) is None
