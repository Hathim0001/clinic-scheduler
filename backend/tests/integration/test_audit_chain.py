"""The audit trail is hash-chained by the database: a past event cannot change unnoticed."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.domain.model import CancelledBy
from app.persistence import repositories as repo
from app.services.views import BookCommand
from tests.integration.conftest import NOW, Clinic, at

pytestmark = pytest.mark.integration


def check(clinic: Clinic) -> tuple[int, list[int]]:
    with clinic.factory() as session:
        return repo.audit_chain_breaks(session)


def tamper(clinic: Clinic, sql: str, **params: int) -> None:
    """What someone with full database rights could do: stand the guard down and edit history."""
    with clinic.factory() as session, session.begin():
        session.execute(
            text("ALTER TABLE appointment_events DISABLE TRIGGER appointment_events_no_change")
        )
        session.execute(text(sql), params)
        session.execute(
            text("ALTER TABLE appointment_events ENABLE TRIGGER appointment_events_no_change")
        )


def make_history(clinic: Clinic) -> int:
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    clinic.booking.cancel(booked.id, CancelledBy.PATIENT, NOW)
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(11), "x"), NOW)
    return booked.id


def test_a_clean_history_verifies(clinic: Clinic) -> None:
    make_history(clinic)
    checked, broken = check(clinic)
    assert checked == 3  # booked, cancelled, and the second booking
    assert broken == []


def test_each_event_links_to_the_one_before_it_for_the_same_appointment(clinic: Clinic) -> None:
    appointment_id = make_history(clinic)
    with clinic.factory() as session:
        rows = session.execute(
            text(
                "SELECT prev_hash, row_hash FROM appointment_events "
                "WHERE appointment_id = :a ORDER BY id"
            ),
            {"a": appointment_id},
        ).all()
    assert rows[0][0] is None
    assert rows[1][0] == rows[0][1]
    assert len({r[1] for r in rows}) == len(rows)


def test_editing_a_past_event_is_refused_by_the_append_only_guard(clinic: Clinic) -> None:
    make_history(clinic)
    with pytest.raises(DBAPIError), clinic.factory() as session, session.begin():
        session.execute(text("UPDATE appointment_events SET kind = 'FORGED' WHERE id = 1"))


def test_an_edit_made_with_the_guard_off_is_detected(clinic: Clinic) -> None:
    make_history(clinic)
    tamper(clinic, "UPDATE appointment_events SET kind = 'FORGED' WHERE id = 2")
    _, broken = check(clinic)
    assert broken == [2]


def test_deleting_an_event_from_the_middle_is_detected(clinic: Clinic) -> None:
    appointment_id = make_history(clinic)
    tamper(
        clinic,
        "DELETE FROM appointment_events WHERE id = "
        "(SELECT min(id) FROM appointment_events WHERE appointment_id = :a)",
        a=appointment_id,
    )
    _, broken = check(clinic)
    assert broken  # the next event's link no longer matches


def test_events_written_after_an_edit_do_not_hide_it(clinic: Clinic) -> None:
    make_history(clinic)
    tamper(clinic, "UPDATE appointment_events SET actor = 'someone-else' WHERE id = 1")
    clinic.booking.book(BookCommand(clinic.rao, clinic.meena, at(12), "x"), NOW)
    _, broken = check(clinic)
    assert 1 in broken
