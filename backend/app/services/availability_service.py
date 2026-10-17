"""Doctor availability: what a day looks like to patients and receptionists, and the changes doctors
make to their weekly hours and to single dates.

Reads (free slots, day schedule) are built on `first_violation`, the same predicate booking uses, so
what is offered can always be booked.

Changes lock the doctor row, which is also the first lock a booking takes. A booking and a change to
the doctor's hours therefore run one after the other, never interleaved: either the booking commits
first and the change sees it as a conflict, or the change commits first and the booking is told the
doctor is not available. No appointment is orphaned without notice (plan 21.4, T-O05).

A change that would leave future BOOKED appointments outside the new hours is refused with
AVAILABILITY_CONFLICTS and the list of appointments, unless the caller resubmits with
`acknowledge_conflicts`. Then it is saved, the appointments stay BOOKED, and they show up as
"needs attention" until someone moves or cancels them (A-12, A-36).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.domain.availability import fits_in_windows, resolve_windows, validate_windows
from app.domain.errors import ConflictError, ErrorCode, RuleViolation
from app.domain.model import ACTIVE_STATUSES, WeeklyWindow, Window
from app.domain.slots import (
    candidate_starts,
    conflicting_appointment,
    first_violation,
    unavailable_reason,
)
from app.domain.timeutil import ist_date, ist_iso
from app.persistence import repositories as repo
from app.persistence.models import (
    Appointment,
    Doctor,
    OverrideRow,
    OverrideWindowRow,
    WeeklyWindowRow,
)
from app.services.appointment_views import build_views
from app.services.support import run
from app.services.views import (
    AppointmentView,
    OverrideChange,
    OverrideView,
    ScheduleSlot,
    ScheduleView,
    SlotState,
    SlotsView,
    WeeklyView,
)

# How a slot that cannot be booked shows up in the day schedule. SLOT_TAKEN is handled before this
# table (a slot with an appointment is BOOKED); OFF_GRID and OUTSIDE_AVAILABILITY cannot happen to
# a grid start inside the windows.
_STATE_OF_VIOLATION = {
    None: SlotState.FREE,
    ErrorCode.BOOKING_IN_PAST: SlotState.PAST,
    ErrorCode.DAILY_CAP_REACHED: SlotState.CAPPED,
    ErrorCode.BOOKING_TOO_FAR: SlotState.CLOSED,
    ErrorCode.DOCTOR_NOT_ACCEPTING: SlotState.CLOSED,
    ErrorCode.PATIENT_OVERLAP: SlotState.BUSY,
}


@dataclass(frozen=True, slots=True)
class Proposal:
    """A change to the doctor's hours, checked against future bookings before it is saved."""

    weekly: Sequence[WeeklyWindow] | None = None  # a replacement weekly pattern
    day: date | None = None  # a date whose override changes ...
    day_override: Sequence[Window] | None = None  # ... to these windows (None: no override)


def _windows_after(
    lookup: repo.WindowsLookup, doctor_id: int, proposal: Proposal, day: date
) -> tuple[Window, ...]:
    weekly = proposal.weekly if proposal.weekly is not None else lookup.weekly(doctor_id)
    override = proposal.day_override if day == proposal.day else lookup.override(doctor_id, day)
    return resolve_windows(day, weekly, override)[0]


def _newly_orphaned(
    session: Session, doctor: Doctor, now: datetime, proposal: Proposal
) -> list[Appointment]:
    """Future BOOKED appointments that fit the doctor's hours now but would not after the change."""
    lookup = repo.WindowsLookup(session)
    orphans = []
    for appt in repo.future_booked(session, doctor.id, now):
        day = ist_date(appt.start_at)
        if proposal.weekly is None and day != proposal.day:
            continue  # a change to one date cannot affect another
        fits_now = fits_in_windows(appt.start_at, appt.end_at, lookup.windows(doctor.id, day))
        after = _windows_after(lookup, doctor.id, proposal, day)
        if fits_now and not fits_in_windows(appt.start_at, appt.end_at, after):
            orphans.append(appt)
    return orphans


def _conflict_error(
    session: Session, doctor: Doctor, orphans: Sequence[Appointment], day: date | None
) -> ConflictError:
    rows = repo.appointment_rows_by_id(session, [a.id for a in orphans])
    noun = "appointment" if len(rows) == 1 else "appointments"
    where = f" on {day.isoformat()}" if day is not None else ""
    return ConflictError(
        ErrorCode.AVAILABILITY_CONFLICTS,
        f"{len(rows)} future {noun} would fall outside {doctor.name}'s availability{where}. "
        "Resubmit with acknowledge_conflicts=true to save anyway.",
        doctor_id=doctor.id,
        date=day.isoformat() if day is not None else None,
        appointments=[
            {
                "id": row.appointment.id,
                "patient_name": row.patient_name,
                "patient_phone": row.patient_phone,
                "start_at_ist": ist_iso(row.appointment.start_at),
            }
            for row in rows
        ],
    )


def _views_of(
    session: Session, rows: Sequence[Appointment], now: datetime
) -> list[AppointmentView]:
    return build_views(session, repo.appointment_rows_by_id(session, [a.id for a in rows]), now)


def _validate_weekly(windows: Sequence[WeeklyWindow], slot_length_min: int) -> None:
    by_weekday: dict[int, list[Window]] = {}
    for window in windows:
        if not 0 <= window.weekday <= 6:
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR,
                "A weekday must be between 0 (Monday) and 6 (Sunday).",
                weekday=window.weekday,
            )
        by_weekday.setdefault(window.weekday, []).append(Window(window.start_min, window.end_min))
    for weekday in sorted(by_weekday):
        validate_windows(by_weekday[weekday], slot_length_min)


class AvailabilityService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    # ------------------------------------------------------------------------------ reads

    def weekly_windows(self, doctor_id: int) -> tuple[WeeklyWindow, ...]:
        def work(session: Session) -> tuple[WeeklyWindow, ...]:
            repo.get_doctor(session, doctor_id)
            return tuple(repo.weekly_windows(session, doctor_id))

        return run(self._factory, work)

    def overrides(self, doctor_id: int, first: date, last: date) -> list[OverrideView]:
        def work(session: Session) -> list[OverrideView]:
            repo.get_doctor(session, doctor_id)
            return [
                OverrideView(
                    row.on_date,
                    row.note,
                    tuple(Window(w.start_min, w.end_min) for w in row.windows),
                )
                for row in repo.overrides_between(session, doctor_id, first, last)
            ]

        return run(self._factory, work)

    def free_slots(
        self, doctor_id: int, day: date, patient_id: int | None, now: datetime
    ) -> SlotsView:
        """The starts on `day` that booking would accept, and why there are none when empty."""

        def work(session: Session) -> SlotsView:
            doctor = repo.get_doctor(session, doctor_id)
            if patient_id is not None:
                repo.get_patient(session, patient_id)
            windows, source = repo.effective_windows(session, doctor.id, day)
            context = repo.slot_context(session, doctor, patient_id, day, now, windows)
            starts = list(candidate_starts(day, windows, doctor.slot_length_min))
            violations = [first_violation(start, context) for start in starts]
            return SlotsView(
                doctor_id=doctor.id,
                day=day,
                slot_length_min=doctor.slot_length_min,
                source=source,
                windows=windows,
                slots=tuple(s for s, v in zip(starts, violations, strict=True) if v is None),
                unavailable_reason=unavailable_reason(violations),
            )

        return run(self._factory, work)

    def day_schedule(
        self, doctor_id: int, day: date, patient_id: int | None, now: datetime
    ) -> ScheduleView:
        """Every grid position of `day` with its state, plus bookings outside the doctor's hours."""

        def work(session: Session) -> ScheduleView:
            doctor = repo.get_doctor(session, doctor_id)
            if patient_id is not None:
                repo.get_patient(session, patient_id)
            windows, source = repo.effective_windows(session, doctor.id, day)
            context = repo.slot_context(session, doctor, patient_id, day, now, windows)
            starts = list(candidate_starts(day, windows, doctor.slot_length_min))
            violations = [first_violation(start, context) for start in starts]
            occupants = {start: conflicting_appointment(start, context) for start in starts}
            outside = [
                a
                for a in context.doctor_appts
                if a.status in ACTIVE_STATUSES
                and ist_date(a.start_at) == day
                and not fits_in_windows(a.start_at, a.end_at, windows)
            ]
            wanted = sorted({o.id for o in occupants.values() if o is not None})
            wanted += [a.id for a in outside if a.id not in wanted]
            views = {
                view.id: view
                for view in build_views(session, repo.appointment_rows_by_id(session, wanted), now)
            }
            length = timedelta(minutes=doctor.slot_length_min)
            slots = []
            for start, violation in zip(starts, violations, strict=True):
                occupant = occupants[start]
                if occupant is not None:
                    slots.append(
                        ScheduleSlot(start, start + length, SlotState.BOOKED, views[occupant.id])
                    )
                else:
                    state = _STATE_OF_VIOLATION[violation]
                    slots.append(ScheduleSlot(start, start + length, state))
            return ScheduleView(
                doctor_id=doctor.id,
                day=day,
                slot_length_min=doctor.slot_length_min,
                source=source,
                windows=windows,
                slots=tuple(slots),
                outside_availability=tuple(views[a.id] for a in outside),
                unavailable_reason=unavailable_reason(violations),
            )

        return run(self._factory, work)

    # --------------------------------------------------------------------------- changes

    def replace_weekly_windows(
        self,
        doctor_id: int,
        windows: Sequence[WeeklyWindow],
        acknowledge_conflicts: bool,
        now: datetime,
    ) -> WeeklyView:
        def work(session: Session) -> WeeklyView:
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            _validate_weekly(windows, doctor.slot_length_min)
            orphans = _newly_orphaned(session, doctor, now, Proposal(weekly=windows))
            if orphans and not acknowledge_conflicts:
                raise _conflict_error(session, doctor, orphans, None)
            session.execute(delete(WeeklyWindowRow).where(WeeklyWindowRow.doctor_id == doctor.id))
            ordered = sorted(windows, key=lambda w: (w.weekday, w.start_min))
            session.add_all(
                WeeklyWindowRow(
                    doctor_id=doctor.id, weekday=w.weekday, start_min=w.start_min, end_min=w.end_min
                )
                for w in ordered
            )
            session.flush()
            return WeeklyView(tuple(ordered), tuple(_views_of(session, orphans, now)))

        return run(self._factory, work)

    def put_override(
        self,
        doctor_id: int,
        day: date,
        windows: Sequence[Window],
        note: str | None,
        acknowledge_conflicts: bool,
        now: datetime,
    ) -> OverrideChange:
        """Create or replace the override for one date. No windows at all means leave."""

        def work(session: Session) -> OverrideChange:
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            validate_windows(windows, doctor.slot_length_min)
            orphans = _newly_orphaned(session, doctor, now, Proposal(day=day, day_override=windows))
            if orphans and not acknowledge_conflicts:
                raise _conflict_error(session, doctor, orphans, day)
            existing = repo.override_row(session, doctor.id, day)
            if existing is not None:
                # Delete before inserting: the new windows may overlap the ones being replaced.
                session.delete(existing)
                session.flush()
            ordered = tuple(sorted(windows, key=lambda w: (w.start_min, w.end_min)))
            row = OverrideRow(doctor_id=doctor.id, on_date=day, note=note)
            row.windows = [
                OverrideWindowRow(start_min=w.start_min, end_min=w.end_min) for w in ordered
            ]
            session.add(row)
            session.flush()
            return OverrideChange(day, note, ordered, tuple(_views_of(session, orphans, now)))

        return run(self._factory, work)

    def delete_override(
        self, doctor_id: int, day: date, acknowledge_conflicts: bool, now: datetime
    ) -> OverrideChange:
        """Revert one date to the weekly pattern (a no-op when there is no override)."""

        def work(session: Session) -> OverrideChange:
            doctor = repo.get_doctor(session, doctor_id, lock=True)
            orphans = _newly_orphaned(session, doctor, now, Proposal(day=day, day_override=None))
            if orphans and not acknowledge_conflicts:
                raise _conflict_error(session, doctor, orphans, day)
            existing = repo.override_row(session, doctor.id, day)
            if existing is not None:
                session.delete(existing)
                session.flush()
            return OverrideChange(day, None, (), tuple(_views_of(session, orphans, now)))

        return run(self._factory, work)
