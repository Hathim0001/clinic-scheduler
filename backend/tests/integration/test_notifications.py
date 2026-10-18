"""Messages to patients: queued with the change, gated on consent, sent or left for staff."""

from __future__ import annotations

import json
import threading
import urllib.error
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from app.domain.errors import ConflictError, ErrorCode, NotFoundError
from app.domain.model import CancelledBy
from app.services.notification_service import (
    MAX_ATTEMPTS,
    NotificationService,
    WebhookProvider,
)
from app.services.views import BookCommand
from tests.factories import add_appointment
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


class Recorder:
    """A provider that records what it was asked to send."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, body: str, kind: str) -> None:
        self.sent.append((to, body, kind))


class Failing:
    def send(self, to: str, body: str, kind: str) -> None:
        raise urllib.error.URLError("gateway down")


def service(clinic: Clinic) -> NotificationService:
    return NotificationService(clinic.factory)


def consent(clinic: Clinic, patient: int) -> None:
    clinic.patients.record_consent(patient, NOW)


def all_messages(clinic: Clinic):  # type: ignore[no-untyped-def]
    return service(clinic).list(None, 100, 0).items


def test_a_booking_queues_a_confirmation_for_a_patient_who_consented(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "Fever"), NOW)
    (message,) = all_messages(clinic)
    assert (message.kind, message.status, message.appointment_id) == (
        "APPOINTMENT_BOOKED",
        "PENDING",
        booked.id,
    )
    assert "Dr. Rao" in message.body
    assert "02 Nov 2026, 10:00" in message.body
    assert "Fever" not in message.body  # the reason is never put in a message


def test_without_recorded_consent_the_message_is_skipped_and_says_so(clinic: Clinic) -> None:
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(10), "x"), NOW)
    (message,) = all_messages(clinic)
    assert message.status == "SKIPPED"
    assert message.last_error is not None
    assert "phone" in message.last_error


def test_a_clinic_cancellation_is_announced_but_a_patient_cancellation_is_not(
    clinic: Clinic,
) -> None:
    consent(clinic, clinic.asha)
    consent(clinic, clinic.ravi)
    mine = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    theirs = clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(11), "x"), NOW)
    clinic.booking.cancel(mine.id, CancelledBy.PATIENT, NOW)
    clinic.booking.cancel(theirs.id, CancelledBy.CLINIC, NOW)
    kinds = [m.kind for m in all_messages(clinic)]
    assert kinds.count("APPOINTMENT_CANCELLED_BY_CLINIC") == 1
    clinic_message = next(m for m in all_messages(clinic) if m.kind.endswith("BY_CLINIC"))
    assert "does not count against you" in clinic_message.body


def test_moving_an_appointment_sends_one_message_about_the_new_time(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(11), "x"), NOW)
    clinic.booking.reschedule(booked.id, at(12), None, None, NOW)
    kinds = [m.kind for m in reversed(all_messages(clinic))]
    assert kinds == ["APPOINTMENT_BOOKED", "APPOINTMENT_MOVED"]


def test_a_waitlist_offer_is_messaged_with_its_deadline(clinic: Clinic) -> None:
    consent(clinic, clinic.meena)
    with clinic.factory() as session, session.begin():
        held = add_appointment(session, clinic.rao, clinic.ravi, at(10)).id
    clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)
    clinic.booking.cancel(held, CancelledBy.PATIENT, NOW)
    offers = [m for m in all_messages(clinic) if m.kind == "WAITLIST_OFFER"]
    assert len(offers) == 1
    assert "held for you until" in offers[0].body
    assert offers[0].patient_id == clinic.meena


def test_a_change_that_is_rolled_back_leaves_no_message(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    with pytest.raises(ConflictError):
        clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(10), "x"), NOW)
    assert len(all_messages(clinic)) == 1  # only the booking that happened


def test_dispatch_sends_pending_messages_and_marks_them_sent(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    provider = Recorder()
    assert service(clinic).dispatch(provider, NOW) == 1
    assert provider.sent[0][0] == "+919000000001"
    (message,) = all_messages(clinic)
    assert (message.status, message.sent_via, message.sent_at) == ("SENT", "GATEWAY", NOW)
    assert service(clinic).dispatch(provider, NOW) == 0  # nothing is sent twice
    assert len(provider.sent) == 1


def test_a_skipped_message_is_never_sent_by_the_gateway(clinic: Clinic) -> None:
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(10), "x"), NOW)
    provider = Recorder()
    assert service(clinic).dispatch(provider, NOW) == 0
    assert provider.sent == []


def test_a_failing_gateway_is_retried_then_the_message_is_marked_failed(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert service(clinic).dispatch(Failing(), NOW) == 0
        (message,) = all_messages(clinic)
        assert message.attempts == attempt
    assert message.status == "FAILED"
    assert message.last_error == "URLError"
    assert service(clinic).dispatch(Recorder(), NOW) == 0  # a failed message is left alone


def test_reception_can_mark_a_message_sent_by_hand_once(clinic: Clinic) -> None:
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(10), "x"), NOW)
    (message,) = all_messages(clinic)
    done = service(clinic).mark_sent(message.id, NOW + timedelta(minutes=5))
    assert (done.status, done.sent_via) == ("SENT", "MANUAL")
    with pytest.raises(ConflictError):
        service(clinic).mark_sent(message.id, NOW)
    with pytest.raises(NotFoundError) as raised:
        service(clinic).mark_sent(999, NOW)
    assert raised.value.code is ErrorCode.NOTIFICATION_NOT_FOUND


def test_the_pending_count_includes_messages_reception_must_phone(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(11), "x"), NOW)
    assert service(clinic).pending_count() == 2
    service(clinic).dispatch(Recorder(), NOW)
    assert service(clinic).pending_count() == 1  # the skipped one still needs a phone call


def test_listing_filters_by_status_and_pages(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    for hour in (9, 10, 11):
        clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(hour), "x"), NOW)
    page = service(clinic).list("PENDING", 2, 1)
    assert (page.total, len(page.items)) == (3, 2)
    assert service(clinic).list("SENT", 10, 0).total == 0


def test_erasing_a_patient_removes_their_number_and_the_text_from_the_outbox(
    clinic: Clinic,
) -> None:
    consent(clinic, clinic.asha)
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    clinic.booking.cancel(booked.id, CancelledBy.CLINIC, NOW)
    clinic.patients.erase(clinic.asha, NOW)
    for message in all_messages(clinic):
        assert message.body == "[erased]"
        assert "9000000001" not in message.to_phone


# --------------------------------------------------------------------------- the webhook provider


class _Handler(BaseHTTPRequestHandler):
    received: ClassVar[list[dict[str, object]]] = []
    auth: ClassVar[list[str | None]] = []
    status = 200

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        type(self).received.append(json.loads(self.rfile.read(length)))
        type(self).auth.append(self.headers.get("Authorization"))
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *args: object) -> None:  # keep test output quiet
        pass


@pytest.fixture
def gateway():  # type: ignore[no-untyped-def]
    _Handler.received, _Handler.auth, _Handler.status = [], [], 200
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/send"
    server.shutdown()
    thread.join(timeout=5)


def test_the_webhook_provider_posts_json_with_the_bearer_token(gateway: str) -> None:
    WebhookProvider(gateway, "secret-token").send("+919000000001", "Hello", "APPOINTMENT_BOOKED")
    assert _Handler.received == [
        {"to": "+919000000001", "body": "Hello", "kind": "APPOINTMENT_BOOKED"}
    ]
    assert _Handler.auth == ["Bearer secret-token"]


def test_the_webhook_provider_treats_a_server_error_as_a_failure(gateway: str) -> None:
    _Handler.status = 500
    with pytest.raises(urllib.error.HTTPError):
        WebhookProvider(gateway).send("+919000000001", "Hello", "k")


def test_an_unreachable_gateway_leaves_the_message_pending_for_retry(clinic: Clinic) -> None:
    consent(clinic, clinic.asha)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    dead = WebhookProvider("http://127.0.0.1:9/send", timeout_s=1)
    assert service(clinic).dispatch(dead, NOW) == 0
    (message,) = all_messages(clinic)
    assert (message.status, message.attempts) == ("PENDING", 1)
