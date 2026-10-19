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
from datetime import datetime, timedelta
from typing import Protocol

import structlog
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ConflictError, ErrorCode, NotFoundError
from app.domain.violations import ist_text
from app.persistence import repositories as repo
from app.persistence.models import Appointment, AppointmentEvent, Doctor, Notification, Patient
from app.services.support import run
from app.services.views import Page

log = structlog.get_logger()

MAX_ATTEMPTS = 3
LEASE = timedelta(minutes=2)  # how long a claimed message is left alone while it is being sent
BATCH = 50
STATUSES = ("PENDING", "SENT", "FAILED", "SKIPPED")
REMINDER_KINDS = ("REMINDER_FIRST", "REMINDER_SECOND")
REMINDER_BATCH = 200


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


def restored_text(doctor: str, start: datetime) -> str:
    return (
        f"Good news: your appointment with {doctor} on {ist_text(start)} (India time) "
        "is back on. The cancellation was undone."
    )


def reminder_text(doctor: str, start: datetime) -> str:
    return (
        f"Reminder: you have an appointment with {doctor} on {ist_text(start)} (India time). "
        "Please call the clinic if you cannot come, so the time can go to someone else."
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

    def schedule_reminders(self, now: datetime) -> int:
        """Queue the reminders that have come due; returns how many were queued.

        A reminder is due when the visit is still ahead, is no more than the clinic's reminder lead
        away, and was booked before that moment (a visit booked three hours ahead needs no "24 hours
        before" message on top of its confirmation). Each kind is queued once per appointment: a
        unique index guarantees it even when two servers run this at the same time. Reminders still
        waiting for a visit that has since been cancelled or moved are withdrawn. Run it on a timer;
        it is cheap and safe to repeat.
        """

        def work(session: Session) -> int:
            policy = repo.load_policy(session)
            leads = (
                ("REMINDER_FIRST", policy.reminder_first_hours),
                ("REMINDER_SECOND", policy.reminder_second_hours),
            )
            queued = sum(
                self._queue_due(session, kind, timedelta(hours=hours), now)
                for kind, hours in leads
                if hours > 0
            )
            self._withdraw_stale(session, now)
            return queued

        return run(self._factory, work)

    @staticmethod
    def _queue_due(session: Session, kind: str, lead: timedelta, now: datetime) -> int:
        booked_at = func.coalesce(
            select(func.min(AppointmentEvent.at))
            .where(
                AppointmentEvent.appointment_id == Appointment.id,
                AppointmentEvent.kind == "BOOKED",
            )
            .correlate(Appointment)
            .scalar_subquery(),
            Appointment.created_at,
        )
        due = session.execute(
            select(Appointment, Doctor.name, Patient)
            .join(Doctor, Doctor.id == Appointment.doctor_id)
            .join(Patient, Patient.id == Appointment.patient_id)
            .where(
                Appointment.status == "BOOKED",
                Appointment.start_at > now,
                Appointment.start_at <= now + lead,
                booked_at <= Appointment.start_at - lead,
                Patient.erased_at.is_(None),
                ~exists().where(
                    Notification.appointment_id == Appointment.id, Notification.kind == kind
                ),
            )
            .order_by(Appointment.start_at, Appointment.id)
            .limit(REMINDER_BATCH)
        ).all()
        queued = 0
        for appointment, doctor_name, patient in due:
            try:
                with session.begin_nested():  # a lost race on the unique index costs nothing
                    queue_message(
                        session,
                        patient,
                        kind,
                        reminder_text(doctor_name, appointment.start_at),
                        appointment.id,
                    )
            except IntegrityError:
                continue
            queued += 1
        return queued

    @staticmethod
    def _withdraw_stale(session: Session, now: datetime) -> None:
        """Reminders that are still waiting for a visit that is over, cancelled or moved."""
        stale = select(Appointment.id).where(
            or_(Appointment.status != "BOOKED", Appointment.start_at <= now)
        )
        session.execute(
            update(Notification)
            .where(
                Notification.kind.in_(REMINDER_KINDS),
                Notification.status == "PENDING",
                Notification.appointment_id.in_(stale),
            )
            .values(status="SKIPPED", last_error="The visit is no longer ahead; nothing to remind.")
        )

    def summary(self) -> dict[str, int]:
        """How many messages are in each status, and how many were reminders sent by the gateway."""

        def work(session: Session) -> dict[str, int]:
            rows = session.execute(
                select(Notification.status, func.count()).group_by(Notification.status)
            ).all()
            counts = dict.fromkeys(STATUSES, 0)
            counts.update({status: int(count) for status, count in rows})
            counts["reminders_sent"] = (
                session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.kind.in_(REMINDER_KINDS), Notification.status == "SENT")
                )
                or 0
            )
            return counts

        return run(self._factory, work)

    def dispatch(self, provider: Provider, now: datetime) -> int:
        """Send pending messages through `provider`; returns how many were delivered.

        A message is claimed with a short lease in one transaction, sent with no transaction open
        (a slow gateway never holds a database connection or a row lock), and its outcome written in
        a second transaction. Two servers never claim the same message: the claim uses a row lock
        that skips rows another instance holds, and the lease keeps a crashed sender's message from
        being retried for `LEASE`. A failure is counted; after `MAX_ATTEMPTS` the message is FAILED.
        """
        ids = run(
            self._factory,
            lambda session: list(
                session.scalars(
                    select(Notification.id)
                    .where(
                        Notification.status == "PENDING",
                        Notification.attempts < MAX_ATTEMPTS,
                        or_(Notification.locked_until.is_(None), Notification.locked_until < now),
                    )
                    .order_by(Notification.id)
                    .limit(BATCH)
                )
            ),
        )
        return sum(self._deliver(provider, notification_id, now) for notification_id in ids)

    def _claim(self, notification_id: int, now: datetime) -> tuple[str, str, str] | None:
        def work(session: Session) -> tuple[str, str, str] | None:
            row = session.scalars(
                select(Notification)
                .where(
                    Notification.id == notification_id,
                    Notification.status == "PENDING",
                    or_(Notification.locked_until.is_(None), Notification.locked_until < now),
                )
                .with_for_update(skip_locked=True)
            ).one_or_none()
            if row is None:
                return None
            row.locked_until = now + LEASE
            return row.to_phone, row.body, row.kind

        return run(self._factory, work)

    def _finish(self, notification_id: int, now: datetime, error: str | None) -> int:
        def work(session: Session) -> int:
            row = session.get(Notification, notification_id, with_for_update=True)
            if row is None or row.status != "PENDING":
                return 0
            row.locked_until = None
            row.attempts += 1
            if error is None:
                row.status, row.sent_at, row.sent_via, row.last_error = "SENT", now, "GATEWAY", None
                log.info("notification.sent", notification_id=row.id, kind=row.kind)
                return 1
            row.last_error = error
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "FAILED"
            log.warning(
                "notification.failed",
                notification_id=row.id,
                attempts=row.attempts,
                error_type=error,
            )
            return 0

        return run(self._factory, work)

    def _deliver(self, provider: Provider, notification_id: int, now: datetime) -> int:
        claimed = self._claim(notification_id, now)
        if claimed is None:
            return 0
        to, body, kind = claimed
        try:
            provider.send(to, body, kind)
        except (urllib.error.URLError, OSError, ValueError) as error:
            return self._finish(notification_id, now, type(error).__name__)
        return self._finish(notification_id, now, None)
