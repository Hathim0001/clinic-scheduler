"""Offering a freed slot to the first waiting patient who can take it.

Kept apart from `waitlist_service` because booking (cancel, reschedule) calls it and the waitlist
service calls booking: this module depends on neither.

An offer is not a reservation. It lasts 30 minutes (never past the start of the slot), and
accepting it is an ordinary booking, so another booking may win the race and the deposit rule still
applies. The caller holds the doctor row lock and has flushed the change that freed the slot.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.slots import first_violation
from app.domain.timeutil import ist_date
from app.persistence import repositories as repo
from app.persistence.models import Doctor, WaitlistEntry

log = structlog.get_logger()

OFFER_HOLD = timedelta(minutes=30)
ACTIVE = ("WAITING", "OFFERED")


def expire_stale_offers(session: Session, doctor_id: int, now: datetime) -> None:
    session.execute(
        update(WaitlistEntry)
        .where(
            WaitlistEntry.doctor_id == doctor_id,
            WaitlistEntry.status == "OFFERED",
            WaitlistEntry.offer_expires_at < now,
        )
        .values(status="EXPIRED")
    )


def offer_freed_slot(
    session: Session, doctor: Doctor, start_at: datetime, now: datetime
) -> WaitlistEntry | None:
    """Offer the slot starting at `start_at` to the first waiting patient who could take it.

    The caller holds the doctor row lock and has already flushed the change that freed the slot.
    """
    expire_stale_offers(session, doctor.id, now)
    day = ist_date(start_at)
    already_offered = session.scalar(
        select(WaitlistEntry.id).where(
            WaitlistEntry.doctor_id == doctor.id,
            WaitlistEntry.status == "OFFERED",
            WaitlistEntry.offered_start_at == start_at,
        )
    )
    if already_offered is not None:
        return None
    waiting = session.scalars(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.doctor_id == doctor.id,
            WaitlistEntry.on_date == day,
            WaitlistEntry.status == "WAITING",
        )
        .order_by(WaitlistEntry.created_at, WaitlistEntry.id)
    ).all()
    for entry in waiting:
        context = repo.slot_context(session, doctor, entry.patient_id, day, now)
        if first_violation(start_at, context) is None:
            entry.status = "OFFERED"
            entry.offered_start_at = start_at
            entry.offer_expires_at = min(now + OFFER_HOLD, start_at)
            session.flush()
            log.info(
                "waitlist.offered",
                waitlist_id=entry.id,
                doctor_id=doctor.id,
                patient_id=entry.patient_id,
            )
            return entry
    return None
