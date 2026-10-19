"""The trends report: per-day outcomes, weekday and hour patterns, and the effect of reminders."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.errors import RuleViolation
from app.domain.model import Status
from app.persistence.models import Appointment, Notification
from app.services.trends_service import TrendsService
from tests.factories import add_appointment
from tests.integration.conftest import NOW, Clinic, at

pytestmark = pytest.mark.integration

MONDAY, TUESDAY = date(2026, 11, 2), date(2026, 11, 3)


def trends(clinic: Clinic, start: date = MONDAY, end: date = TUESDAY, doctor: int | None = None):  # type: ignore[no-untyped-def]
    return TrendsService(clinic.factory).trends(start, end, doctor)


def fill(clinic: Clinic) -> dict[str, int]:
    """Five visits on Monday, one moved visit, and two on Tuesday (one is the move's new time)."""
    ids: dict[str, int] = {}
    with clinic.factory() as session, session.begin():

        def add(
            name: str,
            doctor: int,
            patient: int,
            hour: int,
            minute: int,
            status: Status,
            day: int = 2,
            moved_to: int | None = None,
        ) -> Appointment:
            row = add_appointment(
                session,
                doctor,
                patient,
                at(hour, minute, day=day),
                status=status,
                rescheduled_to_id=moved_to,
            )
            ids[name] = row.id
            return row

        add("done", clinic.rao, clinic.asha, 9, 0, Status.COMPLETED)
        add("missed", clinic.rao, clinic.ravi, 9, 30, Status.NO_SHOW)
        add("cancelled", clinic.rao, clinic.meena, 10, 0, Status.CANCELLED)
        add("late", clinic.rao, clinic.asha, 10, 30, Status.LATE_CANCELLED)
        add("upcoming", clinic.rao, clinic.ravi, 11, 0, Status.BOOKED)
        target = add("target", clinic.rao, clinic.meena, 12, 0, Status.BOOKED, day=3)
        add("moved", clinic.rao, clinic.meena, 12, 0, Status.CANCELLED, moved_to=target.id)
        add("tuesday_done", clinic.menon, clinic.asha, 9, 0, Status.COMPLETED, day=3)
    return ids


def test_an_empty_range_has_a_row_for_every_day(clinic: Clinic) -> None:
    view = trends(clinic, MONDAY, MONDAY + timedelta(days=6))
    assert [d.day for d in view.days] == [MONDAY + timedelta(days=n) for n in range(7)]
    assert all(d.scheduled == 0 for d in view.days)
    assert view.hours == ()
    assert [b.scheduled for b in view.weekdays] == [0] * 7
    assert view.reminder_effect.reminded_visits == view.reminder_effect.other_visits == 0


def test_each_day_counts_its_outcomes_and_leaves_moved_visits_out(clinic: Clinic) -> None:
    fill(clinic)
    monday, tuesday = trends(clinic).days
    assert (monday.scheduled, monday.completed, monday.no_show) == (5, 1, 1)
    assert (monday.cancelled, monday.upcoming) == (2, 1)  # the cancelled and the late cancelled
    # Tuesday has the move's new visit (booked) and Menon's completed one
    assert (tuesday.scheduled, tuesday.completed, tuesday.upcoming) == (2, 1, 1)


def test_the_weekday_buckets_carry_the_no_show_rate(clinic: Clinic) -> None:
    fill(clinic)
    weekdays = trends(clinic).weekdays
    monday, tuesday = weekdays[0], weekdays[1]
    assert (monday.scheduled, monday.completed, monday.no_show) == (5, 1, 1)
    assert monday.no_show_rate == 0.5
    assert tuesday.no_show_rate == 0.0  # one completed, no no-shows
    assert weekdays[2].no_show_rate is None  # nothing known on a Wednesday


def test_the_hour_buckets_cover_only_hours_with_visits(clinic: Clinic) -> None:
    fill(clinic)
    hours = {b.key: b for b in trends(clinic).hours}
    assert sorted(hours) == [9, 10, 11, 12]
    assert (hours[9].scheduled, hours[9].no_show, hours[9].completed) == (3, 1, 2)
    assert hours[9].no_show_rate == pytest.approx(1 / 3, abs=1e-4)
    assert hours[10].no_show_rate is None  # only cancellations at 10


def test_one_doctor_can_be_looked_at_alone(clinic: Clinic) -> None:
    fill(clinic)
    menon = trends(clinic, doctor=clinic.menon)
    assert sum(d.scheduled for d in menon.days) == 1
    assert menon.doctor_id == clinic.menon
    rao = trends(clinic, doctor=clinic.rao)
    assert sum(d.scheduled for d in rao.days) == 6


def test_reminded_patients_are_compared_with_the_rest(clinic: Clinic) -> None:
    ids = fill(clinic)
    with clinic.factory() as session, session.begin():
        session.add(
            Notification(
                patient_id=clinic.asha,
                appointment_id=ids["done"],
                kind="REMINDER_FIRST",
                to_phone="+919000000001",
                body="Reminder",
                status="SENT",
                sent_at=NOW,
                sent_via="GATEWAY",
            )
        )
        session.add(  # a reminder that was never sent proves nothing
            Notification(
                patient_id=clinic.ravi,
                appointment_id=ids["missed"],
                kind="REMINDER_FIRST",
                to_phone="+919000000002",
                body="Reminder",
                status="PENDING",
            )
        )
    effect = trends(clinic).reminder_effect
    assert (effect.reminded_visits, effect.reminded_no_shows) == (1, 0)
    assert (effect.other_visits, effect.other_no_shows) == (2, 1)  # the no-show and Tuesday's visit


def test_an_end_before_the_start_and_a_range_over_92_days_are_refused(clinic: Clinic) -> None:
    with pytest.raises(RuleViolation):
        trends(clinic, TUESDAY, MONDAY)
    with pytest.raises(RuleViolation):
        trends(clinic, MONDAY, MONDAY + timedelta(days=92))
    assert len(trends(clinic, MONDAY, MONDAY + timedelta(days=91)).days) == 92
