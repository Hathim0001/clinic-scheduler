"""The Messages page: what was queued for patients, and what reception sent by hand."""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import NowDep, ServicesDep
from app.api.params import Limit, Offset
from app.api.schemas.responses import PageOut
from app.domain.timeutil import utc_iso
from app.services.notification_service import NotificationView

router = APIRouter(prefix="/notifications", tags=["notifications"])
log = structlog.get_logger()

Status = Literal["PENDING", "SENT", "FAILED", "SKIPPED"]


class NotificationOut(BaseModel):
    id: int
    patient_id: int
    appointment_id: int | None
    kind: str
    to_phone: str
    body: str
    status: str
    attempts: int
    last_error: str | None
    created_at_utc: str
    sent_at_utc: str | None
    sent_via: str | None


class PendingOut(BaseModel):
    count: int  # messages still waiting to be sent or phoned through


def notification_out(view: NotificationView) -> NotificationOut:
    return NotificationOut(
        id=view.id,
        patient_id=view.patient_id,
        appointment_id=view.appointment_id,
        kind=view.kind,
        to_phone=view.to_phone,
        body=view.body,
        status=view.status,
        attempts=view.attempts,
        last_error=view.last_error,
        created_at_utc=utc_iso(view.created_at),
        sent_at_utc=utc_iso(view.sent_at) if view.sent_at else None,
        sent_via=view.sent_via,
    )


@router.get(
    "", response_model=PageOut[NotificationOut], summary="Messages to patients, newest first"
)
def list_notifications(
    services: ServicesDep, status: Status | None = None, limit: Limit = 20, offset: Offset = 0
) -> PageOut[NotificationOut]:
    """PENDING is waiting for the gateway (or for reception when none is set); SKIPPED had no
    recorded consent, so reception should phone; FAILED ran out of retries."""
    page = services.notifications.list(status, limit, offset)
    return PageOut(
        items=[notification_out(v) for v in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/pending", response_model=PendingOut, summary="How many messages still need sending")
def pending(services: ServicesDep) -> PendingOut:
    return PendingOut(count=services.notifications.pending_count())


@router.post(
    "/{notification_id}/sent",
    response_model=NotificationOut,
    summary="Mark a message as sent by hand (reception phoned or messaged the patient)",
    responses={404: {"description": "NOTIFICATION_NOT_FOUND"}},
)
def mark_sent(notification_id: int, services: ServicesDep, now: NowDep) -> NotificationOut:
    view = services.notifications.mark_sent(notification_id, now)
    log.info("notification.marked_sent", notification_id=notification_id)
    return notification_out(view)
