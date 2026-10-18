"""Records about appointments: the audit trail, a patient's full export, and the summary report.

The history is written by the booking service in the same transaction as each change, so it can
neither miss a committed change nor describe a rolled-back one. Nothing here changes data.

Report definitions (the same words appear in the README, because two people counting "no-shows"
differently is its own scenario):

- *new bookings*: appointments that were not created by a reschedule, so moving an appointment is
  not counted as a new booking;
- *rescheduled*: appointments cancelled only because they were moved; these are not counted as
  cancellations, whether the move was late or not;
- *no-show rate*: no-shows divided by completed plus no-shows (appointments whose outcome is known);
- *freed slots*: appointments cancelled (in time or late) and not merely moved; *refilled*: those
  whose time was later taken by another appointment of the same doctor that is still active, and
  *via the waitlist* when that appointment came from accepting a waitlist offer. *Recovery rate* is
  refilled divided by freed, so it shows what the waitlist is worth in real appointments;
- *utilisation*: appointments that took a slot (booked, completed or no-show) divided by the slots
  the doctor's hours offered in the period, so leave days and special hours are taken into account.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ErrorCode, RuleViolation
from app.domain.model import ACTIVE_STATUSES, Status
from app.domain.slots import candidate_starts
from app.domain.timeutil import at_ist
from app.persistence import repositories as repo
from app.persistence.models import Appointment, AppointmentEvent, Doctor
from app.services.appointment_views import build_views
from app.services.support import run
from app.services.views import AppointmentView, EventView, PatientView

MAX_REPORT_DAYS = 92


@dataclass(frozen=True, slots=True)
class DoctorReport:
    doctor_id: int
    doctor_name: str
    capacity_slots: int
    appointments: int  # everything starting in the period, whatever its status
    new_bookings: int
    booked: int
    completed: int
    no_show: int
    cancelled: int
    late_cancelled: int
    rescheduled: int
    checked_in: int
    utilisation: float | None  # None when the doctor offered no slots in the period
    no_show_rate: float | None  # None when no outcome is known yet
    freed_slots: int = 0
    refilled: int = 0
    refilled_via_waitlist: int = 0
    recovery_rate: float | None = None  # None when nothing was freed


@dataclass(frozen=True, slots=True)
class ReportView:
    start: date
    end: date
    doctors: tuple[DoctorReport, ...]
    total: DoctorReport


@dataclass(frozen=True, slots=True)
class PatientExport:
    patient: PatientView
    appointments: tuple[AppointmentView, ...]
    events: tuple[EventView, ...]


def _event_view(row: AppointmentEvent) -> EventView:
    return EventView(
        row.id, row.appointment_id, row.patient_id, row.kind, row.at, dict(row.detail), row.actor
    )


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _recovery(
    rows: list[Appointment], booked: dict[int, tuple[str, datetime]]
) -> tuple[int, int, int]:
    """(freed, refilled, refilled via the waitlist) for the cancellations among `rows`."""
    freed = [
        a
        for a in rows
        if a.status in (Status.CANCELLED.value, Status.LATE_CANCELLED.value)
        and a.rescheduled_to_id is None
        and a.cancelled_at is not None
    ]
    refilled = via = 0
    for gone in freed:
        takers = [
            o
            for o in rows
            if o.doctor_id == gone.doctor_id
            and Status(o.status) in ACTIVE_STATUSES
            and o.start_at < gone.end_at
            and gone.start_at < o.end_at
            and o.id in booked
            and gone.cancelled_at is not None
            and booked[o.id][1] >= gone.cancelled_at
        ]
        refilled += bool(takers)
        via += any(booked[o.id][0] == "WAITLIST" for o in takers)
    return len(freed), refilled, via


def _doctor_report(
    doctor_id: int,
    name: str,
    capacity: int,
    rows: list[Appointment],
    moved_to: set[int],
    booked: dict[int, tuple[str, datetime]],
) -> DoctorReport:
    def count(status: Status, *, moved: bool = False) -> int:
        return sum(
            1
            for a in rows
            if a.status == status.value and (a.rescheduled_to_id is not None) is moved
        )

    completed, no_show = count(Status.COMPLETED), count(Status.NO_SHOW)
    taking_a_slot = sum(a.slots for a in rows if Status(a.status) in ACTIVE_STATUSES)
    freed, refilled, via = _recovery(rows, booked)
    return DoctorReport(
        doctor_id=doctor_id,
        doctor_name=name,
        capacity_slots=capacity,
        appointments=len(rows),
        new_bookings=sum(1 for a in rows if a.id not in moved_to),
        booked=count(Status.BOOKED),
        completed=completed,
        no_show=no_show,
        cancelled=count(Status.CANCELLED),
        late_cancelled=count(Status.LATE_CANCELLED),
        rescheduled=sum(1 for a in rows if a.rescheduled_to_id is not None),
        checked_in=sum(1 for a in rows if a.checked_in_at is not None),
        utilisation=_ratio(taking_a_slot, capacity),
        no_show_rate=_ratio(no_show, completed + no_show),
        freed_slots=freed,
        refilled=refilled,
        refilled_via_waitlist=via,
        recovery_rate=_ratio(refilled, freed),
    )


class RecordService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def history(self, appointment_id: int) -> list[EventView]:
        """Everything that happened to one appointment, oldest first."""

        def work(session: Session) -> list[EventView]:
            repo.get_appointment(session, appointment_id)
            return [_event_view(e) for e in repo.events_for_appointment(session, appointment_id)]

        return run(self._factory, work)

    def patient_export(self, patient_id: int, patient: PatientView, now: datetime) -> PatientExport:
        """The patient's details, every appointment they have had and its history."""

        def work(session: Session) -> PatientExport:
            repo.get_patient(session, patient_id)
            rows = repo.find_appointments(session, repo.AppointmentFilter(patient_id=patient_id))
            return PatientExport(
                patient,
                tuple(build_views(session, rows, now)),
                tuple(_event_view(e) for e in repo.events_for_patient(session, patient_id)),
            )

        return run(self._factory, work)

    def summary(self, start: date, end: date) -> ReportView:
        """Counts per doctor for appointments starting on India dates `start` to `end`."""
        if end < start:
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR, "The end date is before the start date.", field="to"
            )
        if (end - start).days + 1 > MAX_REPORT_DAYS:
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR,
                f"A report covers at most {MAX_REPORT_DAYS} days.",
                field="to",
            )

        def work(session: Session) -> ReportView:
            first, after = at_ist(start, 0), at_ist(end + timedelta(days=1), 0)
            rows = list(
                session.scalars(
                    select(Appointment).where(
                        Appointment.start_at >= first, Appointment.start_at < after
                    )
                )
            )
            moved_to = {a.rescheduled_to_id for a in rows if a.rescheduled_to_id is not None}
            booked = repo.booked_events(session, [a.id for a in rows])
            lookup = repo.WindowsLookup(session)
            days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
            reports = []
            for doctor in session.scalars(select(Doctor).order_by(Doctor.id)):
                capacity = sum(
                    len(
                        list(
                            candidate_starts(
                                day, lookup.windows(doctor.id, day), doctor.slot_length_min
                            )
                        )
                    )
                    for day in days
                )
                mine = [a for a in rows if a.doctor_id == doctor.id]
                reports.append(
                    _doctor_report(doctor.id, doctor.name, capacity, mine, moved_to, booked)
                )
            total = _doctor_report(
                0,
                "All doctors",
                sum(r.capacity_slots for r in reports),
                rows,
                moved_to,
                booked,
            )
            return ReportView(start, end, tuple(reports), total)

        return run(self._factory, work)
