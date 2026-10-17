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

from datetime import datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.domain.cancellation import classify_cancellation
from app.domain.errors import ErrorCode, RuleViolation
from app.domain.model import CancelledBy, DepositStatus, Status
from app.domain.penalties import deposit_status
from app.domain.slots import first_violation
from app.domain.timeutil import ist_date
from app.domain.transitions import check_can_cancel, check_can_mark
from app.domain.violations import deposit_required_error, violation_error
from app.persistence import repositories as repo
from app.persistence.models import Appointment, Doctor, Patient
from app.services.appointment_views import view_of
from app.services.support import run
from app.services.views import AppointmentView, BookCommand, CancelResult, RescheduleResult


def _deposit_of(session: Session, patient_id: int, now: datetime) -> DepositStatus:
    return deposit_status(repo.penalty_events(session, patient_id, now), now)


def _place(
    session: Session,
    doctor: Doctor,
    patient: Patient,
    start_at: datetime,
    reason: str,
    deposit_confirmed: bool,
    deposit: DepositStatus,
    now: datetime,
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
    return appointment


class BookingService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def book(self, command: BookCommand, now: datetime) -> AppointmentView:
        def work(session: Session) -> AppointmentView:
            doctor = repo.get_doctor(session, command.doctor_id, lock=True)
            patient = repo.get_patient(session, command.patient_id, lock=True)
            deposit = _deposit_of(session, patient.id, now)
            appointment = _place(
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

    def cancel(self, appointment_id: int, cancelled_by: CancelledBy, now: datetime) -> CancelResult:
        def work(session: Session) -> CancelResult:
            appointment = repo.get_appointment(session, appointment_id, lock=True)
            check_can_cancel(Status(appointment.status))
            outcome = classify_cancellation(appointment.start_at, now, cancelled_by)
            appointment.status = outcome.value
            appointment.cancelled_at = now
            appointment.cancelled_by = cancelled_by.value
            appointment.status_changed_at = now
            session.flush()
            return CancelResult(
                appointment=view_of(session, appointment.id, now),
                late=outcome is Status.LATE_CANCELLED,
                deposit=_deposit_of(session, appointment.patient_id, now),
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
            deposit = _deposit_of(session, patient.id, now)
            confirmed = old.deposit_confirmed if deposit_confirmed is None else deposit_confirmed

            outcome = classify_cancellation(old.start_at, now, CancelledBy.PATIENT)
            old.status = outcome.value
            old.cancelled_at = now
            old.cancelled_by = CancelledBy.PATIENT.value
            old.status_changed_at = now
            session.flush()

            new = _place(
                session,
                doctors[target_doctor_id],
                patient,
                start_at,
                old.reason,
                confirmed,
                deposit,
                now,
            )
            old.rescheduled_to_id = new.id
            session.flush()
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
            return view_of(session, appointment.id, now)

        return run(self._factory, work)
