"""The Twilio gateway (against a local stand-in) and the choice of gateway from settings."""

from __future__ import annotations

import base64
import threading
import urllib.error
import urllib.parse
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from app.services import gateways
from app.services.gateways import TwilioProvider, gateway_name, provider_from_settings
from app.services.notification_service import WebhookProvider
from app.services.views import BookCommand
from tests.api.conftest import make_settings
from tests.integration.conftest import NOW, Clinic, at

pytestmark = pytest.mark.integration

SID = "AC0123456789abcdef"
TOKEN = "secret-auth-token"


class FakeTwilio(BaseHTTPRequestHandler):
    received: ClassVar[list[dict[str, Any]]] = []
    status: ClassVar[int] = 201

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        FakeTwilio.received.append(
            {
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "type": self.headers.get("Content-Type"),
                "form": {k: v[0] for k, v in form.items()},
            }
        )
        self.send_response(FakeTwilio.status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args: object) -> None:  # keep the test output quiet
        return


@pytest.fixture
def twilio(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    FakeTwilio.received = []
    FakeTwilio.status = 201
    server = HTTPServer(("127.0.0.1", 0), FakeTwilio)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(gateways, "TWILIO_URL", base + "/2010-04-01/Accounts/{sid}/Messages.json")
    yield base
    server.shutdown()


def test_an_sms_is_posted_to_twilio_with_basic_auth_and_a_form_body(twilio: str) -> None:
    TwilioProvider(SID, TOKEN, "+15005550006").send(
        "+919000000001", "Hello there", "REMINDER_FIRST"
    )
    (call,) = FakeTwilio.received
    assert call["path"] == f"/2010-04-01/Accounts/{SID}/Messages.json"
    assert call["auth"] == "Basic " + base64.b64encode(f"{SID}:{TOKEN}".encode()).decode()
    assert call["type"] == "application/x-www-form-urlencoded"
    assert call["form"] == {"To": "+919000000001", "From": "+15005550006", "Body": "Hello there"}


def test_a_whatsapp_message_prefixes_both_numbers(twilio: str) -> None:
    TwilioProvider(SID, TOKEN, "+14155238886", "whatsapp").send("+919000000001", "Hi", "x")
    (call,) = FakeTwilio.received
    assert call["form"]["To"] == "whatsapp:+919000000001"
    assert call["form"]["From"] == "whatsapp:+14155238886"


def test_a_twilio_error_raises_so_the_message_is_retried(twilio: str) -> None:
    FakeTwilio.status = 401
    with pytest.raises(urllib.error.HTTPError):
        TwilioProvider(SID, TOKEN, "+15005550006").send("+919000000001", "x", "x")


def test_a_failing_gateway_leaves_the_message_pending_then_failed(
    twilio: str, clinic: Clinic
) -> None:
    from app.services.notification_service import MAX_ATTEMPTS, NotificationService

    FakeTwilio.status = 500
    clinic.patients.record_consent(clinic.asha, NOW)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    service = NotificationService(clinic.factory)
    gateway = TwilioProvider(SID, TOKEN, "+15005550006")
    for _ in range(MAX_ATTEMPTS):
        assert service.dispatch(gateway, NOW) == 0
    (message,) = service.list(None, 10, 0).items
    assert (message.status, message.attempts) == ("FAILED", MAX_ATTEMPTS)


# --------------------------------------------------------------------- choosing the gateway


def settings(**values: Any):  # type: ignore[no-untyped-def]
    return make_settings("postgresql+psycopg://x:y@localhost/z", **values)


def test_no_gateway_is_configured_by_default() -> None:
    assert provider_from_settings(settings()) is None
    assert gateway_name(settings()) is None


def test_the_webhook_is_used_when_only_it_is_set() -> None:
    configured = settings(notify_webhook_url="https://relay.example/send")
    assert isinstance(provider_from_settings(configured), WebhookProvider)
    assert gateway_name(configured) == "webhook"


def test_twilio_is_preferred_when_both_are_set() -> None:
    configured = settings(
        notify_webhook_url="https://relay.example/send",
        twilio_account_sid=SID,
        twilio_auth_token=TOKEN,
        twilio_from="+15005550006",
    )
    assert isinstance(provider_from_settings(configured), TwilioProvider)
    assert gateway_name(configured) == "twilio"


def test_a_partial_twilio_configuration_is_refused_at_startup() -> None:
    with pytest.raises(ValidationError, match="must all be set together"):
        settings(twilio_account_sid=SID)
    with pytest.raises(ValidationError, match="must all be set together"):
        settings(twilio_account_sid=SID, twilio_auth_token=TOKEN)


def test_blank_twilio_variables_mean_off() -> None:
    assert (
        gateway_name(settings(twilio_account_sid="", twilio_auth_token="", twilio_from="")) is None
    )


def test_the_channel_must_be_sms_or_whatsapp() -> None:
    with pytest.raises(ValidationError):
        settings(notify_channel="telegram")
