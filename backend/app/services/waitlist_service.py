"""The waitlist: patients waiting for a slot with a doctor on one India date, and the offers made to
them when a cancellation frees a slot.

How an offer happens: when an appointment is cancelled or moved, `offer_freed_slot` looks at the
people waiting for that doctor and date, oldest first, and offers the freed slot to the first one
who could actually take it (the same `first_violation` check as a booking, so an offer is never for
a time the rules would refuse). The offer is not a reservation: it lasts 30 minutes (never past the
start of the slot), and accepting it is an ordinary booking, so another booking may win the race and
the deposit rule still applies.

Lock order (extends plan 17.8): appointment, doctors by id, waitlist entry, patient.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import structlog
from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.booking_window import HORIZON_DAYS
from app.domain.errors import ConflictError, DomainError, ErrorCode, NotFoundError, RuleViolation
from app.domain.timeutil import ist_date
from app.persistence import repositories as repo
from app.persistence.models import Doctor, Patient, WaitlistEntry
from app.services.appointment_views import view_of
from app.services.booking_service import deposit_of, place_booking
from app.services.support import run
from app.services.views import WaitlistAcceptance, WaitlistView
from app.services.waitlist_offers import ACTIVE, offer_slot, settle_offers

log = structlog.get_logger()


def _live(now: datetime) -> ColumnElement[bool]:
    """Waiting, or holding an offer that has not run out."""
    return or_(
        WaitlistEntry.status == "WAITING",
        and_(WaitlistEntry.status == "OFFERED", WaitlistEntry.offer_expires_at >= now),
    )


def _views(session: Session, entries: list[WaitlistEntry]) -> list[WaitlistView]:
    ids = {e.doctor_id for e in entries} | {e.patient_id for e in entries}
    doctors = {d.id: d for d in session.scalars(select(Doctor).where(Doctor.id.in_(ids)))}
    patients = {p.id: p for p in session.scalars(select(Patient).where(Patient.id.in_(ids)))}
    # A place in the queue counts everyone waiting for that doctor and date, not just these entries.
    positions: dict[int, int] = {}
    for doctor_id, day in {(e.doctor_id, e.on_date) for e in entries if e.status == "WAITING"}:
        queue = session.scalars(
            select(WaitlistEntry.id)
            .where(
                WaitlistEntry.doctor_id == doctor_id,
                WaitlistEntry.on_date == day,
                WaitlistEntry.status == "WAITING",
            )
            .order_by(WaitlistEntry.created_at, WaitlistEntry.id)
        )
        positions.update({entry_id: place for place, entry_id in enumerate(queue, start=1)})
    return [
        WaitlistView(
            id=e.id,
            doctor_id=e.doctor_id,
            doctor_name=doctors[e.doctor_id].name,
            patient_id=e.patient_id,
            patient_name=patients[e.patient_id].name,
            patient_phone=patients[e.patient_id].phone,
            day=e.on_date,
            status=e.status,
            position=positions.get(e.id),
            offered_start_at=e.offered_start_at,
            offer_expires_at=e.offer_expires_at,
            appointment_id=e.appointment_id,
        )
        for e in entries
    ]


def _entry(session: Session, entry_id: int, *, lock: bool = False) -> WaitlistEntry:
    statement = select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
    entry = session.scalars(statement.with_for_update() if lock else statement).one_or_none()
    if entry is None:
        raise NotFoundError(
            ErrorCode.WAITLIST_ENTRY_NOT_FOUND,
            f"There is no waitlist entry with id {entry_id}.",
            waitlist_id=entry_id,
        )
    return entry


class WaitlistService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def join(self, doctor_id: int, patient_id: int, day: date, now: datetime) -> WaitlistView:
        def work(session: Session) -> WaitlistView:
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            repo.get_patient(session, patient_id)
            today = ist_date(now)
            if day < today:
                raise RuleViolation(ErrorCode.BOOKING_IN_PAST, "That date has already passed.")
            if day > today + timedelta(days=HORIZON_DAYS):
                raise RuleViolation(
                    ErrorCode.BOOKING_TOO_FAR,
                    f"The waitlist opens only {HORIZON_DAYS} days ahead.",
                )
            settle_offers(session, doctor, now)
            existing = session.scalar(
                select(WaitlistEntry.id).where(
                    WaitlistEntry.doctor_id == doctor.id,
                    WaitlistEntry.patient_id == patient_id,
                    WaitlistEntry.on_date == day,
                    WaitlistEntry.status.in_(ACTIVE),
                )
            )
            if existing is not None:
                raise ConflictError(
                    ErrorCode.ALREADY_WAITING,
                    "This patient is already on the waitlist for that doctor and date.",
                    waitlist_id=existing,
                )
            entry = WaitlistEntry(doctor_id=doctor.id, patient_id=patient_id, on_date=day)
            session.add(entry)
            session.flush()
            return _views(session, [entry])[0]

        view = run(self._factory, work)
        log.info("waitlist.joined", waitlist_id=view.id, doctor_id=doctor_id, patient_id=patient_id)
        return view

    def for_doctor_day(self, doctor_id: int, day: date, now: datetime) -> list[WaitlistView]:
        """Everyone still waiting or holding a live offer for that doctor and date, oldest first.

        A read: it takes no lock and writes nothing. An offer whose time has run out is simply not
        shown; the sweep (or the next change to this doctor's waitlist) passes the slot on.
        """

        def work(session: Session) -> list[WaitlistView]:
            repo.get_doctor(session, doctor_id)
            entries = list(
                session.scalars(
                    select(WaitlistEntry)
                    .where(
                        WaitlistEntry.doctor_id == doctor_id,
                        WaitlistEntry.on_date == day,
                        _live(now),
                    )
                    .order_by(WaitlistEntry.created_at, WaitlistEntry.id)
                )
            )
            return _views(session, entries)

        return run(self._factory, work)

    def for_patient(self, patient_id: int, now: datetime) -> list[WaitlistView]:
        """A patient's waitlist entries that are still alive, so their offers can be shown."""

        def work(session: Session) -> list[WaitlistView]:
            repo.get_patient(session, patient_id)
            entries = list(
                session.scalars(
                    select(WaitlistEntry)
                    .where(WaitlistEntry.patient_id == patient_id, _live(now))
                    .order_by(WaitlistEntry.on_date, WaitlistEntry.id)
                )
            )
            return _views(session, entries)

        return run(self._factory, work)

    def sweep(self, now: datetime) -> int:
        """Pass every lapsed offer on to the next patient in line; returns how many doctors moved.

        Run on a timer by the server and safe to run from any number of instances at once: each
        doctor is handled in its own transaction under that doctor's row lock.
        """
        doctor_ids = run(
            self._factory,
            lambda session: sorted(
                session.scalars(
                    select(WaitlistEntry.doctor_id)
                    .where(WaitlistEntry.status == "OFFERED", WaitlistEntry.offer_expires_at < now)
                    .distinct()
                )
            ),
        )
        for doctor_id in doctor_ids:

            def work(session: Session, doctor_id: int = doctor_id) -> None:
                settle_offers(session, repo.get_doctor(session, doctor_id, lock=True), now)

            run(self._factory, work)
        return len(doctor_ids)

    def leave(self, entry_id: int, now: datetime) -> WaitlistView:
        """Leave the queue. Leaving while holding an offer passes the slot to the next patient."""

        def work(session: Session) -> WaitlistView:
            doctor_id = _entry(session, entry_id).doctor_id
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            entry = _entry(session, entry_id, lock=True)
            if entry.status not in ACTIVE:
                raise ConflictError(
                    ErrorCode.INVALID_TRANSITION,
                    f"This waitlist entry is already {entry.status.lower()}.",
                    status=entry.status,
                )
            held = entry.offered_start_at if entry.status == "OFFERED" else None
            entry.status = "CANCELLED"
            session.flush()
            if held is not None:
                offer_slot(session, doctor, held, now, entry.offered_slots)
            return _views(session, [entry])[0]

        view = run(self._factory, work)
        log.info("waitlist.left", waitlist_id=entry_id)
        return view

    def decline(self, entry_id: int, now: datetime) -> WaitlistView:
        """Say no to an offer but keep the place in the queue; the slot goes to the next patient.

        The same slot is never offered to this patient again, so declining cannot loop.
        """

        def work(session: Session) -> WaitlistView:
            doctor_id = _entry(session, entry_id).doctor_id
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            entry = _entry(session, entry_id, lock=True)
            if entry.status != "OFFERED" or entry.offered_start_at is None:
                raise ConflictError(
                    ErrorCode.INVALID_TRANSITION,
                    "There is no open offer to decline.",
                    status=entry.status,
                )
            held = entry.offered_start_at
            lapsed = entry.offer_expires_at is not None and entry.offer_expires_at < now
            if lapsed:
                entry.status = "EXPIRED"
            else:
                entry.status = "WAITING"
                entry.declined_start_at = held
            entry.offered_start_at = None
            entry.offer_expires_at = None
            session.flush()
            offer_slot(session, doctor, held, now, entry.offered_slots)
            return _views(session, [entry])[0]

        view = run(self._factory, work)
        log.info("waitlist.declined", waitlist_id=entry_id)
        return view

    def accept(
        self, entry_id: int, reason: str, deposit_confirmed: bool, now: datetime
    ) -> WaitlistAcceptance:
        """Turn an offer into a booking, with every rule checked as for any booking."""

        def work(session: Session) -> WaitlistAcceptance | DomainError:
            doctor_id = _entry(session, entry_id).doctor_id
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            entry = _entry(session, entry_id, lock=True)
            patient = repo.get_patient(session, entry.patient_id, lock=True)
            if entry.status != "OFFERED" or entry.offered_start_at is None:
                raise ConflictError(
                    ErrorCode.INVALID_TRANSITION,
                    "There is no open offer for this waitlist entry.",
                    status=entry.status,
                )
            if entry.offer_expires_at is not None and entry.offer_expires_at < now:
                held = entry.offered_start_at
                entry.status = "EXPIRED"
                session.flush()
                offer_slot(
                    session, doctor, held, now, entry.offered_slots
                )  # on to the next patient
                return ConflictError(ErrorCode.OFFER_EXPIRED, "The offer has expired.")
            try:
                deposit = deposit_of(session, patient.id, now)
                appointment = place_booking(
                    session,
                    doctor,
                    patient,
                    entry.offered_start_at,
                    reason,
                    deposit_confirmed,
                    deposit,
                    now,
                    via="WAITLIST",
                    slots=entry.offered_slots,
                )
            except DomainError as error:
                if error.code is ErrorCode.DEPOSIT_REQUIRED:
                    raise  # the offer stays open: acknowledge the deposit and accept again
                # The slot is no longer bookable: the offer is dead and the patient waits again.
                # The change is committed, so the error is returned and raised after the commit.
                entry.status = "WAITING"
                entry.declined_start_at = entry.offered_start_at
                entry.offered_start_at = None
                entry.offer_expires_at = None
                session.flush()
                return error
            entry.status = "BOOKED"
            entry.appointment_id = appointment.id
            session.flush()
            return WaitlistAcceptance(
                _views(session, [entry])[0], appointment=view_of(session, appointment.id, now)
            )

        outcome = run(self._factory, work)
        if isinstance(outcome, DomainError):
            raise outcome
        log.info("waitlist.accepted", waitlist_id=entry_id, appointment_id=outcome.appointment.id)
        return outcome
