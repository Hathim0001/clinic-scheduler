"""AppointmentQueries: single reads, filtered lists, patient history and the day queue."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.domain.errors import ErrorCode, NotFoundError
from app.domain.model import Status
from app.services.views import AppointmentView, Page
from tests.factories import add_appointment, add_override
from tests.helpers import ist
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def seed_day(clinic: Clinic) -> None:
    """Monday: Rao 09:00 completed, 10:00 booked, 10:30 cancelled; Menon 09:15 no-show."""
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(9), status=Status.COMPLETED)
        add_appointment(session, clinic.rao, clinic.ravi, at(10))
        add_appointment(session, clinic.rao, clinic.meena, at(10, 30), status=Status.CANCELLED)
        add_appointment(
            session, clinic.menon, clinic.meena, at(9, 15), minutes=15, status=Status.NO_SHOW
        )


def search(
    clinic: Clinic,
    *,
    doctor_id: int | None = None,
    day: date | None = None,
    status: Status | None = None,
    needs_attention: bool | None = None,
    limit: int = 20,
    offset: int = 0,
    now: datetime = NOW,
) -> Page[AppointmentView]:
    return clinic.queries.search(
        doctor_id=doctor_id,
        day=day,
        status=status,
        needs_attention=needs_attention,
        limit=limit,
        offset=offset,
        now=now,
    )


def test_one_appointment_carries_names_and_derived_fields(clinic: Clinic) -> None:
    seed_day(clinic)
    view = clinic.queries.get(2, NOW)
    assert (view.patient_name, view.doctor_name, view.status) == (
        "Ravi Kumar",
        "Dr. Rao",
        Status.BOOKED,
    )
    assert view.allowed_actions == ("cancel", "reschedule")
    assert view.needs_attention is False
    started = clinic.queries.get(2, at(10, 5))
    assert started.allowed_actions == ("complete", "no-show", "cancel")


def test_an_unknown_appointment_is_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError) as raised:
        clinic.queries.get(999, NOW)
    assert raised.value.code is ErrorCode.APPOINTMENT_NOT_FOUND


def test_the_queue_lists_a_day_in_time_order_without_cancelled_ones(clinic: Clinic) -> None:
    seed_day(clinic)
    queue = clinic.queries.queue(MONDAY, None, False, NOW)
    assert [(v.start_at, v.status) for v in queue] == [
        (at(9), Status.COMPLETED),
        (at(9, 15), Status.NO_SHOW),
        (at(10), Status.BOOKED),
    ]


def test_cancelled_appointments_appear_in_the_queue_on_request(clinic: Clinic) -> None:
    seed_day(clinic)
    queue = clinic.queries.queue(MONDAY, None, True, NOW)
    assert [v.status for v in queue][-1] is Status.CANCELLED
    assert len(queue) == 4


def test_the_queue_can_be_limited_to_one_doctor(clinic: Clinic) -> None:
    seed_day(clinic)
    assert [v.doctor_name for v in clinic.queries.queue(MONDAY, clinic.menon, False, NOW)] == [
        "Dr. Menon"
    ]
    with pytest.raises(NotFoundError) as raised:
        clinic.queries.queue(MONDAY, 999, False, NOW)
    assert raised.value.code is ErrorCode.DOCTOR_NOT_FOUND


def test_the_queue_follows_the_india_calendar_not_utc(clinic: Clinic) -> None:
    """23:30 IST on the 2nd is 18:00 UTC; 00:30 IST on the 3rd is 19:00 UTC on the 2nd."""
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, ist(2026, 11, 2, 23, 30))
        add_appointment(session, clinic.rao, clinic.ravi, ist(2026, 11, 3, 0, 30))
    assert [v.start_at for v in clinic.queries.queue(date(2026, 11, 2), None, False, NOW)] == [
        ist(2026, 11, 2, 23, 30)
    ]
    assert [v.start_at for v in clinic.queries.queue(date(2026, 11, 3), None, False, NOW)] == [
        ist(2026, 11, 3, 0, 30)
    ]


def test_a_list_can_be_filtered_by_doctor_day_and_status(clinic: Clinic) -> None:
    seed_day(clinic)
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(9, day=3))
    assert search(clinic).total == 5
    assert search(clinic, doctor_id=clinic.menon).total == 1
    assert search(clinic, day=date(2026, 11, 3)).total == 1
    assert search(clinic, status=Status.CANCELLED).total == 1
    assert [v.start_at for v in search(clinic, doctor_id=clinic.rao, day=MONDAY).items] == [
        at(9),
        at(10),
        at(10, 30),
    ]


def test_a_list_is_paginated_with_the_total(clinic: Clinic) -> None:
    seed_day(clinic)
    page = search(clinic, limit=2, offset=2)
    assert (page.total, page.limit, page.offset, len(page.items)) == (4, 2, 2, 2)
    assert search(clinic, limit=2, offset=4).items == []


def test_the_needs_attention_filter_finds_orphans_and_survives_reloads(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(10))
        add_appointment(session, clinic.rao, clinic.ravi, at(9, day=3))
        add_override(session, clinic.rao, MONDAY, [])  # Monday is now a leave day
    flagged = search(clinic, needs_attention=True)
    assert [(v.patient_name, v.needs_attention) for v in flagged.items] == [("Asha Iyer", True)]
    fine = search(clinic, needs_attention=False)
    assert [v.patient_name for v in fine.items] == ["Ravi Kumar"]
    assert (flagged.total, fine.total) == (1, 1)
    assert search(clinic, needs_attention=True, limit=1, offset=1).items == []


def test_a_started_appointment_is_never_needing_attention(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(10))
        add_override(session, clinic.rao, MONDAY, [])
    assert search(clinic, needs_attention=True, now=at(10, 30)).total == 0


def test_a_patients_history_is_newest_first_and_filterable(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(9), status=Status.COMPLETED)
        add_appointment(session, clinic.rao, clinic.asha, at(9, day=3))
        add_appointment(session, clinic.rao, clinic.asha, at(9, day=4), status=Status.CANCELLED)
        add_appointment(session, clinic.rao, clinic.ravi, at(10))
    history = clinic.queries.for_patient(clinic.asha, None, 20, 0, NOW)
    assert [v.start_at for v in history.items] == [at(9, day=4), at(9, day=3), at(9)]
    assert history.total == 3
    booked = clinic.queries.for_patient(clinic.asha, Status.BOOKED, 20, 0, NOW)
    assert [v.start_at for v in booked.items] == [at(9, day=3)]
    assert clinic.queries.for_patient(clinic.asha, None, 1, 1, NOW).items[0].start_at == at(
        9, day=3
    )


def test_the_history_of_an_unknown_patient_is_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError) as raised:
        clinic.queries.for_patient(999, None, 20, 0, NOW)
    assert raised.value.code is ErrorCode.PATIENT_NOT_FOUND
