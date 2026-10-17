"""Operations: idempotent booking, audit history, check-in, corrections, a doctor who stops taking
bookings, patient edits and duplicates, waitlist pass-on, the report and the patient export."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.errors import ConflictError, DomainError, ErrorCode, RuleViolation
from app.domain.model import CancelledBy, Status
from app.services.views import BookCommand
from tests.factories import add_appointment
from tests.helpers import burst, outcomes
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def command(clinic: Clinic, hour: int = 10, patient: int | None = None) -> BookCommand:
    return BookCommand(clinic.rao, patient or clinic.asha, at(hour), "Check-up")


def kinds(clinic: Clinic, appointment_id: int) -> list[str]:
    return [e.kind for e in clinic.records.history(appointment_id)]


# ----------------------------------------------------------------------------- idempotency


def test_a_retry_with_the_same_key_returns_the_same_appointment(clinic: Clinic) -> None:
    first, replay_a = clinic.booking.book_idempotent(command(clinic), "key-1", NOW)
    again, replay_b = clinic.booking.book_idempotent(command(clinic), "key-1", NOW)
    assert (replay_a, replay_b) == (False, True)
    assert again.id == first.id
    assert len(clinic.appointments()) == 1
    assert kinds(clinic, first.id) == ["BOOKED"]  # the replay wrote nothing


def test_a_retry_still_works_after_the_appointment_was_cancelled(clinic: Clinic) -> None:
    first, _ = clinic.booking.book_idempotent(command(clinic), "key-1", NOW)
    clinic.booking.cancel(first.id, CancelledBy.PATIENT, NOW)
    again, replayed = clinic.booking.book_idempotent(command(clinic), "key-1", NOW)
    assert replayed
    assert (again.id, again.status) == (first.id, Status.CANCELLED)  # not a second booking
    assert len(clinic.appointments()) == 1


def test_the_same_key_for_a_different_request_is_refused(clinic: Clinic) -> None:
    clinic.booking.book_idempotent(command(clinic, 10), "key-1", NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.book_idempotent(command(clinic, 11), "key-1", NOW)
    assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert len(clinic.appointments()) == 1


def test_different_keys_are_different_requests(clinic: Clinic) -> None:
    clinic.booking.book_idempotent(command(clinic, 10), "key-1", NOW)
    with pytest.raises(DomainError) as raised:  # same slot: the second key is a real second try
        clinic.booking.book_idempotent(command(clinic, 10, clinic.meena), "key-2", NOW)
    assert raised.value.code is ErrorCode.SLOT_TAKEN


def test_a_failed_booking_does_not_burn_its_key(clinic: Clinic) -> None:
    with pytest.raises(DomainError):
        clinic.booking.book_idempotent(command(clinic, 14), "key-1", NOW)  # outside the hours
    view, replayed = clinic.booking.book_idempotent(command(clinic, 14 - 4), "key-1", NOW)
    assert not replayed
    assert view.start_at == at(10)


def test_ten_copies_of_one_request_book_exactly_once(clinic: Clinic) -> None:
    results = burst([lambda: clinic.booking.book_idempotent(command(clinic), "key-1", NOW)] * 10)
    assert outcomes(results) == {"OK": 10}
    assert {r[0].id for r in results if not isinstance(r, Exception)} == {
        clinic.appointments()[0].id
    }
    assert len(clinic.appointments()) == 1
    assert sum(1 for r in results if not isinstance(r, Exception) and not r[1]) == 1


# ----------------------------------------------------------------------------- the audit trail


def test_the_history_follows_an_appointment_from_booking_to_the_end(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    clinic.booking.check_in(booked.id, at(9, 50))
    clinic.booking.complete(booked.id, at(10, 5))
    events = clinic.records.history(booked.id)
    assert [e.kind for e in events] == ["BOOKED", "CHECKED_IN", "COMPLETED"]
    assert events[0].detail["via"] == "BOOKING"
    assert [e.at for e in events] == [NOW, at(9, 50), at(10, 5)]


def test_a_reschedule_is_recorded_on_both_appointments(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    moved = clinic.booking.reschedule(booked.id, at(11), None, None, NOW)
    assert kinds(clinic, booked.id) == ["BOOKED", "CANCELLED"]
    assert kinds(clinic, moved.new.id) == ["BOOKED", "RESCHEDULED_FROM"]
    old_event = clinic.records.history(booked.id)[1]
    assert old_event.detail["rescheduled_to_id"] == moved.new.id
    assert clinic.records.history(moved.new.id)[0].detail["via"] == "RESCHEDULE"


def test_a_failed_reschedule_leaves_no_trace_in_the_history(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    with pytest.raises(DomainError):
        clinic.booking.reschedule(booked.id, at(15), None, None, NOW)  # outside the hours
    assert kinds(clinic, booked.id) == ["BOOKED"]
    assert clinic.appointment(booked.id).status == Status.BOOKED.value


def test_a_cancellation_records_who_and_when(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    clinic.booking.cancel(booked.id, CancelledBy.CLINIC, NOW)
    event = clinic.records.history(booked.id)[-1]
    assert (event.kind, event.detail["by"]) == ("CANCELLED", "CLINIC")


def test_the_history_of_an_unknown_appointment_is_not_found(clinic: Clinic) -> None:
    with pytest.raises(DomainError) as raised:
        clinic.records.history(999)
    assert raised.value.code is ErrorCode.APPOINTMENT_NOT_FOUND


# ----------------------------------------------------------------------------- check-in


def test_a_patient_checks_in_on_the_day_and_doing_it_twice_changes_nothing(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    first = clinic.booking.check_in(booked.id, at(9, 40))
    second = clinic.booking.check_in(booked.id, at(9, 55))
    assert first.checked_in_at == second.checked_in_at == at(9, 40)
    assert "check-in" not in second.allowed_actions
    assert kinds(clinic, booked.id).count("CHECKED_IN") == 1


def test_check_in_opens_on_the_day_of_the_visit(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.check_in(booked.id, at(9) - timedelta(days=1))
    assert raised.value.code is ErrorCode.TOO_EARLY_TO_MARK


def test_only_a_booked_appointment_can_be_checked_in(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    clinic.booking.cancel(booked.id, CancelledBy.PATIENT, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.check_in(booked.id, at(9, 40))
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_a_checked_in_patient_cannot_cancel_or_reschedule_but_the_clinic_can_cancel(
    clinic: Clinic,
) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    clinic.booking.check_in(booked.id, at(9, 40))
    for attempt in (
        lambda: clinic.booking.cancel(booked.id, CancelledBy.PATIENT, at(9, 41)),
        lambda: clinic.booking.reschedule(booked.id, at(11), None, None, at(9, 41)),
    ):
        with pytest.raises(ConflictError) as raised:
            attempt()
        assert raised.value.code is ErrorCode.ALREADY_CHECKED_IN
    result = clinic.booking.cancel(booked.id, CancelledBy.CLINIC, at(9, 42))
    assert result.appointment.status is Status.CANCELLED


def test_two_check_ins_at_once_record_one_arrival(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    results = burst([lambda: clinic.booking.check_in(booked.id, at(9, 40))] * 6)
    assert outcomes(results) == {"OK": 6}
    assert kinds(clinic, booked.id).count("CHECKED_IN") == 1


# ----------------------------------------------------------------------------- corrections


def make_no_show(clinic: Clinic, patient: int, hour: int, *, day: int = 1) -> int:
    with clinic.factory() as session, session.begin():
        return add_appointment(
            session, clinic.rao, patient, at(hour, day=day), status=Status.NO_SHOW
        ).id


def test_correcting_a_no_show_to_completed_lifts_the_deposit_flag(clinic: Clinic) -> None:
    flagged = make_no_show(clinic, clinic.asha, 9)
    make_no_show(clinic, clinic.asha, 10)
    assert clinic.patients.get(clinic.asha, NOW).deposit is not None
    assert clinic.patients.get(clinic.asha, NOW).deposit.required  # type: ignore[union-attr]

    fixed = clinic.booking.correct(
        flagged, Status.COMPLETED, "Patient was seen, wrongly marked", NOW
    )

    assert fixed.status is Status.COMPLETED
    assert not clinic.patients.get(clinic.asha, NOW).deposit.required  # type: ignore[union-attr]
    event = clinic.records.history(flagged)[-1]
    assert (event.kind, event.detail["from_status"], event.detail["to_status"]) == (
        "CORRECTED",
        "NO_SHOW",
        "COMPLETED",
    )
    assert event.detail["note"] == "Patient was seen, wrongly marked"


def test_a_completed_visit_can_be_corrected_to_a_no_show(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        done = add_appointment(
            session, clinic.rao, clinic.asha, at(9, day=1), status=Status.COMPLETED
        ).id
    assert (
        clinic.booking.correct(done, Status.NO_SHOW, "Never arrived", NOW).status is Status.NO_SHOW
    )


def test_a_late_cancellation_can_be_waived(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    late = clinic.booking.cancel(booked.id, CancelledBy.PATIENT, at(9, 30))
    assert late.appointment.status is Status.LATE_CANCELLED
    waived = clinic.booking.correct(booked.id, Status.CANCELLED, "Clinic system outage", NOW)
    assert waived.status is Status.CANCELLED
    assert waived.cancelled_by is CancelledBy.PATIENT  # who cancelled is not rewritten


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (Status.BOOKED, Status.COMPLETED),
        (Status.CANCELLED, Status.BOOKED),
        (Status.CANCELLED, Status.COMPLETED),
        (Status.COMPLETED, Status.CANCELLED),
        (Status.NO_SHOW, Status.NO_SHOW),
        (Status.LATE_CANCELLED, Status.COMPLETED),
    ],
)
def test_other_corrections_are_refused(clinic: Clinic, current: Status, target: Status) -> None:
    with clinic.factory() as session, session.begin():
        appointment_id = add_appointment(session, clinic.rao, clinic.asha, at(9), status=current).id
    with pytest.raises(ConflictError) as raised:
        clinic.booking.correct(appointment_id, target, "x", NOW)
    assert raised.value.code is ErrorCode.INVALID_CORRECTION
    assert clinic.appointment(appointment_id).status == current.value


# ----------------------------------------------------------------------------- not accepting


def test_a_doctor_who_stops_taking_bookings_refuses_new_ones_but_keeps_old_ones(
    clinic: Clinic,
) -> None:
    kept = clinic.booking.book(command(clinic), NOW)
    clinic.doctors.update(clinic.rao, NOW, accepting_bookings=False)

    with pytest.raises(DomainError) as raised:
        clinic.booking.book(command(clinic, 11, clinic.meena), NOW)
    assert raised.value.code is ErrorCode.DOCTOR_NOT_ACCEPTING

    slots = clinic.availability.free_slots(clinic.rao, MONDAY, None, NOW)
    assert slots.slots == ()
    assert slots.unavailable_reason is not None
    assert slots.unavailable_reason.value == "NOT_ACCEPTING"

    assert clinic.queries.get(kept.id, NOW).status is Status.BOOKED
    assert clinic.booking.cancel(kept.id, CancelledBy.CLINIC, NOW).appointment.status is (
        Status.CANCELLED
    )


def test_a_doctor_can_start_taking_bookings_again(clinic: Clinic) -> None:
    clinic.doctors.update(clinic.rao, NOW, accepting_bookings=False)
    assert not clinic.doctors.get(clinic.rao).accepting_bookings
    clinic.doctors.update(clinic.rao, NOW, accepting_bookings=True)
    assert clinic.booking.book(command(clinic), NOW).status is Status.BOOKED


def test_a_series_stops_at_a_doctor_who_is_not_accepting(clinic: Clinic) -> None:
    clinic.doctors.update(clinic.rao, NOW, accepting_bookings=False)
    with pytest.raises(DomainError) as raised:
        clinic.booking.book_series(command(clinic), 7, 3, NOW)
    assert raised.value.code is ErrorCode.DOCTOR_NOT_ACCEPTING
    assert raised.value.details["occurrence"] == 1


# ----------------------------------------------------------------------------- patients


def test_a_patient_changes_their_phone_number_and_keeps_their_history(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    changed = clinic.patients.update(clinic.asha, NOW, phone="98765 43210")
    assert changed.phone == "+919876543210"
    assert clinic.queries.get(booked.id, NOW).patient_phone == "+919876543210"
    assert (
        clinic.patients.search(phone="9876543210", name_prefix=None, limit=5, offset=0).total == 1
    )


def test_a_phone_that_belongs_to_someone_else_is_refused(clinic: Clinic) -> None:
    other = clinic.patients.get(clinic.ravi, NOW).phone
    with pytest.raises(ConflictError) as raised:
        clinic.patients.update(clinic.asha, NOW, phone=other)
    assert raised.value.code is ErrorCode.PHONE_TAKEN
    assert raised.value.details["patient_id"] == clinic.ravi


def test_keeping_the_same_phone_is_not_a_conflict(clinic: Clinic) -> None:
    same = clinic.patients.get(clinic.asha, NOW).phone
    assert clinic.patients.update(clinic.asha, NOW, phone=same, name="Asha I.").name == "Asha I."


def test_a_wrong_date_of_birth_is_corrected_and_validated(clinic: Clinic) -> None:
    fixed = clinic.patients.update(clinic.asha, NOW, date_of_birth=date(1991, 5, 17))
    assert fixed.date_of_birth == date(1991, 5, 17)
    with pytest.raises(RuleViolation):
        clinic.patients.update(clinic.asha, NOW, date_of_birth=date(2030, 1, 1))
    with pytest.raises(RuleViolation):
        clinic.patients.update(clinic.asha, NOW, name="   ")


def test_updating_an_unknown_patient_is_not_found(clinic: Clinic) -> None:
    with pytest.raises(DomainError) as raised:
        clinic.patients.update(999, NOW, name="Nobody")
    assert raised.value.code is ErrorCode.PATIENT_NOT_FOUND


def test_registering_the_same_person_again_is_flagged_even_with_a_new_phone(
    clinic: Clinic,
) -> None:
    original = clinic.patients.get(clinic.asha, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.patients.create("  asha   IYER ", "9123456780", original.date_of_birth, NOW)
    assert raised.value.code is ErrorCode.POSSIBLE_DUPLICATE
    assert raised.value.details["candidates"] == [
        {"patient_id": clinic.asha, "name": "Asha Iyer", "phone": original.phone}
    ]


def test_a_confirmed_duplicate_is_registered(clinic: Clinic) -> None:
    original = clinic.patients.get(clinic.asha, NOW)
    twin = clinic.patients.create(
        "Asha Iyer", "9123456780", original.date_of_birth, NOW, allow_duplicate=True
    )
    assert twin.id != clinic.asha


def test_the_same_name_with_a_different_birth_date_is_not_a_duplicate(clinic: Clinic) -> None:
    original = clinic.patients.get(clinic.asha, NOW)
    other_day = original.date_of_birth + timedelta(days=1)
    assert clinic.patients.create("Asha Iyer", "9123456780", other_day, NOW).id != clinic.asha


def test_editing_a_name_into_a_duplicate_is_flagged(clinic: Clinic) -> None:
    born = clinic.patients.get(clinic.asha, NOW).date_of_birth
    clinic.patients.update(clinic.ravi, NOW, date_of_birth=born)
    with pytest.raises(ConflictError) as raised:
        clinic.patients.update(clinic.ravi, NOW, name="Asha Iyer")
    assert raised.value.code is ErrorCode.POSSIBLE_DUPLICATE
    allowed = clinic.patients.update(clinic.ravi, NOW, name="Asha Iyer", allow_duplicate=True)
    assert allowed.name == "Asha Iyer"


# ----------------------------------------------------------------------------- waitlist


def full_slot(clinic: Clinic) -> int:
    with clinic.factory() as session, session.begin():
        return add_appointment(session, clinic.rao, clinic.ravi, at(10)).id


def three_waiting(clinic: Clinic) -> tuple[int, int]:
    first = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    second = clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)
    return first.id, second.id


def test_declining_keeps_the_place_and_passes_the_slot_on(clinic: Clinic) -> None:
    booked = full_slot(clinic)
    first, second = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)

    declined = clinic.waitlist.decline(first, NOW)

    assert declined.status == "WAITING"
    states = {e.id: e.status for e in clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)}
    assert states == {first: "WAITING", second: "OFFERED"}


def test_a_declined_slot_is_not_offered_back_to_the_same_patient(clinic: Clinic) -> None:
    booked = full_slot(clinic)
    first, second = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    clinic.waitlist.decline(first, NOW)
    clinic.waitlist.decline(second, NOW)  # nobody else wants it
    states = {e.id: e.status for e in clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW)}
    assert states == {first: "WAITING", second: "WAITING"}  # no loop, no offer


def test_a_declining_patient_is_still_first_in_line_for_the_next_slot(clinic: Clinic) -> None:
    booked = full_slot(clinic)
    first, _ = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    clinic.waitlist.decline(first, NOW)
    with clinic.factory() as session, session.begin():
        other = add_appointment(session, clinic.rao, clinic.ravi, at(11)).id
    clinic.booking.cancel(other, CancelledBy.PATIENT, NOW)
    offered = [e for e in clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, NOW) if e.id == first]
    assert offered[0].offered_start_at == at(11)


def test_declining_without_an_offer_is_refused(clinic: Clinic) -> None:
    entry = clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.waitlist.decline(entry.id, NOW)
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_a_lapsed_offer_passes_to_the_next_patient_when_anyone_looks(clinic: Clinic) -> None:
    booked = full_slot(clinic)
    _, second = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    later = NOW + timedelta(minutes=40)  # the 30 minute hold has run out
    states = {e.id: e.status for e in clinic.waitlist.for_doctor_day(clinic.rao, MONDAY, later)}
    assert states == {second: "OFFERED"}  # the first lapsed and left the queue
    assert clinic.waitlist.for_patient(clinic.asha, later) == []


def test_an_offer_that_lapses_is_passed_on_when_the_late_patient_tries_to_accept(
    clinic: Clinic,
) -> None:
    booked = full_slot(clinic)
    first, second = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.waitlist.accept(first, "Fever", False, NOW + timedelta(minutes=40))
    assert raised.value.code is ErrorCode.OFFER_EXPIRED
    [offer] = clinic.waitlist.for_patient(clinic.meena, NOW + timedelta(minutes=40))
    assert (offer.id, offer.status) == (second, "OFFERED")


def test_leaving_while_holding_an_offer_passes_it_on(clinic: Clinic) -> None:
    booked = full_slot(clinic)
    first, _ = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    clinic.waitlist.leave(first, NOW)
    assert clinic.waitlist.for_patient(clinic.meena, NOW)[0].status == "OFFERED"


def test_two_patients_accepting_different_offers_do_not_interfere(clinic: Clinic) -> None:
    booked = full_slot(clinic)
    first, second = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    results = burst(
        [
            lambda: clinic.waitlist.accept(first, "Fever", False, NOW),
            lambda: clinic.waitlist.accept(second, "Cough", False, NOW),
        ]
    )
    counts = outcomes(results)
    assert counts["OK"] == 1  # one offer was made, so one acceptance can succeed
    assert len([a for a in clinic.appointments() if a.status == "BOOKED"]) == 1


# ----------------------------------------------------------------------------- reports


def test_the_report_counts_each_outcome_once_and_a_reschedule_is_not_a_cancellation(
    clinic: Clinic,
) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(9, day=3), status=Status.COMPLETED)
        add_appointment(session, clinic.rao, clinic.ravi, at(9, 30, day=3), status=Status.NO_SHOW)
        add_appointment(session, clinic.rao, clinic.meena, at(10, day=3), status=Status.CANCELLED)
        add_appointment(
            session, clinic.rao, clinic.asha, at(10, 30, day=3), status=Status.LATE_CANCELLED
        )
    moved = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(11, day=3), "x"), NOW)
    clinic.booking.reschedule(moved.id, at(11, 30, day=3), None, None, NOW)

    report = clinic.records.summary(date(2026, 11, 3), date(2026, 11, 3))
    rao = next(d for d in report.doctors if d.doctor_id == clinic.rao)

    assert (rao.completed, rao.no_show, rao.cancelled, rao.late_cancelled) == (1, 1, 1, 1)
    assert rao.rescheduled == 1
    assert rao.booked == 1  # the new slot
    assert rao.appointments == 6
    assert rao.new_bookings == 5  # the moved-to appointment is not a new booking
    assert rao.no_show_rate == 0.5
    assert rao.capacity_slots == 8  # 09:00-13:00 in 30 minutes
    assert rao.utilisation == round(3 / 8, 4)  # completed, no-show and the new booking took a slot
    assert report.total.appointments == 6


def test_a_leave_day_has_no_capacity_and_no_rates(clinic: Clinic) -> None:
    clinic.availability.put_override(clinic.rao, date(2026, 11, 4), [], "Conference", True, NOW)
    report = clinic.records.summary(date(2026, 11, 4), date(2026, 11, 4))
    rao = next(d for d in report.doctors if d.doctor_id == clinic.rao)
    assert (rao.capacity_slots, rao.utilisation, rao.no_show_rate) == (0, None, None)


def test_report_ranges_are_validated(clinic: Clinic) -> None:
    with pytest.raises(RuleViolation):
        clinic.records.summary(date(2026, 11, 5), date(2026, 11, 4))
    with pytest.raises(RuleViolation):
        clinic.records.summary(date(2026, 1, 1), date(2026, 6, 1))


# ----------------------------------------------------------------------------- export


def test_a_patient_export_holds_the_details_appointments_and_history(clinic: Clinic) -> None:
    booked = clinic.booking.book(command(clinic), NOW)
    clinic.booking.cancel(booked.id, CancelledBy.PATIENT, NOW)
    patient = clinic.patients.get(clinic.asha, NOW)
    export = clinic.records.patient_export(clinic.asha, patient, NOW)
    assert export.patient.id == clinic.asha
    assert [a.id for a in export.appointments] == [booked.id]
    assert [e.kind for e in export.events] == ["BOOKED", "CANCELLED"]


def test_declining_after_the_hold_ran_out_just_closes_the_entry_and_passes_it_on(
    clinic: Clinic,
) -> None:
    booked = full_slot(clinic)
    first, second = three_waiting(clinic)
    clinic.booking.cancel(booked, CancelledBy.PATIENT, NOW)
    later = NOW + timedelta(minutes=45)
    assert clinic.waitlist.decline(first, later).status == "EXPIRED"
    assert clinic.waitlist.for_patient(clinic.meena, later)[0].id == second
