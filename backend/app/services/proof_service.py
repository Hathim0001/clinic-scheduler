"""Run the booking rules against the real services and database, and leave nothing behind.

Every scenario here is a rule a reviewer might doubt (the exact 2-hour boundary, the 60-day limit,
the deposit flag expiring, a failed move leaving the old appointment alone). They run through the
same services and the same PostgreSQL constraints as a real request. The only difference is the
connection: one outer transaction is opened, the services' own transactions become savepoints inside
it (`join_transaction_mode="create_savepoint"`), and the outer transaction is rolled back at the
end, so no doctor, patient or appointment is ever committed. The clinic's real data is never read
or changed, because the scenarios create their own doctors and patients inside the transaction.

Time is fixed (`NOW`), so the answers do not depend on the day the proof is run. The standard rules
are used whatever the clinic has set, so the proof keeps testing the documented behaviour.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import DomainError
from app.domain.model import CancelledBy
from app.domain.timeutil import IST
from app.persistence import repositories as repo
from app.persistence.models import Doctor, Patient, WeeklyWindowRow
from app.services.booking_service import BookingService
from app.services.patient_service import PatientService
from app.services.views import AppointmentView, BookCommand

NOW = datetime(2026, 11, 2, 8, 0, tzinfo=IST)  # a Monday, 08:00 in India
WORK_START, WORK_END = 9 * 60, 13 * 60  # Monday to Friday, 09:00 to 13:00


def at(day: int, hour: int, minute: int = 0, *, month: int = 11, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=IST)


@dataclass(frozen=True, slots=True)
class ProofCase:
    id: str
    rule: str  # the rule being checked, in the clinic's words
    scenario: str  # what the scenario does
    expected: str
    observed: str
    passed: bool


@dataclass(frozen=True, slots=True)
class ProofReport:
    cases: list[ProofCase]
    rows_before: int  # appointments, patients and doctors that existed before the run
    rows_after: int  # and after it: the two numbers must match

    @property
    def passed(self) -> bool:
        return self.rows_before == self.rows_after and all(c.passed for c in self.cases)


class Lab:
    """The throwaway clinic the scenarios run in: two doctors, three patients."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.booking = BookingService(factory)
        self.patients = PatientService(factory)
        self.factory = factory
        with factory() as session, session.begin():
            self.a = self._doctor(session, "Proof Doctor A", cap=3)
            self.b = self._doctor(session, "Proof Doctor B", cap=10)
            self.p1, self.p2, self.p3 = (self._patient(session, n) for n in (1, 2, 3))

    @staticmethod
    def _doctor(session: Session, name: str, cap: int) -> int:
        doctor = Doctor(name=name, speciality="General", slot_length_min=30, daily_cap=cap)
        session.add(doctor)
        session.flush()
        for weekday in range(5):
            session.add(
                WeeklyWindowRow(
                    doctor_id=doctor.id, weekday=weekday, start_min=WORK_START, end_min=WORK_END
                )
            )
        session.flush()
        return doctor.id

    @staticmethod
    def _patient(session: Session, n: int) -> int:
        patient = Patient(
            name=f"Proof Patient {n}", phone=f"+9190009900{n:02d}", date_of_birth=date(1990, 1, n)
        )
        session.add(patient)
        session.flush()
        return patient.id

    def book(
        self,
        patient: int,
        start: datetime,
        *,
        doctor: int | None = None,
        slots: int = 1,
        confirmed: bool = False,
        now: datetime = NOW,
    ) -> AppointmentView:
        command = BookCommand(
            doctor if doctor is not None else self.a,
            patient,
            start,
            "Proof",
            confirmed,
            slots,
        )
        return self.booking.book(command, now)

    def status_of(self, appointment_id: int) -> str:
        with self.factory() as session:
            return str(repo.get_appointment(session, appointment_id).status)


def outcome(action: Callable[[], object]) -> str:
    """BOOKED-style words for success, or the error code the rules gave."""
    try:
        action()
    except DomainError as error:
        return str(error.code.value)
    return "ACCEPTED"


def _cancel_boundary(lab: Lab) -> tuple[str, str]:
    on_time = lab.book(lab.p1, at(3, 10))
    late = lab.book(lab.p1, at(3, 10, 30))
    first = lab.booking.cancel(on_time.id, CancelledBy.PATIENT, at(3, 8)).appointment.status
    second = lab.booking.cancel(late.id, CancelledBy.PATIENT, at(3, 8, 31)).appointment.status
    return "10:00 cancelled at 08:00 -> CANCELLED; 10:30 cancelled at 08:31 -> LATE_CANCELLED", (
        f"10:00 cancelled at 08:00 -> {first}; 10:30 cancelled at 08:31 -> {second}"
    )


def _clinic_cancel(lab: Lab) -> tuple[str, str]:
    booked = lab.book(lab.p2, at(4, 10))
    result = lab.booking.cancel(booked.id, CancelledBy.CLINIC, at(4, 9, 59))
    return "CANCELLED", str(result.appointment.status)


def _double_booking(lab: Lab) -> tuple[str, str]:
    lab.book(lab.p1, at(5, 10))
    return "SLOT_TAKEN", outcome(lambda: lab.book(lab.p2, at(5, 10)))


def _patient_overlap(lab: Lab) -> tuple[str, str]:
    lab.book(lab.p3, at(5, 11))
    return "PATIENT_OVERLAP", outcome(lambda: lab.book(lab.p3, at(5, 11), doctor=lab.b))


def _daily_cap(lab: Lab) -> tuple[str, str]:
    for minute in (0, 30):
        lab.book(lab.p1, at(6, 9, minute))
    lab.book(lab.p1, at(6, 10))
    return "DAILY_CAP_REACHED", outcome(lambda: lab.book(lab.p2, at(6, 10, 30)))


def _off_grid(lab: Lab) -> tuple[str, str]:
    return "OFF_GRID", outcome(lambda: lab.book(lab.p1, at(9, 10, 10)))


def _outside_hours(lab: Lab) -> tuple[str, str]:
    return "OUTSIDE_AVAILABILITY", outcome(lambda: lab.book(lab.p1, at(9, 14)))


def _starting_now(lab: Lab) -> tuple[str, str]:
    return "BOOKING_IN_PAST", outcome(lambda: lab.book(lab.p1, NOW))


def _sixty_days(lab: Lab) -> tuple[str, str]:
    day_60 = outcome(lambda: lab.book(lab.p3, at(1, 10, month=1, year=2027)))
    day_61 = outcome(lambda: lab.book(lab.p3, at(2, 10, month=1, year=2027)))
    return (
        "day 60 -> ACCEPTED; day 61 -> BOOKING_TOO_FAR",
        f"day 60 -> {day_60}; day 61 -> {day_61}",
    )


def _two_strikes(lab: Lab) -> tuple[str, str]:
    for hour in (11, 12):
        booked = lab.book(lab.p2, at(9, hour), doctor=lab.b)
        lab.booking.no_show(booked.id, at(9, 13))
    later = at(10, 8)
    refused = outcome(lambda: lab.book(lab.p2, at(11, 10), doctor=lab.b, now=later))
    allowed = outcome(lambda: lab.book(lab.p2, at(11, 10), doctor=lab.b, confirmed=True, now=later))
    return (
        "without a deposit -> DEPOSIT_REQUIRED; with it -> ACCEPTED",
        f"without a deposit -> {refused}; with it -> {allowed}",
    )


def _strike_expiry(lab: Lab) -> tuple[str, str]:
    # Reuses the two no-shows by `_two_strikes`. A no-show counts from the appointment's start, and
    # the flag lasts until the older of the two strikes (11:00) is 30 days old.
    expiry = at(9, 11) + timedelta(days=30)
    on = lab.patients.get(lab.p2, expiry).deposit
    after = lab.patients.get(lab.p2, expiry + timedelta(seconds=1)).deposit
    return (
        "flagged at day 30: True; one second later: False",
        f"flagged at day 30: {on.required if on else None}; "
        f"one second later: {after.required if after else None}",
    )


def _failed_move_changes_nothing(lab: Lab) -> tuple[str, str]:
    lab.book(lab.p3, at(10, 10))
    mine = lab.book(lab.p1, at(10, 11))
    refused = outcome(lambda: lab.booking.reschedule(mine.id, at(10, 10), None, None, NOW))
    return (
        "SLOT_TAKEN, and the original is still BOOKED",
        f"{refused}, and the original is still {lab.status_of(mine.id)}",
    )


def _late_move_asks_first(lab: Lab) -> tuple[str, str]:
    booked = lab.book(lab.p1, at(11, 10))
    now = at(11, 9)
    asked = outcome(lambda: lab.booking.reschedule(booked.id, at(11, 11), None, None, now))
    kept = lab.status_of(booked.id)
    moved = lab.booking.reschedule(booked.id, at(11, 11), None, None, now, by=CancelledBy.CLINIC)
    return (
        "patient: LATE_RESCHEDULE_NEEDS_CONFIRMATION, original BOOKED; "
        "clinic: moved, old CANCELLED",
        f"patient: {asked}, original {kept}; clinic: moved, old {moved.old.status}",
    )


def _long_visit(lab: Lab) -> tuple[str, str]:
    lab.book(lab.p1, at(12, 10), doctor=lab.b, slots=2)  # 10:00 to 11:00
    overlapping = outcome(lambda: lab.book(lab.p2, at(12, 10, 30), doctor=lab.b))
    next_free = outcome(lambda: lab.book(lab.p2, at(12, 11), doctor=lab.b))
    return (
        "10:30 -> SLOT_TAKEN; 11:00 -> ACCEPTED",
        f"10:30 -> {overlapping}; 11:00 -> {next_free}",
    )


def _retry_same_key(lab: Lab) -> tuple[str, str]:
    command = BookCommand(lab.b, lab.p3, at(13, 10), "Proof")
    first, first_replay = lab.booking.book_idempotent(command, "proof-key-1", NOW)
    second, second_replay = lab.booking.book_idempotent(command, "proof-key-1", NOW)
    return (
        "the same appointment both times, replay flags False/True",
        f"{'the same' if first.id == second.id else 'different'} appointment both times, "
        f"replay flags {first_replay}/{second_replay}",
    )


def _one_phone_one_patient(lab: Lab) -> tuple[str, str]:
    return "PHONE_TAKEN", outcome(
        lambda: lab.patients.create("Someone Else", "9000990001", date(2000, 1, 1), NOW)
    )


def _cancel_twice(lab: Lab) -> tuple[str, str]:
    booked = lab.book(lab.p2, at(16, 10))
    lab.booking.cancel(booked.id, CancelledBy.PATIENT, NOW)
    return "INVALID_TRANSITION", outcome(
        lambda: lab.booking.cancel(booked.id, CancelledBy.PATIENT, NOW)
    )


CASES: tuple[tuple[str, str, str, Callable[[Lab], tuple[str, str]]], ...] = (
    (
        "cancel-boundary",
        "Cancelling 2 hours or more ahead is free; inside 2 hours is a late cancel",
        "Cancel one appointment exactly 2 hours before, another 2 hours less 1 minute before",
        _cancel_boundary,
    ),
    (
        "clinic-cancel",
        "A cancellation by the clinic is never a late cancel",
        "The clinic cancels an appointment 1 minute before it starts",
        _clinic_cancel,
    ),
    (
        "double-booking",
        "A doctor's slot holds one appointment",
        "Two patients book the same doctor and time",
        _double_booking,
    ),
    (
        "patient-overlap",
        "A patient cannot be in two places at once",
        "One patient books the same time with two doctors",
        _patient_overlap,
    ),
    (
        "daily-cap",
        "A doctor sees at most their daily cap of patients",
        "A cap of 3 and a fourth booking on the same day",
        _daily_cap,
    ),
    (
        "off-grid",
        "Appointments start on the doctor's slot grid",
        "Book at 10:10 with 30-minute slots",
        _off_grid,
    ),
    (
        "outside-hours",
        "Appointments fall inside the doctor's hours",
        "Book at 14:00 for a doctor working 09:00 to 13:00",
        _outside_hours,
    ),
    (
        "starting-now",
        "An appointment cannot be in the past (starting now is past)",
        "Book a start equal to the current time",
        _starting_now,
    ),
    (
        "sixty-days",
        "Bookings open up to 60 days ahead, by India calendar date",
        "Book on day 60 and on day 61",
        _sixty_days,
    ),
    (
        "two-strikes",
        "Two no-shows or late cancels in 30 days require a deposit acknowledgement",
        "Two no-shows, then a booking with and without the deposit acknowledged",
        _two_strikes,
    ),
    (
        "strike-expiry",
        "The deposit flag ends when the second strike is 30 days old",
        "Ask for the flag at exactly 30 days, and one second later",
        _strike_expiry,
    ),
    (
        "atomic-move",
        "A rescheduling that cannot happen leaves the old appointment alone",
        "Move an appointment onto a taken slot",
        _failed_move_changes_nothing,
    ),
    (
        "late-move",
        "A patient is asked before a late move is recorded; the clinic's move is free",
        "Move an appointment 1 hour before it starts, as the patient and as the clinic",
        _late_move_asks_first,
    ),
    (
        "long-visit",
        "A visit of two slots blocks both of them",
        "Book 10:00 to 11:00, then try 10:30 and 11:00",
        _long_visit,
    ),
    (
        "same-key",
        "Retrying a booking with the same key does not book twice",
        "Send one request twice with one Idempotency-Key",
        _retry_same_key,
    ),
    (
        "one-phone",
        "A phone number belongs to one patient",
        "Register a second patient on a number already in use",
        _one_phone_one_patient,
    ),
    (
        "cancel-twice",
        "A cancelled appointment cannot be cancelled again",
        "Cancel the same appointment twice",
        _cancel_twice,
    ),
)


def _count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return repo.count_rows(session)


def run_proof(engine: Engine) -> ProofReport:
    """Run every scenario inside one transaction that is always rolled back."""
    plain = sessionmaker(engine, expire_on_commit=False)
    before = _count(plain)
    connection = engine.connect()
    outer = connection.begin()
    try:
        # The scenarios assert the documented numbers (2 hours, 60 days, 2 strikes in 30 days). The
        # clinic may have changed its own rules, so inside this transaction, and only here, the
        # stored rules are removed and the standard ones apply; the rollback brings them back.
        connection.execute(text("DELETE FROM clinic_policy"))
        factory = sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        lab = Lab(factory)
        cases: list[ProofCase] = []
        for case_id, rule, scenario, run in CASES:
            try:
                expected, observed = run(lab)
            except Exception as error:  # a broken scenario is a failed case, not a failed page
                expected, observed = "no error", f"{type(error).__name__}: {error}"[:200]
            cases.append(
                ProofCase(case_id, rule, scenario, expected, observed, expected == observed)
            )
    finally:
        outer.rollback()
        connection.close()
    return ProofReport(cases, before, _count(plain))
