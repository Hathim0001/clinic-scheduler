"""Seed data for reviewers (plan section 24.1).

Two doctors, fifteen invented patients and a set of scripted scenarios, all placed relative to an
anchor date A so they can be reproduced on any date. `next_weekday(A, wd)` is the first date
strictly after A with that weekday (Monday is 0). Every name and phone number is invented.

The seed writes rows directly instead of going through the booking service: it needs history (a
completed visit last week, a no-show) that the booking rules would refuse to create today.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.domain.model import Status
from app.domain.penalties import LOOKBACK
from app.domain.timeutil import IST, at_ist
from app.persistence import repositories as repo
from app.persistence.models import (
    AppMeta,
    Appointment,
    Doctor,
    OverrideRow,
    OverrideWindowRow,
    Patient,
    WeeklyWindowRow,
)

MON, TUE, WED, FRI, SAT = 0, 1, 2, 4, 5

DATA_TABLES = (
    "notifications, idempotency_keys, appointment_events, waitlist_entries, appointments, "
    "override_windows, "
    "availability_overrides, weekly_windows, patients, doctors, app_meta"
)

# (name, date of birth). Patient n has id n and phone +9190000000nn on a fresh database.
PATIENTS: list[tuple[str, date]] = [
    ("Kavita Nair", date(1988, 4, 12)),  # 1  flagged: a no-show and a late cancel
    ("Rohan Gupta", date(1995, 9, 3)),  # 2  one strike only
    ("Sneha Pillai", date(2001, 1, 22)),  # 3  flag that is about to expire
    ("Arjun Mehta", date(1979, 6, 30)),  # 4  booked with Dr. Rao, for the overlap demo
    ("Meera Iyer", date(1965, 11, 8)),  # 5
    ("Neha Joshi", date(1990, 2, 17)),  # 6
    ("Aditi Das", date(1984, 7, 25)),  # 7
    ("Imran Sheikh", date(1972, 12, 1)),  # 8
    ("Priya Kulkarni", date(2016, 5, 9)),  # 9   children from here on, for the paediatrician
    ("Rahul Verma", date(2019, 8, 14)),  # 10
    ("Divya Reddy", date(2014, 3, 27)),  # 11
    ("Karthik Subramanian", date(2021, 10, 5)),  # 12
    ("Farhan Qureshi", date(2018, 1, 19)),  # 13
    ("Lakshmi Narayanan", date(2015, 6, 2)),  # 14
    ("Sanjay Patel", date(2020, 9, 30)),  # 15
]
REASONS = ["Fever", "Follow-up", "Routine check-up", "Cough and cold", "Vaccination", "Skin rash"]


def next_weekday(after: date, weekday: int) -> date:
    """The first date strictly after `after` that falls on `weekday`."""
    return after + timedelta(days=(weekday - after.weekday()) % 7 or 7)


def previous_workday(day: date) -> date:
    """`day` itself if it is Monday to Friday, otherwise the Friday before."""
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


@dataclass(frozen=True)
class Strike:
    day: date
    hhmm: str  # appointment start, India time
    kind: Status  # NO_SHOW or LATE_CANCELLED
    cancelled_hhmm: str | None = None  # when a late cancel was made (same day)


@dataclass(frozen=True)
class ScenarioDates:
    anchor: date
    queue_day: date
    conflict_day: date
    leave_day: date
    cap_day: date
    extra_saturday: date
    busy_monday: date
    kavita: tuple[Strike, Strike]  # flagged
    rohan: Strike  # one strike
    sneha: tuple[Strike, Strike]  # flag that expires soon


def scenario_dates(anchor: date) -> ScenarioDates:
    """Every date the scenarios use, derived from the anchor alone."""

    def strike_day(days_ago: int) -> date:
        # Doctors do not work weekends, so a strike that would fall on one moves to the Friday.
        return previous_workday(anchor - timedelta(days=days_ago))

    return ScenarioDates(
        anchor=anchor,
        queue_day=anchor if anchor.weekday() < 5 else next_weekday(anchor, MON),
        conflict_day=next_weekday(anchor, TUE),
        leave_day=next_weekday(anchor + timedelta(days=7), WED),
        cap_day=next_weekday(anchor, FRI),
        extra_saturday=next_weekday(anchor, SAT),
        busy_monday=next_weekday(anchor, MON),
        kavita=(
            Strike(strike_day(3), "10:00", Status.NO_SHOW),
            Strike(strike_day(5), "17:15", Status.LATE_CANCELLED, "16:00"),
        ),
        rohan=Strike(strike_day(2), "11:00", Status.NO_SHOW),
        sneha=(
            Strike(strike_day(29), "09:30", Status.NO_SHOW),
            Strike(strike_day(1), "18:00", Status.LATE_CANCELLED, "16:30"),
        ),
    )


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _add_appointment(
    session: Session,
    doctor: Doctor,
    patient_number: int,
    day: date,
    hhmm: str,
    *,
    status: Status = Status.BOOKED,
    reason: str,
    cancelled_hhmm: str | None = None,
) -> Appointment:
    """One appointment, with the timestamps the database constraints require for its status."""
    start = at_ist(day, _minutes(hhmm))
    end = start + timedelta(minutes=doctor.slot_length_min)
    appointment = Appointment(
        doctor_id=doctor.id,
        patient_id=patient_number,
        start_at=start,
        end_at=end,
        status=status.value,
        reason=reason,
    )
    if status in (Status.CANCELLED, Status.LATE_CANCELLED):
        if cancelled_hhmm is None:
            raise ValueError("a cancelled appointment needs the time it was cancelled")
        appointment.cancelled_at = at_ist(day, _minutes(cancelled_hhmm))
        appointment.cancelled_by = "PATIENT"
        appointment.status_changed_at = appointment.cancelled_at
    elif status is not Status.BOOKED:
        appointment.status_changed_at = end
    session.add(appointment)
    return appointment


def _add_strike(
    session: Session, doctor: Doctor, patient_number: int, strike: Strike, reason: str
) -> None:
    _add_appointment(
        session,
        doctor,
        patient_number,
        strike.day,
        strike.hhmm,
        status=strike.kind,
        reason=reason,
        cancelled_hhmm=strike.cancelled_hhmm,
    )


def reset_database(session: Session) -> None:
    """Empty every data table and restart the id counters (the schema stays)."""
    session.execute(text(f"TRUNCATE {DATA_TABLES} RESTART IDENTITY CASCADE"))


def database_is_empty(session: Session) -> bool:
    return session.scalar(select(func.count()).select_from(Doctor)) == 0


def seed_database(session: Session, anchor: date, seeded_at: datetime) -> ScenarioDates:
    """Insert the whole seed into an empty database. The caller owns the transaction."""
    dates = scenario_dates(anchor)

    rao = Doctor(
        name="Dr. Ananya Rao", speciality="General Physician", slot_length_min=15, daily_cap=20
    )
    menon = Doctor(
        name="Dr. Vikram Menon", speciality="Paediatrics", slot_length_min=30, daily_cap=6
    )
    session.add_all([rao, menon])
    session.flush()

    for weekday in range(5):  # Rao: Monday to Friday, two windows a day
        session.add(WeeklyWindowRow(doctor_id=rao.id, weekday=weekday, start_min=540, end_min=780))
        session.add(
            WeeklyWindowRow(doctor_id=rao.id, weekday=weekday, start_min=1020, end_min=1140)
        )
    for weekday in (MON, WED, FRI):  # Menon: Monday, Wednesday, Friday; no weekly Saturday
        session.add(
            WeeklyWindowRow(doctor_id=menon.id, weekday=weekday, start_min=600, end_min=840)
        )

    for number, (name, born) in enumerate(PATIENTS, start=1):
        session.add(Patient(name=name, phone=f"+9190000000{number:02d}", date_of_birth=born))
    session.flush()

    # Extra Saturday: an override that ADDS a day Dr. Menon does not normally work.
    saturday = OverrideRow(
        doctor_id=menon.id, on_date=dates.extra_saturday, note="Extra Saturday clinic"
    )
    saturday.windows = [OverrideWindowRow(start_min=600, end_min=780)]
    session.add(saturday)

    # Strikes: Kavita is flagged, Rohan has one strike, Sneha's flag ends soon.
    for strike in dates.kavita:
        _add_strike(session, rao, 1, strike, "Follow-up")
    _add_strike(session, rao, 2, dates.rohan, "Fever")
    for strike in dates.sneha:
        _add_strike(session, rao, 3, strike, "Cough and cold")

    # Cross-doctor overlap demo: Arjun is booked with Dr. Rao at 10:00 on the next Monday.
    _add_appointment(session, rao, 4, dates.busy_monday, "10:00", reason="Routine check-up")

    # Conflict demo: three bookings and no override, so a leave override gets a 409 with a list.
    for number, hhmm in ((5, "09:15"), (6, "10:30"), (7, "11:45")):
        _add_appointment(session, rao, number, dates.conflict_day, hhmm, reason="Follow-up")

    # Existing orphan: a booking made BEFORE the leave override that now covers its day.
    _add_appointment(session, rao, 8, dates.leave_day, "09:30", reason="Routine check-up")
    leave = OverrideRow(doctor_id=rao.id, on_date=dates.leave_day, note="Conference leave")
    session.add(leave)
    session.flush()
    repo.refresh_outside_hours(session)  # the booking above now lies outside Dr. Rao's hours

    # Cap demo: Dr. Menon's cap is 6 of 8 slots, and 5 are already booked.
    for number, hhmm in ((9, "10:00"), (10, "10:30"), (11, "11:00"), (12, "11:30"), (13, "12:00")):
        _add_appointment(session, menon, number, dates.cap_day, hhmm, reason="Vaccination")

    # Today's queue: the seeded clock preset "Seed day 09:30" lands on this day. The 11:15, 11:30
    # and 11:45 appointments sit just either side of the 2-hour cancellation boundary at 09:30.
    queue_times = ("09:00", "09:15", "09:45", "11:15", "11:30", "11:45", "12:30", "17:15")
    for index, hhmm in enumerate(queue_times):
        _add_appointment(
            session, rao, 5 + index, dates.queue_day, hhmm, reason=REASONS[index % len(REASONS)]
        )
    if dates.queue_day.weekday() in (MON, WED, FRI):
        for number, hhmm in ((13, "10:00"), (14, "11:00"), (15, "12:30")):
            _add_appointment(session, menon, number, dates.queue_day, hhmm, reason="Vaccination")

    _add_history(session, rao, menon, anchor)

    session.add_all(
        [
            AppMeta(key="seed_anchor_date", value=anchor.isoformat()),
            AppMeta(key="seed_queue_day", value=dates.queue_day.isoformat()),
            AppMeta(key="seeded_at", value=seeded_at.isoformat()),
        ]
    )
    session.flush()
    return dates


def _add_history(session: Session, rao: Doctor, menon: Doctor, anchor: date) -> None:
    """About 24 completed visits in the four weeks before the anchor, for the neutral patients.

    History uses late-morning times that no scenario uses, so it can never overlap one. Neutral
    patients get only completed visits: a stray no-show would flag them by accident.
    """
    rao_times = ["11:30", "11:45", "12:00", "12:15", "12:30", "12:45"]
    day = anchor - timedelta(days=28)
    visit = 0
    while day < anchor:
        if day.weekday() < 5:
            _add_appointment(
                session,
                rao,
                5 + visit % 11,
                day,
                rao_times[visit % len(rao_times)],
                status=Status.COMPLETED,
                reason=REASONS[visit % len(REASONS)],
            )
            if day.weekday() == WED:
                _add_appointment(
                    session,
                    menon,
                    9 + visit % 7,
                    day,
                    "10:00",
                    status=Status.COMPLETED,
                    reason="Vaccination",
                )
            visit += 1
        day += timedelta(days=1)


def describe_scenarios(dates: ScenarioDates) -> list[str]:
    """The scenario table for README section 10: what to try, on which date, with which phone."""

    def day(value: date) -> str:
        return f"{value:%a %Y-%m-%d}"

    def flag_ends(strikes: tuple[Strike, Strike]) -> str:
        # The flag lasts through the moment the older of the two strikes is 30 days old.
        older = min(strikes, key=lambda s: (s.day, s.hhmm))
        until = (at_ist(older.day, _minutes(older.hhmm)) + LOOKBACK).astimezone(IST)
        return f"flagged through {until:%Y-%m-%d %H:%M} IST"

    rows = [
        ("anchor date A", day(dates.anchor)),
        ("clock preset 'Seed day'", f"{day(dates.queue_day)} 09:30 IST (today's queue)"),
        ("extra Saturday", f"{day(dates.extra_saturday)}: Dr. Menon works 10:00-13:00 (override)"),
        ("conflict demo", f"{day(dates.conflict_day)}: Dr. Rao has 3 bookings and no override"),
        (
            "leave day with orphan",
            f"{day(dates.leave_day)}: Dr. Rao on leave, 1 booking is orphaned",
        ),
        ("cap demo", f"{day(dates.cap_day)}: Dr. Menon, cap 6, 5 booked, 3 slots still free"),
        (
            "overlap demo",
            f"{day(dates.busy_monday)}: Arjun Mehta has Dr. Rao at 10:00, try Dr. Menon",
        ),
        ("flagged patient", f"Kavita Nair +919000000001, {flag_ends(dates.kavita)}"),
        ("one strike", "Rohan Gupta +919000000002, not flagged"),
        ("expiring flag", f"Sneha Pillai +919000000003, {flag_ends(dates.sneha)}"),
    ]
    return [f"{label:<26}{text}" for label, text in rows]
