"""Consent records, erasure on request and the retention rule."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.errors import ConflictError, ErrorCode
from app.domain.model import CancelledBy, Status
from app.services.patient_service import ERASED_NAME, ERASED_REASON, erased_phone
from app.services.views import BookCommand
from scripts.purge_inactive import main as purge_main
from scripts.purge_inactive import purge
from tests.factories import add_appointment
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration

BORN = date(1990, 1, 1)


def test_consent_is_recorded_when_given_and_not_required(clinic: Clinic) -> None:
    without = clinic.patients.create("No Consent", "9000011111", BORN, NOW)
    with_it = clinic.patients.create("Has Consent", "9000022222", BORN, NOW, consent=True)
    assert without.consent_at is None
    assert with_it.consent_at == NOW


def test_consent_can_be_recorded_later_and_replaces_the_earlier_time(clinic: Clinic) -> None:
    first = clinic.patients.record_consent(clinic.asha, NOW)
    later = clinic.patients.record_consent(clinic.asha, NOW + timedelta(days=1))
    assert (first.consent_at, later.consent_at) == (NOW, NOW + timedelta(days=1))


def test_erasing_replaces_every_identifier_and_keeps_the_anonymous_history(
    clinic: Clinic,
) -> None:
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "Chest pain"), NOW)
    clinic.booking.cancel(booked.id, CancelledBy.PATIENT, NOW)

    erased = clinic.patients.erase(clinic.asha, NOW)

    assert erased.name == ERASED_NAME
    assert erased.phone == erased_phone(clinic.asha)
    assert erased.date_of_birth.year == 1900
    assert erased.erased_at == NOW
    kept = clinic.appointment(booked.id)
    assert (kept.reason, kept.status) == (ERASED_REASON, "CANCELLED")
    export = repr(clinic.records.patient_export(clinic.asha, erased, NOW))
    assert "Asha" not in export
    assert "Chest pain" not in export


def test_erasing_twice_changes_nothing(clinic: Clinic) -> None:
    first = clinic.patients.erase(clinic.meena, NOW)
    second = clinic.patients.erase(clinic.meena, NOW + timedelta(days=5))
    assert second.erased_at == first.erased_at == NOW


def test_an_upcoming_appointment_blocks_erasure_until_it_is_cancelled(clinic: Clinic) -> None:
    booked = clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(11), "Cough"), NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.patients.erase(clinic.ravi, NOW)
    assert raised.value.code is ErrorCode.PATIENT_HAS_UPCOMING
    assert raised.value.details["has_upcoming_appointment"] is True
    assert clinic.patients.get(clinic.ravi, NOW).name == "Ravi Kumar"  # untouched

    clinic.booking.cancel(booked.id, CancelledBy.CLINIC, NOW)
    assert clinic.patients.erase(clinic.ravi, NOW).name == ERASED_NAME


def test_a_waitlist_place_blocks_erasure(clinic: Clinic) -> None:
    clinic.waitlist.join(clinic.rao, clinic.meena, MONDAY, NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.patients.erase(clinic.meena, NOW)
    assert raised.value.details["on_waitlist"] is True


def test_an_erased_patient_cannot_be_booked_edited_or_waitlisted(clinic: Clinic) -> None:
    clinic.patients.erase(clinic.asha, NOW)
    attempts = (
        lambda: clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW),
        lambda: clinic.patients.update(clinic.asha, NOW, name="Back Again"),
        lambda: clinic.waitlist.join(clinic.rao, clinic.asha, MONDAY, NOW),
        lambda: clinic.patients.record_consent(clinic.asha, NOW),
    )
    for attempt in attempts:
        with pytest.raises(ConflictError) as raised:
            attempt()
        assert raised.value.code is ErrorCode.PATIENT_ERASED


def test_erased_patients_leave_search_and_duplicate_matching(clinic: Clinic) -> None:
    clinic.patients.erase(clinic.asha, NOW)
    found = clinic.patients.search(phone=None, name_prefix="Erased", limit=10, offset=0)
    assert found.total == 0
    # the same name and birth date can now be registered without a duplicate warning
    again = clinic.patients.create("Asha Iyer", "9000033333", BORN, NOW)
    assert again.id != clinic.asha


def test_two_erased_patients_do_not_collide_on_the_unique_phone(clinic: Clinic) -> None:
    clinic.patients.erase(clinic.asha, NOW)
    clinic.patients.erase(clinic.ravi, NOW)
    phones = {clinic.patients.get(p, NOW).phone for p in (clinic.asha, clinic.ravi)}
    assert len(phones) == 2


def test_retention_lists_only_patients_with_no_recent_activity(clinic: Clinic) -> None:
    long_after = NOW + timedelta(days=400)
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.rao, clinic.asha, at(10), status=Status.COMPLETED)
    everyone = [clinic.asha, clinic.ravi, clinic.meena]
    assert clinic.patients.inactive_ids(long_after, 365) == everyone
    assert clinic.patients.inactive_ids(NOW + timedelta(days=100), 365) == []


def test_retention_never_touches_a_patient_with_an_upcoming_booking(clinic: Clinic) -> None:
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10, day=3), "x"), NOW)
    ids = clinic.patients.inactive_ids(NOW + timedelta(days=400), 30)
    assert clinic.asha not in ids


def test_the_purge_is_a_dry_run_until_told_to_apply(clinic: Clinic) -> None:
    later = NOW + timedelta(days=400)
    everyone = [clinic.asha, clinic.ravi, clinic.meena]
    assert purge(clinic.patients, later, 365, apply=False) == everyone
    assert clinic.patients.get(clinic.asha, later).erased_at is None
    assert purge(clinic.patients, later, 365, apply=True) == everyone
    assert clinic.patients.get(clinic.asha, later).erased_at == later
    assert purge(clinic.patients, later, 365, apply=True) == []  # nothing left to erase


def test_the_purge_command_refuses_a_period_that_could_erase_recent_patients() -> None:
    with pytest.raises(SystemExit):
        purge_main(["--days", "5"])
