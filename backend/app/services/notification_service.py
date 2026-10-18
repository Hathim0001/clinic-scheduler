"""Messages to patients: a booking confirmation, a clinic cancellation or move, a waitlist offer.

Every message is written to the `notifications` table in the same transaction as the change that
caused it, so there is never a message about something that was rolled back and never a change
whose message was lost (a transactional outbox). Delivery is separate:

- with `NOTIFY_WEBHOOK_URL` set, a background task posts each pending message to that URL (an SMS
  or WhatsApp gateway, or a small relay in front of one) and marks it SENT, retrying up to three
  times before marking it FAILED;
- without it nothing leaves the server and the messages wait as PENDING on the Messages page, where
  reception can phone the patient and mark each one sent. That is the honest default: the clinic
  chooses and pays for a gateway, and this project does not pretend to have sent anything.

A message is only sent to a patient whose consent to the privacy notice is recorded; otherwise it is
SKIPPED, still listed, so reception knows to phone. Message text never reaches the logs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ConflictError, ErrorCode, NotFoundError
from app.domain.violations import ist_text
from app.persistence.models import Notification, Patient
from app.services.support import run
from app.services.views import Page

log = structlog.get_logger()

MAX_ATTEMPTS = 3
BATCH = 50
STATUSES = ("PENDING", "SENT", "FAILED", "SKIPPED")


class Provider(Protocol):
    def send(self, to: str, body: str, kind: str) -> None:
        """Deliver one message or raise."""


class WebhookProvider:
    """POSTs `{"to", "body", "kind"}` as JSON, with an optional bearer token. Any non-2xx or network
    error counts as a failure, so the message is retried."""

    def __init__(self, url: str, token: str | None = None, timeout_s: float = 5.0) -> None:
        self._url, self._token, self._timeout = url, token, timeout_s

    def send(self, to: str, body: str, kind: str) -> None:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(  # noqa: S310 - the URL is operator configuration
            self._url,
            data=json.dumps({"to": to, "body": body, "kind": kind}).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout):  # noqa: S310
            pass


@dataclass(frozen=True, slots=True)
class NotificationView:
    id: int
    patient_id: int
    appointment_id: int | None
    kind: str
    to_phone: str
    body: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    sent_via: str | None


def _view(row: Notification) -> NotificationView:
    return NotificationView(
        row.id,
        row.patient_id,
        row.appointment_id,
        row.kind,
        row.to_phone,
        row.body,
        row.status,
        row.attempts,
        row.last_error,
        row.created_at,
        row.sent_at,
        row.sent_via,
    )


# ----------------------------------------------------------------------------- the message texts


def booked_text(doctor: str, start: datetime) -> str:
    return f"Your appointment with {doctor} is booked for {ist_text(start)} (India time)."


def moved_text(doctor: str, start: datetime) -> str:
    return f"Your appointment has been moved: {doctor}, {ist_text(start)} (India time)."


def cancelled_text(doctor: str, start: datetime) -> str:
    return (
        f"The clinic has cancelled your appointment with {doctor} on {ist_text(start)}. "
        "Please call us to choose another time. This does not count against you."
    )


def offer_text(doctor: str, start: datetime, until: datetime) -> str:
    return (
        f"A time has opened with {doctor} on {ist_text(start)}. It is held for you until "
        f"{ist_text(until)}; call the clinic to take it."
    )


# ------------------------------------------------------------------ writing (in-transaction)


def queue_message(
    session: Session,
    patient: Patient,
    kind: str,
    body: str,
    appointment_id: int | None = None,
) -> Notification:
    """Add a message to the outbox as part of the caller's transaction."""
    consented = patient.consent_at is not None
    row = Notification(
        patient_id=patient.id,
        appointment_id=appointment_id,
        kind=kind,
        to_phone=patient.phone,
        body=body,
        status="PENDING" if consented else "SKIPPED",
        last_error=None if consented else "No consent recorded: tell the patient by phone.",
    )
    session.add(row)
    session.flush()
    return row


def scrub_patient(session: Session, patient: Patient, placeholder_phone: str) -> None:
    """On erasure: keep the outbox rows (counts, ids) but remove the phone number and the text."""
    for row in session.scalars(select(Notification).where(Notification.patient_id == patient.id)):
        row.to_phone = placeholder_phone
        row.body = "[erased]"


# ------------------------------------------------------------------------------------- service


class NotificationService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list(self, status: str | None, limit: int, offset: int) -> Page[NotificationView]:
        def work(session: Session) -> Page[NotificationView]:
            condition = [Notification.status == status] if status is not None else []
            total = (
                session.scalar(select(func.count()).select_from(Notification).where(*condition))
                or 0
            )
            rows = session.scalars(
                select(Notification)
                .where(*condition)
                .order_by(Notification.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return Page([_view(r) for r in rows], total, limit, offset)

        return run(self._factory, work)

    def pending_count(self) -> int:
        def work(session: Session) -> int:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.status.in_(("PENDING", "SKIPPED")))
                )
                or 0
            )

        return run(self._factory, work)

    def mark_sent(self, notification_id: int, now: datetime) -> NotificationView:
        """Reception told the patient themselves (by phone, or a message sent by hand)."""

        def work(session: Session) -> NotificationView:
            row = session.get(Notification, notification_id, with_for_update=True)
            if row is None:
                raise NotFoundError(
                    ErrorCode.NOTIFICATION_NOT_FOUND,
                    f"There is no message {notification_id}.",
                    notification_id=notification_id,
                )
            if row.status == "SENT":
                raise ConflictError(
                    ErrorCode.INVALID_TRANSITION, "This message is already marked as sent."
                )
            row.status, row.sent_at, row.sent_via = "SENT", now, "MANUAL"
            session.flush()
            return _view(row)

        return run(self._factory, work)

    def dispatch(self, provider: Provider, now: datetime) -> int:
        """Send pending messages through `provider`; returns how many were delivered.

        Each message is handled in its own transaction under a row lock that skips rows another
        instance is already working on, so two servers never send the same message twice. A failure
        is counted and kept; after `MAX_ATTEMPTS` the message is FAILED and shows on the page.
        """
        ids = run(
            self._factory,
            lambda session: list(
                session.scalars(
                    select(Notification.id)
                    .where(Notification.status == "PENDING", Notification.attempts < MAX_ATTEMPTS)
                    .order_by(Notification.id)
                    .limit(BATCH)
                )
            ),
        )
        delivered = 0
        for notification_id in ids:
            delivered += self._deliver(provider, notification_id, now)
        return delivered

    def _deliver(self, provider: Provider, notification_id: int, now: datetime) -> int:
        def work(session: Session) -> int:
            row = session.scalars(
                select(Notification)
                .where(Notification.id == notification_id, Notification.status == "PENDING")
                .with_for_update(skip_locked=True)
            ).one_or_none()
            if row is None:
                return 0
            try:
                provider.send(row.to_phone, row.body, row.kind)
            except (urllib.error.URLError, OSError, ValueError) as error:
                row.attempts += 1
                row.last_error = type(error).__name__
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "FAILED"
                log.warning(
                    "notification.failed",
                    notification_id=row.id,
                    attempts=row.attempts,
                    error_type=type(error).__name__,
                )
                return 0
            row.status, row.sent_at, row.sent_via = "SENT", now, "GATEWAY"
            row.attempts += 1
            row.last_error = None
            log.info("notification.sent", notification_id=row.id, kind=row.kind)
            return 1

        return run(self._factory, work)
