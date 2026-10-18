"""run_in_transaction and the services' error translation, including a real deadlock."""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ConflictError, ErrorCode
from app.persistence.db import run_in_transaction
from app.persistence.db_errors import is_unavailable
from app.persistence.models import Doctor
from app.services.support import run
from tests.factories import add_doctor
from tests.helpers import burst, db_error

pytestmark = pytest.mark.integration


def doctor_names(factory: sessionmaker[Session]) -> list[str]:
    with factory() as session:
        return list(session.scalars(select(Doctor.name).order_by(Doctor.id)))


def test_work_that_succeeds_is_committed(session_factory: sessionmaker[Session]) -> None:
    result = run_in_transaction(session_factory, lambda s: add_doctor(s, name="Dr. Kept").id)
    assert result == 1
    assert doctor_names(session_factory) == ["Dr. Kept"]


def test_work_that_raises_is_rolled_back(session_factory: sessionmaker[Session]) -> None:
    def work(session: Session) -> None:
        add_doctor(session, name="Dr. Lost")
        raise ValueError("changed my mind")

    with pytest.raises(ValueError, match="changed my mind"):
        run_in_transaction(session_factory, work)
    assert doctor_names(session_factory) == []


def test_a_deadlock_error_is_retried_once_and_the_second_run_wins(
    session_factory: sessionmaker[Session],
) -> None:
    calls = []

    def work(session: Session) -> str:
        calls.append(1)
        if len(calls) == 1:
            raise db_error("40P01", cls=OperationalError)
        add_doctor(session, name="Dr. Retried")
        return "done"

    assert run_in_transaction(session_factory, work) == "done"
    assert len(calls) == 2
    assert doctor_names(session_factory) == ["Dr. Retried"]  # the first attempt left nothing


def test_a_second_deadlock_is_given_up_on(session_factory: sessionmaker[Session]) -> None:
    calls = []

    def work(session: Session) -> None:
        calls.append(1)
        raise db_error("40P01", cls=OperationalError)

    with pytest.raises(OperationalError) as raised:
        run_in_transaction(session_factory, work)
    assert len(calls) == 2  # one retry, not an endless loop
    assert is_unavailable(raised.value)  # the API turns this into a 503


@pytest.mark.parametrize("state", ["23505", "55P03", "57014", None])
def test_other_database_errors_are_not_retried(
    session_factory: sessionmaker[Session], state: str | None
) -> None:
    calls = []

    def work(session: Session) -> None:
        calls.append(1)
        raise db_error(state, cls=OperationalError)

    with pytest.raises(DBAPIError):
        run_in_transaction(session_factory, work)
    assert len(calls) == 1


def test_a_real_deadlock_is_detected_retried_and_both_sides_finish(
    session_factory: sessionmaker[Session],
) -> None:
    """Two transactions take two doctor rows in opposite order, so PostgreSQL aborts one of them.

    The helper reruns the aborted one and both complete. (The app avoids this by always locking
    doctors in ascending id order; this proves the safety net behind that rule.)
    """
    with session_factory() as session, session.begin():
        first, second = add_doctor(session, name="A").id, add_doctor(session, name="B").id
    meeting = threading.Barrier(2)
    attempts: Counter[int] = Counter()

    def lock(session: Session, doctor_id: int) -> None:
        session.execute(text("SELECT id FROM doctors WHERE id = :id FOR UPDATE"), {"id": doctor_id})

    def crossing(own: int, other: int) -> Callable[[], str]:
        def work(session: Session) -> str:
            attempts[own] += 1
            lock(session, own)
            if attempts[own] == 1:
                meeting.wait(timeout=10)  # both now hold their own row; each wants the other's
            lock(session, other)
            return "done"

        return lambda: run_in_transaction(session_factory, work)

    results = burst([crossing(first, second), crossing(second, first)])
    assert results == ["done", "done"]
    assert sum(attempts.values()) == 3  # two first runs and one rerun


def test_a_constraint_error_a_client_caused_becomes_a_domain_error(
    session_factory: sessionmaker[Session],
) -> None:
    def work(session: Session) -> None:
        raise db_error("23P01", "no_doctor_overlap")

    with pytest.raises(ConflictError) as raised:
        run(session_factory, work)
    assert raised.value.code is ErrorCode.SLOT_TAKEN
    assert isinstance(raised.value.__cause__, DBAPIError)  # the original stays attached


def test_an_error_the_client_did_not_cause_is_left_for_the_api(
    session_factory: sessionmaker[Session],
) -> None:
    def work(session: Session) -> None:
        raise db_error("57014", cls=OperationalError)  # statement timeout

    with pytest.raises(OperationalError):
        run(session_factory, work)
