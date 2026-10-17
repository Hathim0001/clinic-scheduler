"""translate_db_error against real PostgreSQL errors, with the constraint names of the real schema.

The unit tests cover the decision table with stand-ins; these prove the driver really reports the
SQLSTATE and constraint name the table expects.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ConflictError, DomainError, ErrorCode, NotFoundError, RuleViolation
from app.persistence.db_errors import is_retryable, is_unavailable, translate_db_error
from tests.factories import add_appointment, add_doctor, add_patient, add_weekly
from tests.helpers import ist

pytestmark = pytest.mark.integration

START = ist(2026, 11, 2, 11, 0)


def attempt(factory: sessionmaker[Session], work: Callable[[Session], object]) -> None:
    with factory() as session, session.begin():
        work(session)


def translated(factory: sessionmaker[Session], work: Callable[[Session], object]) -> DomainError:
    with pytest.raises(DBAPIError) as raised:
        attempt(factory, work)
    error = translate_db_error(raised.value)
    assert error is not None, f"not translated: {raised.value}"
    return error


@pytest.fixture
def booked(session_factory: sessionmaker[Session]) -> tuple[int, int, int]:
    """A 30-minute doctor with one booking for patient 1; returns (doctor, patient 1, patient 2)."""
    with session_factory() as session, session.begin():
        doctor = add_doctor(session, slot=30)
        first, second = add_patient(session, 1), add_patient(session, 2)
        add_appointment(session, doctor.id, first.id, START)
        return doctor.id, first.id, second.id


def test_a_second_booking_of_the_same_slot_is_slot_taken(
    session_factory: sessionmaker[Session], booked: tuple[int, int, int]
) -> None:
    doctor, _, second = booked
    error = translated(session_factory, lambda s: add_appointment(s, doctor, second, START))
    assert isinstance(error, ConflictError)
    assert error.code is ErrorCode.SLOT_TAKEN


def test_a_patient_in_two_places_at_once_is_patient_overlap(
    session_factory: sessionmaker[Session], booked: tuple[int, int, int]
) -> None:
    _, first, _ = booked

    def double_book(session: Session) -> None:
        other = add_doctor(session, name="Dr. Other", slot=30)
        add_appointment(session, other.id, first, START)

    error = translated(session_factory, double_book)
    assert isinstance(error, ConflictError)
    assert error.code is ErrorCode.PATIENT_OVERLAP


def test_a_duplicate_phone_number_is_phone_taken(
    session_factory: sessionmaker[Session], booked: tuple[int, int, int]
) -> None:
    error = translated(session_factory, lambda s: add_patient(s, 1, name="Someone Else"))
    assert isinstance(error, ConflictError)
    assert error.code is ErrorCode.PHONE_TAKEN


def test_an_unknown_doctor_is_a_missing_reference(
    session_factory: sessionmaker[Session], booked: tuple[int, int, int]
) -> None:
    _, _, second = booked  # the patient with no appointment, so only the foreign key can fail
    error = translated(session_factory, lambda s: add_appointment(s, 999_999, second, START))
    assert isinstance(error, NotFoundError)
    assert error.code is ErrorCode.REFERENCE_NOT_FOUND


def test_a_check_violation_is_a_validation_error(session_factory: sessionmaker[Session]) -> None:
    error = translated(session_factory, lambda s: add_doctor(s, slot=20))
    assert isinstance(error, RuleViolation)
    assert error.code is ErrorCode.VALIDATION_ERROR


def test_a_nul_byte_is_a_validation_error(session_factory: sessionmaker[Session]) -> None:
    error = translated(session_factory, lambda s: add_patient(s, 3, name="Ravi" + chr(0) + "Kumar"))
    assert isinstance(error, RuleViolation)
    assert error.code is ErrorCode.VALIDATION_ERROR


def test_overlapping_weekly_windows_are_a_window_overlap(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session, session.begin():
        doctor_id = add_doctor(session).id

    def overlapping(session: Session) -> None:
        add_weekly(session, doctor_id, 0, 540, 780)
        add_weekly(session, doctor_id, 0, 720, 900)

    error = translated(session_factory, overlapping)
    assert isinstance(error, RuleViolation)
    assert error.code is ErrorCode.WINDOW_OVERLAP


def test_a_lock_timeout_means_unavailable_not_a_client_error(
    session_factory: sessionmaker[Session], booked: tuple[int, int, int]
) -> None:
    doctor, _, _ = booked

    def lock_with_timeout(session: Session) -> None:
        session.execute(text("SET LOCAL lock_timeout = '150ms'"))
        session.execute(text("SELECT id FROM doctors WHERE id = :id FOR UPDATE"), {"id": doctor})

    with session_factory() as holder, holder.begin():
        holder.execute(text("SELECT id FROM doctors WHERE id = :id FOR UPDATE"), {"id": doctor})
        with pytest.raises(DBAPIError) as raised:
            attempt(session_factory, lock_with_timeout)

    assert is_unavailable(raised.value)
    assert not is_retryable(raised.value)  # waiting longer is not a deadlock; the API answers 503
    assert translate_db_error(raised.value) is None
