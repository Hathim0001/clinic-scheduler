"""DoctorService and PatientService against PostgreSQL (FR-001, FR-004, A-06, A-15, A-24)."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.errors import ConflictError, DomainError, ErrorCode, NotFoundError, RuleViolation
from app.domain.model import Status
from app.services.views import BookCommand
from tests.factories import add_appointment, add_override, add_patient
from tests.helpers import ist
from tests.integration.conftest import MONDAY, NOW, Clinic, at

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------------------------ doctors


def test_doctors_are_created_listed_and_fetched(clinic: Clinic) -> None:
    created = clinic.doctors.create("  Dr. Iyer  ", "Paediatrics", 15, 12)
    assert (created.name, created.speciality, created.slot_length_min, created.daily_cap) == (
        "Dr. Iyer",
        "Paediatrics",
        15,
        12,
    )
    assert clinic.doctors.get(created.id) == created
    assert [d.name for d in clinic.doctors.list()] == ["Dr. Rao", "Dr. Menon", "Dr. Iyer"]


@pytest.mark.parametrize(
    ("name", "speciality", "slot", "cap", "field"),
    [
        ("   ", "General", 30, 10, "name"),
        ("x" * 101, "General", 30, 10, "name"),
        ("Dr. A", "", 30, 10, "speciality"),
        ("Dr. A", "General", 20, 10, "slot_length_min"),
        ("Dr. A", "General", 30, 0, "daily_cap"),
        ("Dr. A", "General", 30, 97, "daily_cap"),
    ],
)
def test_invalid_doctors_are_refused(
    clinic: Clinic, name: str, speciality: str, slot: int, cap: int, field: str
) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.doctors.create(name, speciality, slot, cap)
    assert raised.value.code is ErrorCode.VALIDATION_ERROR
    assert raised.value.details["field"] == field
    assert len(clinic.doctors.list()) == 2


def test_a_doctors_details_can_be_changed(clinic: Clinic) -> None:
    changed = clinic.doctors.update(
        clinic.rao, NOW, name="Dr. R. Rao", speciality="Cardiology", daily_cap=8
    )
    assert (changed.name, changed.speciality, changed.daily_cap) == ("Dr. R. Rao", "Cardiology", 8)
    assert changed.slot_length_min == 30  # untouched


def test_updating_an_unknown_doctor_is_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError) as raised:
        clinic.doctors.update(999, NOW, name="Nobody")
    assert raised.value.code is ErrorCode.DOCTOR_NOT_FOUND


def test_the_slot_length_can_change_when_nothing_depends_on_it(clinic: Clinic) -> None:
    changed = clinic.doctors.update(clinic.menon, NOW, slot_length_min=30)
    assert changed.slot_length_min == 30
    slots = clinic.availability.free_slots(clinic.menon, MONDAY, None, NOW).slots
    assert slots[:2] == (at(9), at(9, 30))  # the grid follows the new length


def test_the_slot_length_is_locked_while_future_bookings_exist(clinic: Clinic) -> None:
    """A-06"""
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.menon, clinic.asha, at(10), minutes=15)
    with pytest.raises(ConflictError) as raised:
        clinic.doctors.update(clinic.menon, NOW, slot_length_min=30)
    assert raised.value.code is ErrorCode.SLOT_LENGTH_LOCKED
    assert raised.value.details == {"reason": "FUTURE_APPOINTMENTS", "appointments": 1}
    assert clinic.doctors.get(clinic.menon).slot_length_min == 15


def test_past_and_finished_appointments_do_not_lock_the_slot_length(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(session, clinic.menon, clinic.asha, at(10), minutes=15)  # booked, past
        add_appointment(
            session, clinic.menon, clinic.ravi, at(11), minutes=15, status=Status.NO_SHOW
        )
    later = at(12)  # after both
    assert clinic.doctors.update(clinic.menon, later, slot_length_min=30).slot_length_min == 30


def test_the_slot_length_is_locked_when_windows_would_fall_off_the_grid(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_override(session, clinic.menon, date(2026, 11, 10), [(555, 600)])  # 09:15-10:00
    with pytest.raises(ConflictError) as raised:
        clinic.doctors.update(clinic.menon, NOW, slot_length_min=30)
    assert raised.value.code is ErrorCode.SLOT_LENGTH_LOCKED
    assert raised.value.details == {"reason": "WINDOWS_OFF_GRID"}


def test_an_invalid_slot_length_is_refused_before_the_lock_checks(clinic: Clinic) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.doctors.update(clinic.menon, NOW, slot_length_min=20)
    assert raised.value.code is ErrorCode.VALIDATION_ERROR


def test_lowering_the_cap_never_cancels_anything(clinic: Clinic) -> None:
    """A-24"""
    with clinic.factory() as session, session.begin():
        for index, start in enumerate((at(9), at(9, 30), at(10))):
            add_appointment(
                session, clinic.rao, [clinic.asha, clinic.ravi, clinic.meena][index], start
            )
    clinic.doctors.update(clinic.rao, NOW, daily_cap=1)
    assert [a.status for a in clinic.appointments()] == ["BOOKED"] * 3
    with pytest.raises(DomainError) as raised:
        clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(11), "Check"), NOW)
    assert raised.value.code is ErrorCode.DAILY_CAP_REACHED


# ----------------------------------------------------------------------------------- patients


@pytest.mark.parametrize(
    "phone",
    ["98765 43210", "+91-98765-43210", "09876543210", "919876543210", "(98765) 43210"],
)
def test_the_usual_ways_of_typing_a_phone_are_stored_in_one_form(
    clinic: Clinic, phone: str
) -> None:
    """T-X13"""
    created = clinic.patients.create("  Kiran Bose ", phone, date(1985, 4, 2), NOW)
    assert (created.name, created.phone) == ("Kiran Bose", "+919876543210")
    assert created.deposit is not None
    assert created.deposit.required is False


@pytest.mark.parametrize(
    "phone", ["1234567890", "+9198765", "' OR 1=1--", "9876543210; DROP TABLE patients", ""]
)
def test_bad_phones_are_refused(clinic: Clinic, phone: str) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.patients.create("Kiran Bose", phone, date(1985, 4, 2), NOW)
    assert raised.value.code is ErrorCode.VALIDATION_ERROR
    assert raised.value.details["field"] == "phone"


@pytest.mark.parametrize(
    ("born", "ok"),
    [
        (date(1899, 12, 31), False),
        (date(1900, 1, 1), True),
        (date(2026, 11, 2), True),  # today, by the clock
        (date(2026, 11, 3), False),  # tomorrow
    ],
)
def test_the_date_of_birth_is_checked_against_the_clock(
    clinic: Clinic, born: date, ok: bool
) -> None:
    if ok:
        assert clinic.patients.create("Baby Das", "9811111111", born, NOW).date_of_birth == born
    else:
        with pytest.raises(RuleViolation) as raised:
            clinic.patients.create("Baby Das", "9811111111", born, NOW)
        assert raised.value.details["field"] == "date_of_birth"


def test_a_name_must_have_visible_characters(clinic: Clinic) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.patients.create("    ", "9811111111", date(1990, 1, 1), NOW)
    assert raised.value.details["field"] == "name"


def test_the_same_phone_in_another_format_is_taken(clinic: Clinic) -> None:
    clinic.patients.create("First", "98765 43210", date(1990, 1, 1), NOW)
    with pytest.raises(ConflictError) as raised:
        clinic.patients.create("Second", "+91 9876543210", date(1991, 1, 1), NOW)
    assert raised.value.code is ErrorCode.PHONE_TAKEN
    assert isinstance(raised.value.details["patient_id"], int)


def test_a_patient_shows_the_deposit_block_with_the_strikes(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_appointment(
            session, clinic.rao, clinic.ravi, ist(2026, 10, 29, 10), status=Status.NO_SHOW
        )
        add_appointment(
            session,
            clinic.rao,
            clinic.ravi,
            ist(2026, 10, 28, 16, 30),
            status=Status.LATE_CANCELLED,
            cancelled_at=ist(2026, 10, 28, 15, 10),
            status_changed_at=ist(2026, 10, 28, 15, 10),
        )
    deposit = clinic.patients.get(clinic.ravi, NOW).deposit
    assert deposit is not None
    assert deposit.required is True
    assert deposit.required_until == ist(2026, 11, 27, 15, 10)
    assert [e.kind for e in deposit.reasons] == [Status.NO_SHOW, Status.LATE_CANCELLED]
    unflagged = clinic.patients.get(clinic.asha, NOW).deposit
    assert unflagged is not None
    assert unflagged.required is False


def test_an_unknown_patient_is_not_found(clinic: Clinic) -> None:
    with pytest.raises(NotFoundError) as raised:
        clinic.patients.get(999, NOW)
    assert raised.value.code is ErrorCode.PATIENT_NOT_FOUND


def search(
    clinic: Clinic,
    *,
    phone: str | None = None,
    name_prefix: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[str]:
    page = clinic.patients.search(phone=phone, name_prefix=name_prefix, limit=limit, offset=offset)
    return [p.name for p in page.items]


def test_patients_are_found_by_phone_in_any_format(clinic: Clinic) -> None:
    assert search(clinic, phone="090000 00001") == ["Asha Iyer"]
    assert search(clinic, phone="+91-9000000002") == ["Ravi Kumar"]


def test_an_unknown_phone_is_an_empty_page_not_an_error(clinic: Clinic) -> None:
    page = clinic.patients.search(phone="9811111111", name_prefix=None, limit=20, offset=0)
    assert (page.items, page.total) == ([], 0)


def test_a_malformed_search_phone_is_a_validation_error(clinic: Clinic) -> None:
    with pytest.raises(RuleViolation) as raised:
        clinic.patients.search(phone="12345", name_prefix=None, limit=20, offset=0)
    assert raised.value.code is ErrorCode.VALIDATION_ERROR


def test_names_are_matched_by_case_insensitive_prefix(clinic: Clinic) -> None:
    assert search(clinic, name_prefix="as") == ["Asha Iyer"]
    assert search(clinic, name_prefix="  RAVI ") == ["Ravi Kumar"]
    assert search(clinic, name_prefix="sha") == []  # a prefix, not a substring


def test_like_wildcards_in_a_search_are_taken_literally(clinic: Clinic) -> None:
    with clinic.factory() as session, session.begin():
        add_patient(session, 30, name="Ann_Lee")
        add_patient(session, 31, name="AnnXLee")
        add_patient(session, 32, name="100% Sure")
    assert search(clinic, name_prefix="Ann_") == ["Ann_Lee"]
    assert search(clinic, name_prefix="100%") == ["100% Sure"]
    assert search(clinic, name_prefix="%") == []  # a bare % must not match everyone
    assert search(clinic, name_prefix="_") == []
    assert search(clinic, name_prefix=chr(92)) == []


def test_search_is_paginated_with_a_total(clinic: Clinic) -> None:
    first = clinic.patients.search(phone=None, name_prefix=None, limit=2, offset=0)
    second = clinic.patients.search(phone=None, name_prefix=None, limit=2, offset=2)
    assert [p.name for p in first.items] == ["Asha Iyer", "Meena Das"]
    assert [p.name for p in second.items] == ["Ravi Kumar"]
    assert (first.total, second.total, first.limit, second.offset) == (3, 3, 2, 2)


def test_phone_and_name_filters_combine(clinic: Clinic) -> None:
    assert search(clinic, phone="9000000001", name_prefix="as") == ["Asha Iyer"]
    assert search(clinic, phone="9000000001", name_prefix="ravi") == []


def test_the_create_staff_script_makes_an_account_that_can_sign_in(
    clinic: Clinic, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.domain.model import Role
    from app.services.staff_service import StaffService
    from scripts.create_staff import main

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STAFF_NEW_PASSWORD", "script-made-pass")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert main(["--username", "scripted", "--name", "Scripted Admin", "--role", "ADMIN"]) == 0
    account = StaffService(clinic.factory).authenticate("scripted", "script-made-pass")
    assert account is not None
    assert account.role is Role.ADMIN


def test_a_staff_password_must_be_long_enough_when_created_or_reset(clinic: Clinic) -> None:
    from app.domain.model import Role
    from app.services.staff_service import StaffService

    staff = StaffService(clinic.factory)
    with pytest.raises(RuleViolation):
        staff.create("shorty", "Shorty", "short", Role.RECEPTIONIST)
    made = staff.create("longer", "Longer", "long-enough-pass", Role.RECEPTIONIST)
    with pytest.raises(RuleViolation):
        staff.update(made.id, password="short")
    renamed = staff.update(made.id, display_name="Longer Name")
    assert renamed.display_name == "Longer Name"
