"""Trends for the report page: how the days went, which weekdays and hours see the most no-shows,
and whether patients who were sent a reminder came more often.

It counts the same way the summary report does: a rescheduled appointment is one that moved, not a
cancellation, so it is left out of every outcome count; the no-show rate is no-shows out of
completed plus no-shows (visits whose outcome is known).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ErrorCode, RuleViolation
from app.domain.model import Status
from app.domain.timeutil import IST, at_ist, ist_date
from app.persistence.models import Appointment, Notification
from app.services.notification_service import REMINDER_KINDS
from app.services.record_service import MAX_REPORT_DAYS
from app.services.support import run


@dataclass(frozen=True, slots=True)
class DayTrend:
    day: date
    scheduled: int  # visits that were not moved elsewhere
    completed: int
    no_show: int
    cancelled: int  # cancelled and late-cancelled
    upcoming: int  # still booked


@dataclass(frozen=True, slots=True)
class Bucket:
    key: int  # weekday (Monday is 0) or hour of the India day
    scheduled: int
    completed: int
    no_show: int
    no_show_rate: float | None


@dataclass(frozen=True, slots=True)
class ReminderEffect:
    reminded_visits: int  # visits with a known outcome whose patient was sent a reminder
    reminded_no_shows: int
    other_visits: int
    other_no_shows: int


@dataclass(frozen=True, slots=True)
class TrendsView:
    start: date
    end: date
    doctor_id: int | None
    days: tuple[DayTrend, ...]
    weekdays: tuple[Bucket, ...]
    hours: tuple[Bucket, ...]
    reminder_effect: ReminderEffect


def _rate(no_show: int, completed: int) -> float | None:
    known = no_show + completed
    return round(no_show / known, 4) if known else None


def _bucket(key: int, rows: list[Appointment]) -> Bucket:
    completed = sum(1 for a in rows if a.status == Status.COMPLETED.value)
    no_show = sum(1 for a in rows if a.status == Status.NO_SHOW.value)
    return Bucket(key, len(rows), completed, no_show, _rate(no_show, completed))


class TrendsService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def trends(self, start: date, end: date, doctor_id: int | None = None) -> TrendsView:
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

        def work(session: Session) -> TrendsView:
            first, after = at_ist(start, 0), at_ist(end + timedelta(days=1), 0)
            query = select(Appointment).where(
                Appointment.start_at >= first,
                Appointment.start_at < after,
                Appointment.rescheduled_to_id.is_(None),  # moved visits are not outcomes
            )
            if doctor_id is not None:
                query = query.where(Appointment.doctor_id == doctor_id)
            rows = list(session.scalars(query))

            by_day: dict[date, list[Appointment]] = {}
            by_weekday: dict[int, list[Appointment]] = {n: [] for n in range(7)}
            by_hour: dict[int, list[Appointment]] = {}
            for appointment in rows:
                local = appointment.start_at.astimezone(IST)
                by_day.setdefault(ist_date(appointment.start_at), []).append(appointment)
                by_weekday[local.weekday()].append(appointment)
                by_hour.setdefault(local.hour, []).append(appointment)

            def day_trend(day: date) -> DayTrend:
                mine = by_day.get(day, [])

                def count(*statuses: Status) -> int:
                    return sum(1 for a in mine if a.status in {s.value for s in statuses})

                return DayTrend(
                    day,
                    len(mine),
                    count(Status.COMPLETED),
                    count(Status.NO_SHOW),
                    count(Status.CANCELLED, Status.LATE_CANCELLED),
                    count(Status.BOOKED),
                )

            days = tuple(
                day_trend(start + timedelta(days=n)) for n in range((end - start).days + 1)
            )
            return TrendsView(
                start,
                end,
                doctor_id,
                days,
                tuple(_bucket(n, by_weekday[n]) for n in range(7)),
                tuple(_bucket(h, by_hour[h]) for h in sorted(by_hour)),
                _reminder_effect(session, rows),
            )

        return run(self._factory, work)


def _reminder_effect(session: Session, rows: list[Appointment]) -> ReminderEffect:
    known = [a for a in rows if a.status in (Status.COMPLETED.value, Status.NO_SHOW.value)]
    reminded: set[int] = set()
    if known:
        found = session.scalars(
            select(Notification.appointment_id).where(
                Notification.kind.in_(REMINDER_KINDS),
                Notification.status == "SENT",
                Notification.appointment_id.in_([a.id for a in known]),
            )
        )
        reminded = {appointment_id for appointment_id in found if appointment_id is not None}
    with_reminder = [a for a in known if a.id in reminded]
    without = [a for a in known if a.id not in reminded]

    def missed(group: list[Appointment]) -> int:
        return sum(1 for a in group if a.status == Status.NO_SHOW.value)

    return ReminderEffect(len(with_reminder), missed(with_reminder), len(without), missed(without))
