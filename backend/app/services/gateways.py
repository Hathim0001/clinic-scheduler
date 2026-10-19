"""Where messages to patients actually go: a Twilio account (SMS or WhatsApp), or any gateway or
relay that accepts a JSON POST. Both are plain standard-library HTTP, so there is nothing to
install, and both raise on any failure so the outbox retries the message.
"""

from __future__ import annotations

import base64
import urllib.parse
import urllib.request
from typing import Literal

from app.core.config import Settings
from app.services.notification_service import Provider, WebhookProvider

TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class TwilioProvider:
    """Sends through Twilio's Messages API: an SMS, or a WhatsApp message when `channel` is
    "whatsapp" (the numbers are then prefixed `whatsapp:` as Twilio requires). Any non-2xx answer
    or network error raises, so the message is retried and finally marked FAILED."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        sender: str,
        channel: str = "sms",
        timeout_s: float = 8.0,
    ) -> None:
        self._url = TWILIO_URL.format(sid=urllib.parse.quote(account_sid, safe=""))
        credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        self._auth = f"Basic {credentials}"
        self._sender, self._channel, self._timeout = sender, channel, timeout_s

    def _address(self, number: str) -> str:
        return f"whatsapp:{number}" if self._channel == "whatsapp" else number

    def send(self, to: str, body: str, kind: str) -> None:
        form = urllib.parse.urlencode(
            {"To": self._address(to), "From": self._address(self._sender), "Body": body}
        ).encode()
        request = urllib.request.Request(  # noqa: S310 - fixed https URL
            self._url,
            data=form,
            headers={
                "Authorization": self._auth,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout):  # noqa: S310
            pass


def provider_from_settings(settings: Settings) -> Provider | None:
    """The configured gateway, or None when nothing is set and reception sends by hand."""
    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from:
        return TwilioProvider(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            settings.twilio_from,
            settings.notify_channel,
        )
    if settings.notify_webhook_url:
        return WebhookProvider(settings.notify_webhook_url, settings.notify_webhook_token)
    return None


def gateway_name(settings: Settings) -> Literal["twilio", "webhook"] | None:
    """What the Messages page says is sending: "twilio", "webhook" or None."""
    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from:
        return "twilio"
    return "webhook" if settings.notify_webhook_url else None
