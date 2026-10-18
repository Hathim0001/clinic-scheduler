"""The nearest bookable times when the asked-for day is not available."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.alternatives_service import AlternativesService
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def service(clinic: Clinic) -> AlternativesService:
    return AlternativesService(clinic.availability, clinic.doctors)


def leave(clinic: Clinic, doctor_id: int, day: date = MONDAY) -> None:
    clinic.availability.put_override(doctor_id, day, [], "leave", False, NOW)


def test_a_doctor_on_leave_gets_the_next_day_and_the_other_doctor_the_same_day(
    clinic: Clinic,
) -> None:
    leave(clinic, clinic.rao)
    options = service(clinic).nearest(clinic.rao, MONDAY, clinic.asha, NOW)

    assert (options[0].doctor_id, options[0].start_at) == (clinic.rao, at(9, day=3))
    assert options[0].same_doctor
    others = [o for o in options if not o.same_doctor]
    assert others
    assert others[0].doctor_id == clinic.menon
    assert others[0].start_at == at(9)  # Dr. Menon is free on the day that was asked for
    assert all(o.start_at >= NOW for o in options)


def test_the_same_doctor_comes_first_even_when_another_is_sooner(clinic: Clinic) -> None:
    leave(clinic, clinic.rao)
    options = service(clinic).nearest(clinic.rao, MONDAY, None, NOW, limit=3)
    assert [o.same_doctor for o in options] == sorted(
        (o.same_doctor for o in options), reverse=True
    )
    assert len(options) == 3


def test_a_longer_visit_only_gets_starts_where_it_fits(clinic: Clinic) -> None:
    leave(clinic, clinic.rao)
    options = service(clinic).nearest(clinic.rao, MONDAY, clinic.asha, NOW, slots=4)
    assert options
    for option in options:
        slot_len = 30 if option.doctor_id == clinic.rao else 15
        assert option.duration_min == 4 * slot_len


def test_a_doctor_who_stopped_taking_bookings_is_not_offered(clinic: Clinic) -> None:
    leave(clinic, clinic.rao)
    clinic.doctors.update(clinic.menon, NOW, accepting_bookings=False)
    options = service(clinic).nearest(clinic.rao, MONDAY, None, NOW, limit=12)
    assert {o.doctor_id for o in options} == {clinic.rao}


def test_looking_at_many_days_in_one_transaction_gives_the_same_answers(clinic: Clinic) -> None:
    from datetime import timedelta

    days = [MONDAY + timedelta(days=n) for n in range(5)]
    leave(clinic, clinic.rao, days[1])
    many = clinic.availability.free_slots_many(clinic.rao, days, clinic.asha, NOW, 2)
    single = [clinic.availability.free_slots(clinic.rao, d, clinic.asha, NOW, 2) for d in days]
    assert many == single
    assert many[1].slots == ()
