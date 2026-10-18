"""Hardening: reads that do not write, idempotency keys that expire, an audit trail the database
protects, an actor on every audit row, and the background sweep."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.actor import current_actor
from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import CancelledBy
from app.domain.timeutil import IST
from app.main import create_app
from app.services.views import BookCommand
from tests.api.conftest import make_settings
from tests.factories import add_appointment
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


# -------------------------------------------------------------------------------- reads are reads


def test_reading_a_lapsed_offer_changes_nothing_in_the_database(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        booked = add_appointment(session, clinic.rao, clinic.ravi, at(10)).id
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    later = NOW + timedelta(hours=2)

    assert clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, later) == []
    assert clinic.waitlist.for_patient(clinic.asha, later) == []

    with clinic.factory() as session:
        status = session.execute(
            text("SELECT status FROM waitlist_entries WHERE id = :id"), {"id": entry.id}
        ).scalar_one()
    assert (
        status == "OFFERED"
    )  # still as the last write left it: only the sweep or a change moves it


def test_a_live_offer_is_shown_up_to_its_last_second(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        booked = add_appointment(session, clinic.rao, clinic.ravi, at(10)).id
    clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    expiry = NOW + timedelta(minutes=30)
    assert len(clinic.waitlist.for_patient(clinic.asha, expiry)) == 1
    assert clinic.waitlist.for_patient(clinic.asha, expiry + timedelta(seconds=1)) == []


# ------------------------------------------------------------------------- idempotency expiry


def command(clinic: Clinic) -> BookCommand:
    return BookCommand(clinic.rao, clinic.asha, at(10), "Check-up")


def keys(clinic: Clinic) -> list[str]:
    with clinic.factory() as session:
        return list(
            session.execute(text("SELECT key FROM idempotency_keys ORDER BY key")).scalars()
        )


def test_an_old_idempotency_key_is_forgotten_and_a_fresh_one_is_kept(clinic: Clinic) -> None:
    clinic.booking.book_idempotent(command(clinic), "old", NOW)
    clinic.booking.book_idempotent(BookCommand(clinic.rao, clinic.meena, at(11), "x"), "fresh", NOW)
    with clinic.factory() as session, session.begin():
        session.execute(
            text("UPDATE idempotency_keys SET created_at = now() - interval '25 h' WHERE key = :k"),
            {"k": "old"},
        )
    # any later keyed booking sweeps the old one away
    clinic.booking.book_idempotent(BookCommand(clinic.rao, clinic.ravi, at(12), "x"), "third", NOW)
    assert keys(clinic) == ["fresh", "third"]


def test_a_forgotten_key_no_longer_replays(clinic: Clinic) -> None:
    first, _ = clinic.booking.book_idempotent(command(clinic), "k", NOW)
    with clinic.factory() as session, session.begin():
        session.execute(text("UPDATE idempotency_keys SET created_at = now() - interval '2 days'"))
    with pytest.raises(ConflictError) as raised:  # a real second attempt now meets the real slot
        clinic.booking.book_idempotent(command(clinic), "k", NOW)
    assert raised.value.code is ErrorCode.SLOT_TAKEN
    assert raised.value.details["appointment_id"] == first.id


def test_a_test_clock_cannot_expire_real_keys(clinic: Clinic) -> None:
    clinic.booking.book_idempotent(command(clinic), "k", NOW)
    far_future = NOW + timedelta(days=30)  # the key's age is the database's, not the request's
    _, replayed = clinic.booking.book_idempotent(command(clinic), "k", far_future)
    assert replayed


# ---------------------------------------------------------------------------- the audit trail


def execute(clinic: Clinic, statement: str) -> None:
    with clinic.factory() as session:
        session.execute(text(statement))


def test_the_database_refuses_to_change_or_delete_an_audit_row(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    for statement in (
        "UPDATE appointment_events SET kind = 'X'",
        "DELETE FROM appointment_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            execute(clinic, statement)
    assert [e.kind for e in clinic.records.history(booked.id)] == ["BOOKED"]


def test_a_new_audit_row_is_still_allowed(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    clinic.booking.cancel(booked.id, CancelledBy.PATIENT, NOW)
    assert [e.kind for e in clinic.records.history(booked.id)] == ["BOOKED", "CANCELLED"]


def test_every_audit_row_names_who_did_it(clinic: Clinic) -> None:
    assert current_actor.get() == "system"  # outside a request
    booked = clinic.booking.book(command(clinic), NOW)
    token = current_actor.set("Meera")
    try:
        clinic.booking.cancel(booked.id, CancelledBy.CLINIC, NOW)
    finally:
        current_actor.reset(token)
    assert [(e.kind, e.actor) for e in clinic.records.history(booked.id)] == [
        ("BOOKED", "system"),
        ("CANCELLED", "Meera"),
    ]


# -------------------------------------------------------------------------------- the sweep


def next_weekday_ten(days_ahead: int) -> datetime:
    """10:00 India time on the first Monday to Friday at least `days_ahead` days from today."""
    day = datetime.now(IST).date() + timedelta(days=days_ahead)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST)


def test_the_server_passes_a_lapsed_offer_on_by_itself(clinic: Clinic, database_url: str) -> None:
    """With the real clock: an offer that ran out a minute ago is given to the next patient
    within a couple of seconds, with nobody asking."""
    slot = next_weekday_ten(3)
    day: date = slot.date()
    now = datetime.now(UTC)
    with clinic.factory() as session, session.begin():
        booked = add_appointment(session, clinic.rao, clinic.ravi, slot).id
    first = clinic.waitlist.join(clinic.rao, clinic.asha, day, now)
    second = clinic.waitlist.join(clinic.rao, clinic.meena, day, now)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, now)  # offered to the first
    with clinic.factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE waitlist_entries SET offer_expires_at = now() - interval '1 m' WHERE id=:i"
            ),
            {"i": first.id},
        )

    app = create_app(make_settings(database_url, offer_sweep_interval_s=1))
    with TestClient(app):
        deadline = time.monotonic() + 10
        status = ""
        while time.monotonic() < deadline:
            status = clinic.waitlist.for_patient(clinic.meena, datetime.now(UTC))[0].status
            if status == "OFFERED":
                break
            time.sleep(0.3)
    assert status == "OFFERED"
    assert clinic.waitlist.for_patient(clinic.asha, datetime.now(UTC)) == []
    assert second.id != first.id


def test_a_sweep_that_fails_does_not_stop_the_next_round(
    clinic: Clinic, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def flaky(self: object, now: datetime) -> int:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the database blinked")
        return 0

    monkeypatch.setattr("app.services.waitlist_service.WaitlistService.sweep", flaky)
    app = create_app(make_settings(database_url, offer_sweep_interval_s=1))
    with TestClient(app):
        deadline = time.monotonic() + 10
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.2)
    assert len(calls) >= 2
