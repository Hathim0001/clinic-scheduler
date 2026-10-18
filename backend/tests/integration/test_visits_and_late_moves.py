"""Visits longer than one slot, and moving an appointment inside two hours: two design limits that
were lifted (a phone number stays unique, as the problem statement defines the patient)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.errors import ConflictError, DomainError, ErrorCode, RuleViolation
from app.domain.model import CancelledBy, Status
from app.services.views import AppointmentView, BookCommand
from tests.factories import add_appointment
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def visit(
    clinic: Clinic, hour: int, minute: int = 0, *, slots: int = 2, patient: int | None = None
) -> AppointmentView:
    return clinic.booking.book(
        BookCommand(clinic.rao, patient or clinic.asha, at(hour, minute), "Physio", slots=slots),
        NOW,
    )


# ------------------------------------------------------------------------------ longer visits


def test_a_two_slot_visit_lasts_two_of_the_doctors_slots(clinic: Clinic) -> None:
    booked = visit(clinic, 10, slots=2)  # Dr. Rao sees patients in 30 minutes
    assert (booked.slots, booked.end_at - booked.start_at) == (2, timedelta(minutes=60))
    stored = clinic.appointment(booked.id)
    assert (stored.slots, stored.end_at - stored.start_at) == (2, timedelta(minutes=60))


def test_every_slot_a_long_visit_covers_is_taken(clinic: Clinic) -> None:
    visit(clinic, 10, slots=2)  # 10:00 to 11:00
    for hour, minute in ((10, 0), (10, 30)):
        with pytest.raises(ConflictError) as raised:
            clinic.booking.book(BookCommand(clinic.rao, clinic.meena, at(hour, minute), "x"), NOW)
        assert raised.value.code is ErrorCode.SLOT_TAKEN
    free_after = clinic.booking.book(BookCommand(clinic.rao, clinic.meena, at(11), "x"), NOW)
    assert free_after.start_at == at(11)  # the slot after the visit is free


def test_a_visit_cannot_start_inside_another_or_run_into_it(clinic: Clinic) -> None:
    visit(clinic, 11, slots=1, patient=clinic.ravi)  # 11:00 to 11:30 is taken
    with pytest.raises(ConflictError) as raised:  # 10:30 to 11:30 would run into it
        visit(clinic, 10, 30, slots=2)
    assert raised.value.code is ErrorCode.SLOT_TAKEN
    assert raised.value.details["appointment_id"] is not None


def test_a_long_visit_must_fit_inside_one_window(clinic: Clinic) -> None:
    with pytest.raises(
        RuleViolation
    ) as raised:  # 12:30 + 60 minutes ends at 13:30; she stops at 13:00
        visit(clinic, 12, 30, slots=2)
    assert raised.value.code is ErrorCode.OUTSIDE_AVAILABILITY
    assert "60-minute visit" in raised.value.message
    assert clinic.booking.book(
        BookCommand(clinic.rao, clinic.asha, at(12), "x", slots=2), NOW
    ).end_at == at(13)  # exactly up to the window's edge is fine


def test_the_start_of_a_long_visit_is_still_on_the_grid(clinic: Clinic) -> None:
    with pytest.raises(RuleViolation) as raised:
        visit(clinic, 10, 15, slots=2)
    assert raised.value.code is ErrorCode.OFF_GRID


def test_a_patient_cannot_be_in_two_places_during_a_long_visit(clinic: Clinic) -> None:
    visit(clinic, 10, slots=2)  # Asha, 10:00 to 11:00 with Dr. Rao
    with pytest.raises(ConflictError) as raised:
        clinic.booking.book(BookCommand(clinic.menon, clinic.asha, at(10, 45), "x"), NOW)
    assert raised.value.code is ErrorCode.PATIENT_OVERLAP


def test_a_long_visit_counts_once_against_the_daily_cap(clinic: Clinic) -> None:
    """The cap limits patients seen, not minutes: six two-slot visits fit under a cap of six."""
    patients = []
    for n in range(6):
        patients.append(
            clinic.patients.create(f"Cap {n}", f"98000000{n:02d}", date(1990, 1, 1), NOW, True).id
        )
    for n, patient in enumerate(patients[:2]):
        visit(clinic, 9 + n, slots=2, patient=patient)  # 09:00-10:00 and 10:00-11:00
    visit(clinic, 11, slots=2, patient=patients[2])  # 11:00-12:00
    visit(clinic, 12, slots=2, patient=patients[3])  # 12:00-13:00
    assert len(clinic.appointments()) == 4  # four visits, eight slots, cap not reached


def test_free_slots_for_a_long_visit_leave_out_starts_where_it_does_not_fit(clinic: Clinic) -> None:
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(10), "x"), NOW)  # 10:00 is taken
    one = clinic.availability.free_slots(clinic.rao, MONDAY, None, NOW, 1)
    two = clinic.availability.free_slots(clinic.rao, MONDAY, None, NOW, 2)
    assert at(10) not in one.slots
    assert at(9, 30) in one.slots
    assert at(9, 30) not in two.slots  # 09:30 to 10:30 would run into the 10:00 visit
    assert at(10, 30) in two.slots
    assert at(12, 30) not in two.slots  # would end after the window
    assert (one.duration_min, two.duration_min) == (30, 60)


def test_the_day_schedule_shows_every_covered_slot_as_booked(clinic: Clinic) -> None:
    visit(clinic, 10, slots=2)
    schedule = clinic.availability.day_schedule(clinic.rao, MONDAY, None, NOW)
    states = {
        s.start_at: (s.state.value, s.appointment.slots if s.appointment else None)
        for s in schedule.slots
    }
    assert states[at(10)] == ("BOOKED", 2)
    assert states[at(10, 30)] == ("BOOKED", 2)
    assert states[at(11)][0] == "FREE"


def test_rescheduling_keeps_the_length_in_slots_with_the_same_doctor(clinic: Clinic) -> None:
    booked = visit(clinic, 10, slots=2)
    moved = clinic.booking.reschedule(booked.id, at(11), None, None, NOW)
    assert (moved.new.slots, moved.new.end_at - moved.new.start_at) == (2, timedelta(minutes=60))


def test_rescheduling_to_a_doctor_with_other_slots_keeps_the_minutes(clinic: Clinic) -> None:
    booked = visit(clinic, 10, slots=2)  # 60 minutes
    moved = clinic.booking.reschedule(booked.id, at(10), clinic.menon, None, NOW)  # 15-minute slots
    assert (moved.new.slots, moved.new.end_at - moved.new.start_at) == (4, timedelta(minutes=60))


def test_a_visit_that_does_not_fit_the_other_doctors_slots_is_refused(clinic: Clinic) -> None:
    booked = clinic.booking.book(BookCommand(clinic.menon, clinic.asha, at(10), "x", slots=3), NOW)
    with pytest.raises(RuleViolation) as raised:  # 45 minutes does not divide into 30
        clinic.booking.reschedule(booked.id, at(11), clinic.rao, None, NOW)
    assert raised.value.code is ErrorCode.VALIDATION_ERROR
    assert clinic.appointment(booked.id).status == Status.BOOKED.value


def test_a_series_of_long_visits_books_every_one_with_its_length(clinic: Clinic) -> None:
    views = clinic.booking.book_series(
        BookCommand(clinic.rao, clinic.asha, at(10), "Physio", slots=2), 7, 3, NOW
    )
    assert [(v.slots, v.end_at - v.start_at) for v in views] == [(2, timedelta(minutes=60))] * 3


def test_a_freed_long_visit_is_offered_as_a_long_visit(clinic: Clinic) -> None:
    booked = visit(clinic, 10, slots=2, patient=clinic.ravi)
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    clinic.booking.cancel(booked.id, CancelledBy.CLINIC, NOW)
    [offer] = clinic.waitlist.for_patient(clinic.asha, NOW)
    assert offer.status == "OFFERED"
    accepted = clinic.waitlist.accept(entry.id, "Physio", False, NOW)
    assert accepted.appointment.slots == 2
    assert accepted.appointment.end_at - accepted.appointment.start_at == timedelta(minutes=60)


def test_a_freed_long_visit_is_not_offered_to_someone_it_would_not_suit(clinic: Clinic) -> None:
    """The second patient is busy for half of the freed hour, so the offer skips them."""
    booked = visit(clinic, 10, slots=2, patient=clinic.ravi)
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.menon, clinic.asha, at(10, 30), minutes=15)
    busy = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    free = clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)
    clinic.booking.cancel(booked.id, CancelledBy.CLINIC, NOW)
    states = {e.id: e.status for e in clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)}
    assert states == {busy.id: "WAITING", free.id: "OFFERED"}


def test_the_report_counts_the_slots_a_visit_took(clinic: Clinic) -> None:
    visit(clinic, 10, slots=2)
    report = clinic.records.summary(MONDAY, MONDAY)
    rao = next(d for d in report.doctors if d.doctor_id == clinic.rao)
    assert (rao.appointments, rao.capacity_slots) == (1, 8)
    assert rao.utilisation == round(2 / 8, 4)


def test_the_booking_hash_includes_the_length(clinic: Clinic) -> None:
    one = BookCommand(clinic.rao, clinic.asha, at(10), "x", slots=1)
    first, _ = clinic.booking.book_idempotent(one, "k", NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.book_idempotent(
            BookCommand(clinic.rao, clinic.asha, at(10), "x", slots=2), "k", NOW
        )
    assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert first.slots == 1


# --------------------------------------------------------------- moving it inside two hours


def seed(clinic: Clinic, hour: int = 10) -> int:
    with clinic.factory() as session, session.begin():
        return add_appointment(session, clinic.rao, clinic.asha, at(hour)).id


def test_a_patient_move_inside_two_hours_is_refused_until_confirmed(clinic: Clinic) -> None:
    old = seed(clinic)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.reschedule(old, at(11), None, None, at(8, 30))  # 90 minutes before
    assert raised.value.code is ErrorCode.LATE_RESCHEDULE_NEEDS_CONFIRMATION
    assert raised.value.details["minutes_until_start"] == 90
    assert "late cancellation" in raised.value.message
    assert clinic.appointment(old).status == Status.BOOKED.value  # nothing changed
    assert [e.kind for e in clinic.records.history(old)] == []  # and nothing was recorded


def test_the_confirmed_move_records_the_late_cancellation_and_who_moved_it(clinic: Clinic) -> None:
    old = seed(clinic)
    moved = clinic.booking.reschedule(old, at(11), None, None, at(8, 30), acknowledge_late=True)
    assert moved.old.status is Status.LATE_CANCELLED
    assert clinic.records.history(old)[-1].detail["by"] == "PATIENT"


def test_exactly_two_hours_ahead_needs_no_confirmation(clinic: Clinic) -> None:
    old = seed(clinic, 11)
    moved = clinic.booking.reschedule(old, at(12), None, None, at(9))
    assert moved.old.status is Status.CANCELLED


def test_a_clinic_move_is_never_a_late_cancellation(clinic: Clinic) -> None:
    old = seed(clinic)
    moved = clinic.booking.reschedule(old, at(11), None, None, at(9, 30), by=CancelledBy.CLINIC)
    assert moved.old.status is Status.CANCELLED
    assert moved.old.cancelled_by is CancelledBy.CLINIC
    assert not clinic.patients.get(clinic.asha, NOW).deposit.reasons  # type: ignore[union-attr]
    assert clinic.records.history(old)[-1].detail["by"] == "CLINIC"


def test_the_clinic_can_move_a_patient_who_has_already_checked_in(clinic: Clinic) -> None:
    old = seed(clinic)
    clinic.booking.check_in(old, at(9, 30))
    with pytest.raises(ConflictError) as raised:
        clinic.booking.reschedule(old, at(11), None, None, at(9, 40))
    assert raised.value.code is ErrorCode.ALREADY_CHECKED_IN
    moved = clinic.booking.reschedule(old, at(11), None, None, at(9, 40), by=CancelledBy.CLINIC)
    assert moved.new.status is Status.BOOKED


def test_an_impossible_move_is_reported_before_the_penalty_is_mentioned(clinic: Clinic) -> None:
    """Nobody is asked to accept a late cancellation for a move that cannot happen anyway."""
    old = seed(clinic)
    with pytest.raises(DomainError) as raised:
        clinic.booking.reschedule(old, at(15), None, None, at(9))  # 14:00+ is outside her hours
    assert raised.value.code is ErrorCode.OUTSIDE_AVAILABILITY


def test_the_confirmation_flag_changes_nothing_for_a_move_that_is_not_late(clinic: Clinic) -> None:
    old = seed(clinic)
    moved = clinic.booking.reschedule(old, at(11), None, None, NOW, acknowledge_late=True)
    assert moved.old.status is Status.CANCELLED
