"""Booking, cancelling, rescheduling and marking appointments.

Every public method is one database transaction, and the work inside it always goes in this order:

1. lock the rows that make the decision safe, in the fixed hierarchy appointment, then doctors by
   ascending id, then the patient (plan 17.8), so two requests can never wait on each other;
2. load the facts the rules need;
3. let the domain functions decide (they never touch the database);
4. write, and let the database constraints have the last word on overlaps.

`now` is passed in and never read from a clock, so a retry after a deadlock repeats the same unit
of work and the test clock stays consistent.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import delete, func
from sqlalchemy.orm import Session, sessionmaker

from app.domain.cancellation import check_can_reschedule, classify_cancellation
from app.domain.errors import ConflictError, DomainError, ErrorCode, RuleViolation
from app.domain.model import CancelledBy, DepositStatus, Status
from app.domain.penalties import deposit_status
from app.domain.slots import first_violation
from app.domain.timeutil import ist_date, ist_iso, utc_iso
from app.domain.transitions import (
    check_can_cancel,
    check_can_check_in,
    check_can_mark,
    check_correction,
)
from app.domain.violations import deposit_required_error, ist_text, violation_error
from app.persistence import repositories as repo
from app.persistence.models import Appointment, Doctor, IdempotencyKey, Patient
from app.services.appointment_views import view_of
from app.services.support import run
from app.services.views import AppointmentView, BookCommand, CancelResult, RescheduleResult
from app.services.waitlist_offers import offer_freed_slot

KEY_LIFETIME = timedelta(hours=24)


def deposit_of(session: Session, patient_id: int, now: datetime) -> DepositStatus:
    return deposit_status(repo.penalty_events(session, patient_id, now), now)


def place_booking(
    session: Session,
    doctor: Doctor,
    patient: Patient,
    start_at: datetime,
    reason: str,
    deposit_confirmed: bool,
    deposit: DepositStatus,
    now: datetime,
    via: str = "BOOKING",
) -> Appointment:
    """Check every rule for the slot, then insert a BOOKED appointment. Locks must be held."""
    context = repo.slot_context(session, doctor, patient.id, ist_date(start_at), now)
    violation = first_violation(start_at, context)
    if violation is not None:
        raise violation_error(violation, start_at, context, patient.id)
    if deposit.required and not deposit_confirmed:
        raise deposit_required_error(deposit)

    appointment = Appointment(
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=doctor.slot_length_min),
        status=Status.BOOKED.value,
        reason=reason,
        deposit_required_at_booking=deposit.required,
        deposit_confirmed=deposit_confirmed,
    )
    session.add(appointment)
    session.flush()  # an overlap that slipped past the checks fails here, on the constraint
    repo.record_event(
        session,
        appointment,
        "BOOKED",
        now,
        via=via,
        doctor_id=doctor.id,
        start_at=utc_iso(start_at),
        deposit_confirmed=deposit_confirmed,
    )
    return appointment


def _request_hash(command: BookCommand) -> str:
    text = "|".join(
        (
            str(command.doctor_id),
            str(command.patient_id),
            utc_iso(command.start_at),
            command.reason,
            str(command.deposit_confirmed),
        )
    )
    return hashlib.sha256(text.encode()).hexdigest()


class BookingService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def book(self, command: BookCommand, now: datetime) -> AppointmentView:
        def work(session: Session) -> AppointmentView:
            doctor = repo.get_doctor(session, command.doctor_id, lock=True)
            patient = repo.get_patient(session, command.patient_id, lock=True)
            deposit = deposit_of(session, patient.id, now)
            appointment = place_booking(
                session,
                doctor,
                patient,
                command.start_at,
                command.reason,
                command.deposit_confirmed,
                deposit,
                now,
            )
            return view_of(session, appointment.id, now)

        return run(self._factory, work)

    def book_idempotent(
        self, command: BookCommand, key: str, now: datetime
    ) -> tuple[AppointmentView, bool]:
        """Book once per `key`: a retry of the same request returns the same appointment.

        This is for a response lost on the way back (a timeout, a double click, an integration that
        resends an event). The key is stored in the same transaction as the booking, and the doctor
        row is locked first, so two copies of one request arriving together are served one after
        the other: the second finds the key and returns the first's appointment. The same key with
        a different request is refused rather than guessed at. Returns the view and whether it was
        a replay.
        """
        fingerprint = _request_hash(command)

        def work(session: Session) -> tuple[AppointmentView, bool]:
            doctor = repo.get_doctor(session, command.doctor_id, lock=True)
            patient = repo.get_patient(session, command.patient_id, lock=True)
            session.execute(  # by the database's own clock, so a test clock cannot expire real keys
                delete(IdempotencyKey).where(IdempotencyKey.created_at < func.now() - KEY_LIFETIME)
            )
            seen = session.get(IdempotencyKey, key)
            if seen is not None:
                if seen.request_hash != fingerprint:
                    raise ConflictError(
                        ErrorCode.IDEMPOTENCY_KEY_REUSED,
                        "This Idempotency-Key was already used for a different request.",
                    )
                return view_of(session, seen.appointment_id, now), True
            deposit = deposit_of(session, patient.id, now)
            appointment = place_booking(
                session,
                doctor,
                patient,
                command.start_at,
                command.reason,
                command.deposit_confirmed,
                deposit,
                now,
            )
            session.add(
                IdempotencyKey(key=key, request_hash=fingerprint, appointment_id=appointment.id)
            )
            session.flush()
            return view_of(session, appointment.id, now), False

        return run(self._factory, work)

    def book_series(
        self, command: BookCommand, every_days: int, count: int, now: datetime
    ) -> list[AppointmentView]:
        """Book `count` appointments, `every_days` apart at the same India time, all or none.

        Every occurrence goes through the same checks as a single booking. If one fails (a leave
        day, a taken slot, the cap) the whole series is rolled back and the error says which
        occurrence it was.
        """

        def work(session: Session) -> list[AppointmentView]:
            doctor = repo.get_doctor(session, command.doctor_id, lock=True)
            patient = repo.get_patient(session, command.patient_id, lock=True)
            deposit = deposit_of(session, patient.id, now)
            ids = []
            for index in range(count):
                start = command.start_at + timedelta(days=every_days * index)
                try:
                    placed = place_booking(
                        session,
                        doctor,
                        patient,
                        start,
                        command.reason,
                        command.deposit_confirmed,
                        deposit,
                        now,
                    )
                except DomainError as error:
                    error.message = (
                        f"Occurrence {index + 1} of {count} ({ist_text(start)}): {error.message}"
                    )
                    error.args = (error.message,)
                    error.details.update(occurrence=index + 1, start_at=ist_iso(start))
                    raise
                ids.append(placed.id)
            return [view_of(session, appointment_id, now) for appointment_id in ids]

        return run(self._factory, work)

    def cancel(self, appointment_id: int, cancelled_by: CancelledBy, now: datetime) -> CancelResult:
        def work(session: Session) -> CancelResult:
            appointment = repo.get_appointment(session, appointment_id, lock=True)
            check_can_cancel(Status(appointment.status))
            if cancelled_by is CancelledBy.PATIENT:
                _require_not_checked_in(appointment, "cancelled")
            outcome = classify_cancellation(appointment.start_at, now, cancelled_by)
            appointment.status = outcome.value
            appointment.cancelled_at = now
            appointment.cancelled_by = cancelled_by.value
            appointment.status_changed_at = now
            session.flush()
            repo.record_event(
                session,
                appointment,
                outcome.value,
                now,
                by=cancelled_by.value,
                start_at=utc_iso(appointment.start_at),
            )
            doctor = repo.get_doctor(session, appointment.doctor_id, lock=True)
            offer_freed_slot(session, doctor, appointment.start_at, now)  # waiting patients first
            return CancelResult(
                appointment=view_of(session, appointment.id, now),
                late=outcome is Status.LATE_CANCELLED,
                deposit=deposit_of(session, appointment.patient_id, now),
            )

        return run(self._factory, work)

    def reschedule(
        self,
        appointment_id: int,
        start_at: datetime,
        doctor_id: int | None,
        deposit_confirmed: bool | None,
        now: datetime,
    ) -> RescheduleResult:
        """Move an appointment: cancel the old one, book the new one, in one transaction.

        The old one is cancelled first so the new slot may overlap the patient's own old slot and
        the old slot stops counting toward the cap. If anything about the new slot is wrong the
        whole transaction rolls back and the old appointment is untouched.
        """

        def work(session: Session) -> RescheduleResult:
            old = repo.get_appointment(session, appointment_id, lock=True)
            check_can_cancel(Status(old.status))
            _require_not_checked_in(old, "rescheduled")
            check_can_reschedule(old.start_at, now)
            target_doctor_id = doctor_id if doctor_id is not None else old.doctor_id
            doctors = repo.lock_doctors(session, {old.doctor_id, target_doctor_id})
            patient = repo.get_patient(session, old.patient_id, lock=True)

            if target_doctor_id == old.doctor_id and start_at == old.start_at:
                raise RuleViolation(
                    ErrorCode.RESCHEDULE_NO_CHANGE,
                    "The new time and doctor are the same as the current appointment.",
                )

            # The deposit check uses the patient's status before this move's own cancellation, so
            # moving a late appointment does not flag the patient for the booking they asked for.
            deposit = deposit_of(session, patient.id, now)
            confirmed = old.deposit_confirmed if deposit_confirmed is None else deposit_confirmed

            outcome = classify_cancellation(old.start_at, now, CancelledBy.PATIENT)
            old.status = outcome.value
            old.cancelled_at = now
            old.cancelled_by = CancelledBy.PATIENT.value
            old.status_changed_at = now
            session.flush()

            new = place_booking(
                session,
                doctors[target_doctor_id],
                patient,
                start_at,
                old.reason,
                confirmed,
                deposit,
                now,
                via="RESCHEDULE",
            )
            old.rescheduled_to_id = new.id
            session.flush()
            repo.record_event(
                session,
                old,
                outcome.value,
                now,
                by=CancelledBy.PATIENT.value,
                start_at=utc_iso(old.start_at),
                rescheduled_to_id=new.id,
                rescheduled_to_start_at=utc_iso(new.start_at),
            )
            repo.record_event(session, new, "RESCHEDULED_FROM", now, from_id=old.id)
            offer_freed_slot(session, doctors[old.doctor_id], old.start_at, now)
            return RescheduleResult(
                old=view_of(session, old.id, now), new=view_of(session, new.id, now)
            )

        return run(self._factory, work)

    def complete(self, appointment_id: int, now: datetime) -> AppointmentView:
        return self._mark(appointment_id, Status.COMPLETED, now)

    def no_show(self, appointment_id: int, now: datetime) -> AppointmentView:
        return self._mark(appointment_id, Status.NO_SHOW, now)

    def _mark(self, appointment_id: int, status: Status, now: datetime) -> AppointmentView:
        def work(session: Session) -> AppointmentView:
            appointment = repo.get_appointment(session, appointment_id, lock=True)
            check_can_mark(Status(appointment.status), appointment.start_at, now)
            appointment.status = status.value
            appointment.status_changed_at = now
            session.flush()
            repo.record_event(session, appointment, status.value, now)
            return view_of(session, appointment.id, now)

        return run(self._factory, work)

    def check_in(self, appointment_id: int, now: datetime) -> AppointmentView:
        """Record that the patient has arrived. Doing it twice changes nothing."""

        def work(session: Session) -> AppointmentView:
            appointment = repo.get_appointment(session, appointment_id, lock=True)
            if appointment.checked_in_at is None:
                check_can_check_in(Status(appointment.status), appointment.start_at, now)
                appointment.checked_in_at = now
                session.flush()
                repo.record_event(session, appointment, "CHECKED_IN", now)
            return view_of(session, appointment.id, now)

        return run(self._factory, work)

    def correct(
        self, appointment_id: int, target: Status, note: str, now: datetime
    ) -> AppointmentView:
        """Fix a wrongly recorded outcome, keeping the original in the history (A-48).

        COMPLETED and NO_SHOW swap; a LATE_CANCELLED can be waived to CANCELLED. The deposit flag
        is worked out from the statuses, so a correction takes effect on it straight away.
        """

        def work(session: Session) -> AppointmentView:
            appointment = repo.get_appointment(session, appointment_id, lock=True)
            before = Status(appointment.status)
            check_correction(before, target)
            appointment.status = target.value
            appointment.status_changed_at = now
            session.flush()
            repo.record_event(
                session,
                appointment,
                "CORRECTED",
                now,
                from_status=before.value,
                to_status=target.value,
                note=note,
            )
            return view_of(session, appointment.id, now)

        return run(self._factory, work)


def _require_not_checked_in(appointment: Appointment, action: str) -> None:
    if appointment.checked_in_at is not None:
        raise ConflictError(
            ErrorCode.ALREADY_CHECKED_IN,
            f"The patient has already checked in, so the appointment cannot be {action} by "
            "the patient. The clinic can cancel it or mark the outcome.",
            checked_in_at=utc_iso(appointment.checked_in_at),
        )
