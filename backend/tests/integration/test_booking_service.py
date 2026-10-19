"""BookingService against PostgreSQL: booking (T-B), cancelling (T-C), marking (T-M),
rescheduling (T-R) and the deposit flag (T-D).

Rows that only set the scene (strikes in the past, a full day) are inserted through the factories,
which bypass the rules; everything under test goes through the service.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.errors import ConflictError, DomainError, ErrorCode, NotFoundError
from app.domain.model import CancelledBy, Status
from app.services.views import AppointmentView, BookCommand
from tests.factories import add_appointment, add_override
from tests.helpers import ist
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


def book(
    clinic: Clinic,
    start: datetime,
    *,
    doctor: int | None = None,
    patient: int | None = None,
    deposit_confirmed: bool = False,
    now: datetime = NOW,
) -> AppointmentView:
    command = BookCommand(
        doctor_id=doctor or clinic.rao,
        patient_id=patient or clinic.asha,
        start_at=start,
        reason="Check-up",
        deposit_confirmed=deposit_confirmed,
    )
    return clinic.booking.book(command, now)


def rejected(clinic: Clinic, start: datetime, **kwargs: object) -> DomainError:
    with pytest.raises(DomainError) as raised:
        book(clinic, start, **kwargs)  # type: ignore[arg-type]
    return raised.value


def flag_patient(clinic: Clinic, patient: int) -> None:
    """Two strikes before NOW: a no-show on 29 Oct 10:00 and a late cancel on 28 Oct 15:10."""
    with clinic.factory() as session, session.begin():
        add_appointment(
            session, clinic.rao, patient, ist(2026, 10, 29, 10, 0), status=Status.NO_SHOW
        )
        late_start = ist(2026, 10, 28, 16, 30)
        add_appointment(
            session,
            clinic.rao,
            patient,
            late_start,
            status=Status.LATE_CANCELLED,
            cancelled_at=ist(2026, 10, 28, 15, 10),
            status_changed_at=ist(2026, 10, 28, 15, 10),
        )


# ------------------------------------------------------------------------------------ booking


def test_a_booking_gets_its_end_from_the_doctors_slot_length(clinic: Clinic) -> None:
    view = book(clinic, at(10))
    assert view.status is Status.BOOKED
    assert (view.start_at, view.end_at) == (at(10), at(10, 30))
    assert view.allowed_actions == ("check-in", "cancel", "reschedule")
    assert view.needs_attention is False
    assert (view.doctor_name, view.patient_name) == ("Dr. Rao", "Asha Iyer")
    assert (view.deposit_required_at_booking, view.deposit_confirmed) == (False, False)


def test_a_start_with_another_utc_offset_is_stored_as_the_same_instant(clinic: Clinic) -> None:
    """T-B15: 03:30 UTC is 09:00 in India."""
    view = book(clinic, datetime(2026, 11, 2, 3, 30, tzinfo=UTC))
    assert view.start_at == at(9)


@pytest.mark.parametrize(
    ("start", "now", "code"),
    [
        (at(10), at(10, 1), ErrorCode.BOOKING_IN_PAST),  # T-W01
        (at(10), at(10), ErrorCode.BOOKING_IN_PAST),  # a start equal to now is past
        (at(10, day=2) + timedelta(days=61), NOW, ErrorCode.BOOKING_TOO_FAR),  # T-W04
        (at(10, 15), NOW, ErrorCode.OFF_GRID),  # T-B01
        (at(13), NOW, ErrorCode.OUTSIDE_AVAILABILITY),  # T-B03
        (at(8, 30), NOW, ErrorCode.OUTSIDE_AVAILABILITY),  # T-B04
        (at(10, day=7), NOW, ErrorCode.OUTSIDE_AVAILABILITY),  # a Saturday: no weekly window
    ],
    ids=["past", "now", "too far", "off grid", "after hours", "before hours", "saturday"],
)
def test_each_rule_is_reachable_through_the_service(
    clinic: Clinic, start: datetime, now: datetime, code: ErrorCode
) -> None:
    assert rejected(clinic, start, now=now).code is code
    assert clinic.appointments() == []  # a refusal writes nothing


def test_the_last_slot_of_a_window_can_be_booked(clinic: Clinic) -> None:
    """T-B02: 12:30-13:00 ends exactly when the window ends."""
    assert book(clinic, at(12, 30)).end_at == at(13)


def test_a_leave_day_override_closes_the_whole_day(clinic: Clinic) -> None:
    """T-B05"""
    with clinic.factory() as session, session.begin():
        add_override(session, clinic.rao, MONDAY, [])
    assert rejected(clinic, at(10)).code is ErrorCode.OUTSIDE_AVAILABILITY


def test_an_override_replaces_the_weekly_hours_on_both_sides(clinic: Clinic) -> None:
    """T-B14: weekly 09:00-13:00 but an override of 11:00-12:00 for this Monday."""
    with clinic.factory() as session, session.begin():
        add_override(session, clinic.rao, MONDAY, [(660, 720)])
    assert rejected(clinic, at(10)).code is ErrorCode.OUTSIDE_AVAILABILITY
    assert rejected(clinic, at(12)).code is ErrorCode.OUTSIDE_AVAILABILITY
    assert book(clinic, at(11)).start_at == at(11)


def test_an_extra_working_day_can_be_booked(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_override(session, clinic.rao, date(2026, 11, 7), [(600, 660)])  # a Saturday
    assert book(clinic, at(10, day=7)).start_at == at(10, day=7)


def test_the_same_slot_cannot_be_booked_twice(clinic: Clinic) -> None:
    """T-B06"""
    book(clinic, at(10))
    error = rejected(clinic, at(10), patient=clinic.ravi)
    assert isinstance(error, ConflictError)
    assert error.code is ErrorCode.SLOT_TAKEN
    assert error.details["same_patient"] is False
    assert len(clinic.appointments()) == 1


def test_a_double_click_is_reported_as_the_same_patient(clinic: Clinic) -> None:
    book(clinic, at(10))
    error = rejected(clinic, at(10))
    assert error.code is ErrorCode.SLOT_TAKEN
    assert error.details["same_patient"] is True


def test_adjacent_slots_do_not_conflict(clinic: Clinic) -> None:
    """T-B07"""
    book(clinic, at(10))
    assert book(clinic, at(10, 30), patient=clinic.ravi).start_at == at(10, 30)


def test_a_patient_cannot_be_in_two_places_at_once(clinic: Clinic) -> None:
    """T-B08: Dr. Rao 10:00-10:30 and Dr. Menon 10:15-10:30 overlap for the same patient."""
    book(clinic, at(10))
    error = rejected(clinic, at(10, 15), doctor=clinic.menon)
    assert error.code is ErrorCode.PATIENT_OVERLAP
    assert book(clinic, at(10, 30), doctor=clinic.menon).start_at == at(10, 30)


def test_the_daily_cap_counts_active_appointments_only(clinic: Clinic) -> None:
    """T-B09 to T-B11 with Dr. Rao's cap of 6: three active and two inactive appointments."""
    statuses = [
        Status.BOOKED,
        Status.COMPLETED,
        Status.NO_SHOW,
        Status.CANCELLED,
        Status.LATE_CANCELLED,
    ]
    with clinic.factory() as session, session.begin():
        for index, status in enumerate(statuses):
            start = at(9) + timedelta(minutes=30 * index)
            add_appointment(session, clinic.rao, clinic.ravi, start, status=status)
    for start in (at(11, 30), at(12), at(12, 30)):  # 3 active + 3 = 6, exactly the cap
        book(clinic, start, patient=clinic.meena)
    # 11:00 is free (that appointment was late-cancelled) but the day is full
    assert rejected(clinic, at(11), patient=clinic.asha).code is ErrorCode.DAILY_CAP_REACHED


def test_unknown_doctors_and_patients_are_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError) as raised:
        book(clinic, at(10), doctor=999)
    assert raised.value.code is ErrorCode.DOCTOR_NOT_FOUND
    with pytest.raises(NotFoundError) as raised:
        book(clinic, at(10), patient=999)
    assert raised.value.code is ErrorCode.PATIENT_NOT_FOUND


# ------------------------------------------------------------------------------- the deposit


def test_one_strike_does_not_require_a_deposit(clinic: Clinic) -> None:
    """T-D01"""
    with clinic.factory() as session, session.begin():
        add_appointment(
            session, clinic.rao, clinic.ravi, ist(2026, 10, 28, 10), status=Status.NO_SHOW
        )
    assert book(clinic, at(10), patient=clinic.ravi).deposit_required_at_booking is False


def test_a_flagged_patient_must_confirm_the_deposit(clinic: Clinic) -> None:
    """T-D02"""
    flag_patient(clinic, clinic.ravi)
    error = rejected(clinic, at(10), patient=clinic.ravi)
    assert error.code is ErrorCode.DEPOSIT_REQUIRED
    assert error.details["required_until"] == "2026-11-27T15:10:00+05:30"
    strike_ids = [a.id for a in clinic.appointments()]
    assert [r["appointment_id"] for r in error.details["reasons"]] == strike_ids
    assert len(clinic.appointments()) == 2  # only the two strikes


def test_confirming_the_deposit_allows_the_booking_and_records_both_flags(clinic: Clinic) -> None:
    """T-D03"""
    flag_patient(clinic, clinic.ravi)
    view = book(clinic, at(10), patient=clinic.ravi, deposit_confirmed=True)
    assert (view.deposit_required_at_booking, view.deposit_confirmed) == (True, True)


def test_confirming_without_being_flagged_is_stored_as_sent(clinic: Clinic) -> None:
    view = book(clinic, at(10), deposit_confirmed=True)
    assert (view.deposit_required_at_booking, view.deposit_confirmed) == (False, True)


def test_the_flag_follows_the_test_clock(clinic: Clinic) -> None:
    """Strikes age out: a month later the same patient can book without a deposit."""
    flag_patient(clinic, clinic.ravi)
    later = ist(2026, 11, 28, 8, 0)  # one day after required_until
    view = book(clinic, at(10, day=30), patient=clinic.ravi, now=later)
    assert view.deposit_required_at_booking is False


# ---------------------------------------------------------------------------------- cancelling


def seed_booked(clinic: Clinic, start: datetime, *, patient: int | None = None) -> int:
    with clinic.factory() as session, session.begin():
        return add_appointment(session, clinic.rao, patient or clinic.asha, start).id


@pytest.mark.parametrize(
    ("now", "status"),
    [
        (ist(2026, 11, 2, 10, 0, 0), Status.CANCELLED),  # T-C01 exactly two hours before
        (ist(2026, 11, 2, 10, 1), Status.LATE_CANCELLED),  # T-C02
        (ist(2026, 11, 2, 9, 59), Status.CANCELLED),  # T-C03
    ],
)
def test_cancelling_around_the_two_hour_line(clinic: Clinic, now: datetime, status: Status) -> None:
    appointment_id = seed_booked(clinic, at(12))
    result = clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, now)
    assert result.appointment.status is status
    assert result.late is (status is Status.LATE_CANCELLED)
    stored = clinic.appointment(appointment_id)
    assert (stored.cancelled_at, stored.status_changed_at) == (now, now)
    assert stored.cancelled_by == "PATIENT"
    expected = ("undo-cancel",) if status is Status.CANCELLED else ("correct", "undo-cancel")
    assert result.appointment.allowed_actions == expected


def test_a_cancelled_slot_can_be_booked_again(clinic: Clinic) -> None:
    appointment_id = seed_booked(clinic, at(12))
    clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, NOW)
    assert book(clinic, at(12), patient=clinic.ravi).start_at == at(12)


def test_cancelling_at_the_start_is_a_late_cancellation(clinic: Clinic) -> None:
    """T-C04 as the statement words it: later than 2 hours before the start is late."""
    appointment_id = seed_booked(clinic, at(12))
    result = clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, at(12))
    assert (result.late, result.appointment.status) == (True, Status.LATE_CANCELLED)
    assert result.deposit.reasons[0].appointment_id == appointment_id


def test_a_clinic_cancellation_is_never_late_and_never_a_strike(clinic: Clinic) -> None:
    """T-C05 and T-D07"""
    ids = [seed_booked(clinic, at(12)), seed_booked(clinic, at(12, 30))]
    results = [
        clinic.booking.cancel(i, CancelledBy.CLINIC, at(11, 45))
        for i in ids  # 15 minutes before
    ]
    assert [r.appointment.status for r in results] == [Status.CANCELLED, Status.CANCELLED]
    assert all(r.deposit.required is False and r.deposit.reasons == () for r in results)


def test_cancelling_twice_is_an_invalid_transition(clinic: Clinic) -> None:
    """T-C06"""
    appointment_id = seed_booked(clinic, at(12))
    clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, NOW)
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_two_late_cancellations_flag_the_patient_and_the_response_says_so(clinic: Clinic) -> None:
    first, second = seed_booked(clinic, at(12)), seed_booked(clinic, at(12, 30))
    one = clinic.booking.cancel(first, CancelledBy.PATIENT, at(11, 30))
    assert one.deposit.required is False
    two = clinic.booking.cancel(second, CancelledBy.PATIENT, at(11, 45))
    assert two.deposit.required is True
    assert two.deposit.required_until == at(11, 30) + timedelta(days=30)
    assert rejected(clinic, at(10, day=3), now=at(12, 0)).code is ErrorCode.DEPOSIT_REQUIRED


def test_cancelling_an_unknown_appointment_is_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError) as raised:
        clinic.booking.cancel(999, CancelledBy.PATIENT, NOW)
    assert raised.value.code is ErrorCode.APPOINTMENT_NOT_FOUND


# ----------------------------------------------------------------------------------- marking


def test_an_appointment_cannot_be_marked_before_it_starts(clinic: Clinic) -> None:
    """T-M01"""
    appointment_id = seed_booked(clinic, at(12))
    for mark in (clinic.booking.no_show, clinic.booking.complete):
        with pytest.raises(ConflictError) as raised:
            mark(appointment_id, at(11, 59))
        assert raised.value.code is ErrorCode.TOO_EARLY_TO_MARK


def test_completing_and_no_show_at_or_after_the_start(clinic: Clinic) -> None:
    done, missed = seed_booked(clinic, at(10)), seed_booked(clinic, at(10, 30))
    completed = clinic.booking.complete(done, at(10))
    assert completed.status is Status.COMPLETED
    assert completed.allowed_actions == ("correct",)
    assert clinic.appointment(done).status_changed_at == at(10)
    assert clinic.booking.no_show(missed, at(11)).status is Status.NO_SHOW


def test_a_cancelled_appointment_cannot_be_completed(clinic: Clinic) -> None:
    """T-M02"""
    appointment_id = seed_booked(clinic, at(12))
    clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.complete(appointment_id, at(12, 30))
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_a_no_show_counts_as_a_strike_from_the_appointment_start(clinic: Clinic) -> None:
    first, second = seed_booked(clinic, at(9)), seed_booked(clinic, at(9, 30))
    clinic.booking.no_show(first, at(10))
    clinic.booking.no_show(second, at(10))
    error = rejected(clinic, at(10, day=3), now=at(10, 5))
    assert error.code is ErrorCode.DEPOSIT_REQUIRED
    assert error.details["required_until"] == "2026-12-02T09:00:00+05:30"  # older strike + 30 days
    assert [r["appointment_id"] for r in error.details["reasons"]] == [second, first]
    assert [r["type"] for r in error.details["reasons"]] == ["NO_SHOW", "NO_SHOW"]


# --------------------------------------------------------------------------------- rescheduling


def test_rescheduling_to_a_free_slot_swaps_the_appointments(clinic: Clinic) -> None:
    """T-R02"""
    old_id = seed_booked(clinic, at(10))
    result = clinic.booking.reschedule(old_id, at(10, 30), None, None, NOW)
    assert result.old.status is Status.CANCELLED
    assert result.old.rescheduled_to_id == result.new.id
    assert (result.new.status, result.new.start_at) == (Status.BOOKED, at(10, 30))
    assert result.new.reason == "Check-up"  # copied from the old appointment


def test_rescheduling_to_a_taken_slot_leaves_the_old_appointment_untouched(clinic: Clinic) -> None:
    """T-R01"""
    old_id = seed_booked(clinic, at(10))
    seed_booked(clinic, at(11), patient=clinic.ravi)
    with pytest.raises(ConflictError) as raised:
        clinic.booking.reschedule(old_id, at(11), None, None, NOW)
    assert raised.value.code is ErrorCode.SLOT_TAKEN
    stored = clinic.appointment(old_id)
    assert (stored.status, stored.cancelled_at, stored.rescheduled_to_id) == ("BOOKED", None, None)
    assert len(clinic.appointments()) == 2


def test_the_new_slot_may_overlap_the_patients_own_old_slot(clinic: Clinic) -> None:
    """T-R03: Dr. Rao 10:00-10:30 moved to Dr. Menon 10:15-10:30."""
    old_id = seed_booked(clinic, at(10))
    result = clinic.booking.reschedule(old_id, at(10, 15), clinic.menon, None, NOW)
    assert (result.new.doctor_id, result.new.start_at) == (clinic.menon, at(10, 15))


def test_rescheduling_to_the_same_slot_is_refused_and_costs_nothing(clinic: Clinic) -> None:
    """T-R04: even a late no-op must not become a strike."""
    old_id = seed_booked(clinic, at(10))
    with pytest.raises(DomainError) as raised:
        clinic.booking.reschedule(old_id, at(10), None, None, at(9))  # 1 hour before: would be late
    assert raised.value.code is ErrorCode.RESCHEDULE_NO_CHANGE
    assert clinic.appointment(old_id).status == "BOOKED"


def test_a_late_reschedule_is_a_late_cancellation(clinic: Clinic) -> None:
    """T-R05"""
    old_id = seed_booked(clinic, at(10))
    result = clinic.booking.reschedule(
        old_id, at(11), None, None, at(8, 30), acknowledge_late=True
    )  # 1.5 h before, and the patient confirmed the penalty
    assert result.old.status is Status.LATE_CANCELLED
    assert result.new.status is Status.BOOKED


def test_the_deposit_check_ignores_the_strike_made_by_the_move_itself(clinic: Clinic) -> None:
    """A-11: one earlier strike plus this late move makes two, but the move is still allowed."""
    with clinic.factory() as session, session.begin():
        add_appointment(
            session, clinic.rao, clinic.asha, ist(2026, 10, 28, 10), status=Status.NO_SHOW
        )
    old_id = seed_booked(clinic, at(10))
    result = clinic.booking.reschedule(
        old_id, at(11), None, None, at(9), acknowledge_late=True
    )  # late: 1 h before
    assert result.new.deposit_required_at_booking is False
    error = rejected(clinic, at(10, day=3), now=at(9, 5))  # now flagged for later bookings
    assert error.code is ErrorCode.DEPOSIT_REQUIRED


def test_a_flagged_patient_inherits_the_confirmed_deposit(clinic: Clinic) -> None:
    """T-D08"""
    flag_patient(clinic, clinic.ravi)
    booked = book(clinic, at(10), patient=clinic.ravi, deposit_confirmed=True)
    result = clinic.booking.reschedule(booked.id, at(11), None, None, NOW)
    assert (result.new.deposit_required_at_booking, result.new.deposit_confirmed) == (True, True)


def test_a_flagged_patient_cannot_withdraw_the_deposit_when_rescheduling(clinic: Clinic) -> None:
    flag_patient(clinic, clinic.ravi)
    booked = book(clinic, at(10), patient=clinic.ravi, deposit_confirmed=True)
    with pytest.raises(DomainError) as raised:
        clinic.booking.reschedule(booked.id, at(11), None, False, NOW)
    assert raised.value.code is ErrorCode.DEPOSIT_REQUIRED
    assert clinic.appointment(booked.id).status == "BOOKED"


def test_rescheduling_to_an_unknown_doctor_changes_nothing(clinic: Clinic) -> None:
    old_id = seed_booked(clinic, at(10))
    with pytest.raises(NotFoundError) as raised:
        clinic.booking.reschedule(old_id, at(11), 999, None, NOW)
    assert raised.value.code is ErrorCode.DOCTOR_NOT_FOUND
    assert clinic.appointment(old_id).status == "BOOKED"


def test_a_started_or_finished_appointment_cannot_be_rescheduled(clinic: Clinic) -> None:
    started = seed_booked(clinic, at(10))
    with pytest.raises(ConflictError) as raised:
        clinic.booking.reschedule(started, at(11), None, None, at(10, 5))
    assert raised.value.code is ErrorCode.APPOINTMENT_ALREADY_STARTED
    clinic.booking.complete(started, at(10, 5))
    with pytest.raises(ConflictError) as raised:
        clinic.booking.reschedule(started, at(11), None, None, at(10, 6))
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


# ------------------------------------------------------------------------------ recurring


def series(
    clinic: Clinic,
    start: datetime,
    *,
    every: int = 7,
    count: int = 3,
    patient: int | None = None,
) -> list[AppointmentView]:
    command = BookCommand(clinic.rao, patient or clinic.asha, start, "Review")
    return clinic.booking.book_series(command, every, count, NOW)


def test_a_weekly_series_books_every_occurrence_at_the_same_india_time(clinic: Clinic) -> None:
    views = series(clinic, at(10), count=3)
    assert [v.start_at for v in views] == [at(10), at(10, day=9), at(10, day=16)]
    assert all(v.status is Status.BOOKED for v in views)


def test_one_bad_occurrence_rolls_back_the_whole_series(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.ravi, at(10, day=16))  # the third week is taken
    with pytest.raises(DomainError) as raised:
        series(clinic, at(10), count=3)
    assert raised.value.code is ErrorCode.SLOT_TAKEN
    assert raised.value.details["occurrence"] == 3
    assert "Occurrence 3 of 3" in raised.value.message
    assert [a.patient_id for a in clinic.appointments()] == [clinic.ravi]  # nothing else was kept


def test_a_series_that_leaves_the_booking_window_is_refused_as_a_whole(clinic: Clinic) -> None:
    with pytest.raises(DomainError) as raised:
        series(clinic, at(10), every=30, count=4)  # the fourth is 90 days ahead
    assert raised.value.code is ErrorCode.BOOKING_TOO_FAR
    assert raised.value.details["occurrence"] == 4
    assert clinic.appointments() == []


def test_a_series_counts_toward_the_daily_cap_as_it_goes(clinic: Clinic) -> None:
    clinic.doctors.update(clinic.rao, NOW, daily_cap=1)
    series(clinic, at(10), every=1, count=2)  # one a day on two days: fine
    with pytest.raises(DomainError) as raised:
        series(clinic, at(10, 30), every=7, count=2, patient=clinic.ravi)  # the first day is full
    assert raised.value.code is ErrorCode.DAILY_CAP_REACHED
    assert raised.value.details["occurrence"] == 1


def test_a_flagged_patient_needs_the_deposit_for_a_series_too(clinic: Clinic) -> None:
    flag_patient(clinic, clinic.ravi)
    with pytest.raises(DomainError) as raised:
        series(clinic, at(10), patient=clinic.ravi)
    assert raised.value.code is ErrorCode.DEPOSIT_REQUIRED
