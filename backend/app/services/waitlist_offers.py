"""Offering a freed slot to the first waiting patient who can take it.

Kept apart from `waitlist_service` because booking (cancel, reschedule) calls it and the waitlist
service calls booking: this module depends on neither.

An offer is not a reservation. It lasts 30 minutes (never past the start of the slot), and
accepting it is an ordinary booking, so another booking may win the race and the deposit rule still
applies. The caller holds the doctor row lock and has flushed the change that freed the slot.

An offer that lapses or is declined does not strand the slot: `settle_offers` passes it on to the
next patient in the queue (never back to someone who declined that same slot).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.slots import first_violation
from app.domain.timeutil import ist_date
from app.persistence import repositories as repo
from app.persistence.models import Doctor, WaitlistEntry

log = structlog.get_logger()

OFFER_HOLD = timedelta(minutes=30)
ACTIVE = ("WAITING", "OFFERED")


def _expire(session: Session, doctor_id: int, now: datetime) -> list[datetime]:
    """Mark lapsed offers EXPIRED; return the slots they were holding."""
    lapsed = session.scalars(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.doctor_id == doctor_id,
            WaitlistEntry.status == "OFFERED",
            WaitlistEntry.offer_expires_at < now,
        )
        .order_by(WaitlistEntry.id)
    ).all()
    for entry in lapsed:
        entry.status = "EXPIRED"
    session.flush()
    return sorted({e.offered_start_at for e in lapsed if e.offered_start_at is not None})


def settle_offers(session: Session, doctor: Doctor, now: datetime) -> None:
    """Expire lapsed offers and pass each slot on to the next patient. Doctor row lock held."""
    for slot in _expire(session, doctor.id, now):
        offer_slot(session, doctor, slot, now)


def offer_freed_slot(
    session: Session, doctor: Doctor, start_at: datetime, now: datetime
) -> WaitlistEntry | None:
    """Offer the slot starting at `start_at` to the first waiting patient who could take it.

    The caller holds the doctor row lock and has already flushed the change that freed the slot.
    """
    settle_offers(session, doctor, now)
    return offer_slot(session, doctor, start_at, now)


def offer_slot(
    session: Session, doctor: Doctor, start_at: datetime, now: datetime
) -> WaitlistEntry | None:
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
            or_(
                WaitlistEntry.declined_start_at.is_(None),
                WaitlistEntry.declined_start_at != start_at,
            ),
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
