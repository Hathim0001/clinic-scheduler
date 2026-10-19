"""The demo logins: one receptionist and one login per demo doctor, made only on request and
never twice."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.domain.model import Role
from app.persistence.models import StaffAccount
from app.services.staff_service import StaffService
from scripts.migrate_and_seed import seed_demo_accounts
from tests.factories import add_doctor
from tests.integration.conftest import Clinic

pytestmark = pytest.mark.integration


def accounts(clinic: Clinic) -> dict[str, StaffAccount]:
    with clinic.factory() as session:
        return {a.username: a for a in session.scalars(select(StaffAccount))}


def make_demo_doctors(clinic: Clinic) -> tuple[int, int]:
    with clinic.factory() as session, session.begin():
        rao = add_doctor(session, name="Dr. Ananya Rao", slot=15, cap=20)
        menon = add_doctor(session, name="Dr. Vikram Menon", slot=30, cap=6)
        return rao.id, menon.id


def test_each_role_gets_a_login_and_a_doctor_login_names_its_doctor(clinic: Clinic) -> None:
    rao, menon = make_demo_doctors(clinic)
    made = seed_demo_accounts(clinic.factory, "demo-password-1")
    assert made == ["reception", "dr.rao", "dr.menon"]
    found = accounts(clinic)
    assert (found["reception"].role, found["reception"].doctor_id) == ("RECEPTIONIST", None)
    assert (found["dr.rao"].role, found["dr.rao"].doctor_id) == ("DOCTOR", rao)
    assert (found["dr.menon"].role, found["dr.menon"].doctor_id) == ("DOCTOR", menon)
    signed = StaffService(clinic.factory).authenticate("dr.rao", "demo-password-1")
    assert signed is not None
    assert signed.role is Role.DOCTOR


def test_running_it_again_changes_nothing(clinic: Clinic) -> None:
    make_demo_doctors(clinic)
    seed_demo_accounts(clinic.factory, "demo-password-1")
    assert seed_demo_accounts(clinic.factory, "another-password-2") == []
    # the first password still works: an existing account is never overwritten
    assert StaffService(clinic.factory).authenticate("reception", "demo-password-1") is not None


def test_a_doctor_login_is_skipped_when_that_doctor_does_not_exist(clinic: Clinic) -> None:
    made = seed_demo_accounts(clinic.factory, "demo-password-1")  # the fixture's doctors differ
    assert made == ["reception"]
