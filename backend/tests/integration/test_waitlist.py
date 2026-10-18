"""The waitlist: joining, the offer a cancellation triggers, and accepting it."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.errors import ConflictError, DomainError, ErrorCode, NotFoundError, RuleViolation
from app.domain.model import CancelledBy, Status
from app.services.views import BookCommand
from tests.factories import add_appointment, add_patient
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def book_ten(clinic: Clinic) -> int:
    """Dr. Rao's 10:00 slot booked for Ravi; returns the appointment id."""
    with clinic.factory() as session, session.begin():
        return add_appointment(session, clinic.rao, clinic.ravi, at(10)).id


def test_a_patient_joins_and_sees_their_place(clinic: Clinic) -> None:
    first = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    second = clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)
    assert (first.status, first.position, second.position) == ("WAITING", 1, 2)
    queue = clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)
    assert [(e.patient_name, e.position) for e in queue] == [("Asha Iyer", 1), ("Meena Das", 2)]


def test_joining_twice_is_refused_but_another_date_or_doctor_is_fine(clinic: Clinic) -> None:
    clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    assert raised.value.code is ErrorCode.ALREADY_WAITING
    clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY + timedelta(days=1), NOW)
    clinic.waitlist.join(clinic.menon, clinic.asha, MONDAY, NOW)


@pytest.mark.parametrize(
    ("day", "code"),
    [
        (date(2026, 11, 1), ErrorCode.BOOKING_IN_PAST),
        (date(2027, 1, 5), ErrorCode.BOOKING_TOO_FAR),
    ],
)
def test_the_date_must_be_inside_the_booking_window(
    clinic: Clinic, day: date, code: ErrorCode
) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.waitlist.join(clinic.rao, clinic.asha, day, NOW)
    assert raised.value.code is code


def test_unknown_doctors_patients_and_entries_are_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError):
        clinic.waitlist.join(999, clinic.asha, MONDAY, NOW)
    with pytest.raises(NotFoundError):
        clinic.waitlist.join(clinic.rao, 999, MONDAY, NOW)
    with pytest.raises(NotFoundError) as raised:
        clinic.waitlist.leave(999, NOW)
    assert raised.value.code is ErrorCode.WAITLIST_ENTRY_NOT_FOUND
    with pytest.raises(NotFoundError):
        clinic.waitlist.for_doctor_day(999, MONDAY, NOW)
    with pytest.raises(NotFoundError):
        clinic.waitlist.for_patient(999, NOW)


def test_a_cancellation_offers_the_slot_to_the_first_in_the_queue(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    first = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)

    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)

    [offered, waiting] = clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)
    assert (offered.id, offered.status, offered.offered_start_at) == (first.id, "OFFERED", at(10))
    assert offered.offer_expires_at == NOW + timedelta(minutes=30)
    assert (waiting.status, waiting.position) == ("WAITING", 1)


def test_the_offer_skips_a_patient_who_cannot_take_the_slot(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.menon, clinic.asha, at(10), minutes=15)  # Asha is busy
    busy = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    free = clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)

    clinic.booking.cancel(booked, CancelledBy.CLINIC, NOW)

    states = {e.id: e.status for e in clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)}
    assert states == {busy.id: "WAITING", free.id: "OFFERED"}


def test_nobody_is_offered_a_slot_on_another_day_or_for_another_doctor(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY + timedelta(days=1), NOW)
    clinic.waitlist.join(clinic.menon, clinic.meena, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    assert clinic.waitlist.for_patient(clinic.asha, NOW)[0].status == "WAITING"
    assert clinic.waitlist.for_patient(clinic.meena, NOW)[0].status == "WAITING"


def test_accepting_books_the_offered_slot(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)

    result = clinic.waitlist.accept(entry.id, "Fever", False, NOW + timedelta(minutes=5))

    assert (result.entry.status, result.appointment.start_at) == ("BOOKED", at(10))
    assert result.entry.appointment_id == result.appointment.id
    assert result.appointment.patient_name == "Asha Iyer"
    assert clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW) == []


def test_an_expired_offer_cannot_be_accepted_and_the_entry_is_closed(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    later = NOW + timedelta(minutes=31)
    with pytest.raises(ConflictError) as raised:
        clinic.waitlist.accept(entry.id, "Fever", False, later)
    assert raised.value.code is ErrorCode.OFFER_EXPIRED
    assert clinic.waitlist.for_patient(clinic.asha, later) == []


def test_the_offer_lasts_until_the_slot_starts_when_that_is_sooner(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, at(9, 30))
    clinic.booking.cancel(booked, CancelledBy.CLINIC, at(9, 45))
    [offer] = clinic.waitlist.for_patient(clinic.asha, at(9, 45))
    assert offer.offer_expires_at == at(10)  # 15 minutes, not 30


def test_a_lost_race_returns_the_patient_to_the_queue(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(10), "Walk-in"), NOW)

    with pytest.raises(DomainError) as raised:
        clinic.waitlist.accept(entry.id, "Fever", False, NOW)
    assert raised.value.code is ErrorCode.SLOT_TAKEN
    [again] = clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)
    assert (again.status, again.position) == ("WAITING", 1)


def test_accepting_without_an_offer_is_an_invalid_transition(clinic: Clinic) -> None:
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.waitlist.accept(entry.id, "Fever", False, NOW)
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_a_flagged_patient_must_confirm_the_deposit_and_keeps_the_offer(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        for hour in (9, 10):
            add_appointment(
                session, clinic.rao, clinic.asha, at(hour, day=1), status=Status.NO_SHOW
            )
    booked = book_ten(clinic)
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)

    with pytest.raises(DomainError) as raised:
        clinic.waitlist.accept(entry.id, "Fever", False, NOW)
    assert raised.value.code is ErrorCode.DEPOSIT_REQUIRED
    assert clinic.waitlist.for_patient(clinic.asha, NOW)[0].status == "OFFERED"
    assert clinic.waitlist.accept(entry.id, "Fever", True, NOW).entry.status == "BOOKED"


def test_leaving_removes_the_entry_and_a_second_leave_is_refused(clinic: Clinic) -> None:
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    assert clinic.waitlist.leave(entry.id, NOW).status == "CANCELLED"
    with pytest.raises(ConflictError):
        clinic.waitlist.leave(entry.id, NOW)
    clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)  # can join again


def test_a_reschedule_frees_the_old_slot_for_the_waitlist(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)
    clinic.booking.reschedule(booked, at(11), None, None, NOW)
    [offer] = clinic.waitlist.for_patient(clinic.meena, NOW)
    assert (offer.status, offer.offered_start_at) == ("OFFERED", at(10))


def test_a_slot_already_in_the_past_is_not_offered(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, at(9, 59))
    clinic.booking.cancel(booked, CancelledBy.PATIENT, at(10, 5))
    assert clinic.waitlist.for_patient(clinic.meena, at(10, 5))[0].status == "WAITING"


def test_queue_positions_follow_the_order_of_joining(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        extra = add_patient(session, 7, name="Extra").id
    a = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    b = clinic.waitlist.join(clinic.rao, extra, MONDAY, NOW)
    assert (a.position, b.position) == (1, 2)


def test_a_slot_already_on_offer_is_not_offered_twice(clinic: Clinic) -> None:
    from app.persistence import repositories as repo
    from app.services.waitlist_offers import offer_freed_slot

    booked = book_ten(clinic)
    clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    with clinic.factory() as session, session.begin():
        doctor = repo.get_doctor(session, clinic.rao, lock=True)
        assert offer_freed_slot(session, doctor, at(10), NOW) is None
    states = [e.status for e in clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)]
    assert states == ["OFFERED", "WAITING"]


def test_the_report_counts_a_cancelled_slot_the_waitlist_refilled(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    before = clinic.records.summary(MONDAY, MONDAY).total
    assert (before.freed_slots, before.refilled, before.recovery_rate) == (1, 0, 0.0)

    clinic.waitlist.accept(entry.id, "Fever", False, NOW + timedelta(minutes=5))

    total = clinic.records.summary(MONDAY, MONDAY).total
    assert (total.freed_slots, total.refilled, total.refilled_via_waitlist) == (1, 1, 1)
    assert total.recovery_rate == 1.0


def test_a_slot_refilled_by_an_ordinary_booking_is_not_credited_to_the_waitlist(
    clinic: Clinic,
) -> None:
    booked = book_ten(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    clinic.booking.book(
        BookCommand(clinic.rao, clinic.meena, at(10), "Cough"), NOW + timedelta(minutes=1)
    )
    total = clinic.records.summary(MONDAY, MONDAY).total
    assert (total.freed_slots, total.refilled, total.refilled_via_waitlist) == (1, 1, 0)


def test_a_booking_made_before_the_cancellation_is_not_a_refill(clinic: Clinic) -> None:
    booked = book_ten(clinic)
    other = clinic.booking.book(BookCommand(clinic.rao, clinic.meena, at(11), "Cough"), NOW)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW + timedelta(minutes=1))
    total = clinic.records.summary(MONDAY, MONDAY).total
    assert other.id != booked
    assert (total.freed_slots, total.refilled) == (1, 0)


def test_a_moved_appointment_is_not_counted_as_freed(clinic: Clinic) -> None:
    mine = clinic.booking.book(BookCommand(clinic.rao, clinic.meena, at(10), "Cough"), NOW)
    clinic.booking.reschedule(mine.id, at(11), None, None, NOW)
    total = clinic.records.summary(MONDAY, MONDAY).total
    assert (total.freed_slots, total.recovery_rate) == (0, None)
