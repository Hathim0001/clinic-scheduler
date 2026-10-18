"""`needs_attention` is stored (appointments.outside_hours); it must always equal the rule."""

from __future__ import annotations

import random
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.domain.availability import needs_attention
from app.domain.model import Window
from app.domain.timeutil import ist_date
from app.persistence import repositories as repo
from app.services.views import BookCommand
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def derived(clinic: Clinic) -> dict[int, bool]:
    """The rule worked out from scratch for every appointment, as the old code did on each read."""
    with clinic.factory() as session:
        lookup = repo.WindowsLookup(session)
        answer = {}
        for appointment in clinic.appointments():
            windows = lookup.windows(appointment.doctor_id, ist_date(appointment.start_at))
            facts = repo.appointment_facts(appointment)
            answer[appointment.id] = needs_attention(facts, NOW, windows)
    return answer


def stored(clinic: Clinic) -> dict[int, bool]:
    views = clinic.queries.search(
        doctor_id=None, day=None, status=None, needs_attention=None, limit=100, offset=0, now=NOW
    ).items
    return {v.id: v.needs_attention for v in views}


def book_some(clinic: Clinic) -> None:
    for day in range(2, 7):
        for hour in (9, 10, 11, 12):
            clinic.booking.book(
                BookCommand(
                    clinic.rao, clinic.asha if hour % 2 else clinic.ravi, at(hour, day=day), "x"
                ),
                NOW,
            )


def test_the_stored_flag_matches_the_rule_after_any_run_of_hour_changes(clinic: Clinic) -> None:
    book_some(clinic)
    for seed in range(12):
        rng = random.Random(seed)
        day = MONDAY + timedelta(days=rng.randrange(0, 5))
        choice = rng.choice(["leave", "short", "late", "remove"])
        if choice == "remove":
            clinic.availability.delete_override(clinic.rao, day, True, NOW)
        else:
            windows = {
                "leave": [],
                "short": [Window(9 * 60, 10 * 60 + 30)],
                "late": [Window(11 * 60, 13 * 60)],
            }[choice]
            clinic.availability.put_override(clinic.rao, day, windows, None, True, NOW)
        assert stored(clinic) == derived(clinic), f"seed {seed}: {choice} on {day}"


def test_a_new_booking_is_never_stored_as_outside_the_hours(clinic: Clinic) -> None:
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    assert clinic.appointment(booked.id).outside_hours is False


def test_the_flag_goes_away_when_the_hours_come_back(clinic: Clinic) -> None:
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)
    clinic.availability.put_override(clinic.rao, MONDAY, [], "leave", True, NOW)
    assert clinic.appointment(booked.id).outside_hours is True
    clinic.availability.delete_override(clinic.rao, MONDAY, False, NOW)
    assert clinic.appointment(booked.id).outside_hours is False


def test_a_partial_index_covers_exactly_the_rows_the_list_asks_for(clinic: Clinic) -> None:
    with clinic.factory() as session:
        definition = session.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_appointments_outside_hours'"
            )
        )
    assert definition is not None
    assert "(start_at)" in definition
    assert "outside_hours" in definition
    assert "BOOKED" in definition


def test_the_needs_attention_list_is_paged_from_the_stored_flag(clinic: Clinic) -> None:
    book_some(clinic)
    clinic.availability.put_override(clinic.rao, MONDAY, [], "leave", True, NOW)
    page = clinic.queries.search(
        doctor_id=None, day=None, status=None, needs_attention=True, limit=2, offset=1, now=NOW
    )
    assert page.total == 4  # the four 09:00 to 12:00 bookings on the leave Monday
    assert len(page.items) == 2
    assert all(v.needs_attention for v in page.items)
