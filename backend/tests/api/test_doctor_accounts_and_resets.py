"""Doctor logins (what a doctor may and may not do), one-time reset codes, changing your own
password, and sessions ending when a password changes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.conftest import BASE, Api, clock, make_settings
from tests.api.test_hostile_input import assert_error, book_body
from tests.integration.conftest import NOW, Clinic

pytestmark = pytest.mark.integration

SECRET = "a-long-random-signing-secret"
SHARED = "bootstrap-password"
GOOD = "a-good-password"
NEW = "a-brand-new-password"
AFTER_THE_VISIT = NOW + timedelta(hours=3)  # 11:00, after a 10:00 visit began


@pytest.fixture
def accounts(clinic: Clinic, database_url: str) -> Iterator[Api]:
    settings = make_settings(database_url, auth_secret=SECRET, staff_password=SHARED)
    with TestClient(create_app(settings), raise_server_exceptions=False) as http:
        yield Api(http, clinic)


def login(api: Api, name: str, password: str) -> Any:
    return api.http.post(f"{BASE}/auth/login", json={"name": name, "password": password})


def headers_for(api: Api, name: str, password: str, now: Any = NOW) -> dict[str, str]:
    token = login(api, name, password).json()["token"]
    return {"Authorization": f"Bearer {token}", **clock(now)}


@pytest.fixture
def admin(accounts: Api) -> dict[str, str]:
    return headers_for(accounts, "Boss", SHARED)


def make(api: Api, admin: dict[str, str], username: str, role: str, **extra: Any) -> Any:
    body = {"username": username, "display_name": username.title(), "password": GOOD, "role": role}
    return api.http.post(f"{BASE}/staff", json=body | extra, headers=admin)


def appointment_for(api: Api, admin: dict[str, str], doctor: int, patient: int) -> int:
    body = book_body(api, doctor_id=doctor, patient_id=patient)
    made = api.http.post(f"{BASE}/appointments", json=body, headers=admin)
    assert made.status_code == 201, made.text
    return int(made.json()["id"])


# ------------------------------------------------------------------------------ doctor accounts


def test_a_doctor_account_must_name_a_doctor_and_others_must_not(
    accounts: Api, admin: dict[str, str]
) -> None:
    assert_error(make(accounts, admin, "dr.rao", "DOCTOR"), 422, "VALIDATION_ERROR")
    assert_error(
        make(accounts, admin, "meera", "RECEPTIONIST", doctor_id=accounts.clinic.rao),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(make(accounts, admin, "dr.rao", "DOCTOR", doctor_id=999), 404, "DOCTOR_NOT_FOUND")
    made = make(accounts, admin, "dr.rao", "DOCTOR", doctor_id=accounts.clinic.rao)
    assert made.status_code == 201
    assert (made.json()["role"], made.json()["doctor_id"]) == ("DOCTOR", accounts.clinic.rao)


def test_signing_in_as_a_doctor_says_which_doctor(accounts: Api, admin: dict[str, str]) -> None:
    make(accounts, admin, "dr.rao", "DOCTOR", doctor_id=accounts.clinic.rao)
    body = login(accounts, "dr.rao", GOOD).json()
    assert (body["role"], body["doctor_id"]) == ("DOCTOR", accounts.clinic.rao)


def test_a_doctor_reads_the_schedule_and_marks_their_own_visit(
    accounts: Api, admin: dict[str, str]
) -> None:
    make(accounts, admin, "dr.rao", "DOCTOR", doctor_id=accounts.clinic.rao)
    visit = appointment_for(accounts, admin, accounts.clinic.rao, accounts.clinic.asha)
    doctor = headers_for(accounts, "dr.rao", GOOD, AFTER_THE_VISIT)

    queue = accounts.http.get(f"{BASE}/queue", params={"date": "2026-11-02"}, headers=doctor)
    assert queue.status_code == 200
    done = accounts.http.post(f"{BASE}/appointments/{visit}/complete", headers=doctor)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"


def test_a_doctor_cannot_mark_another_doctors_visit(accounts: Api, admin: dict[str, str]) -> None:
    make(accounts, admin, "dr.rao", "DOCTOR", doctor_id=accounts.clinic.rao)
    others = appointment_for(accounts, admin, accounts.clinic.menon, accounts.clinic.asha)
    doctor = headers_for(accounts, "dr.rao", GOOD, AFTER_THE_VISIT)
    refused = accounts.http.post(f"{BASE}/appointments/{others}/no-show", headers=doctor)
    assert_error(refused, 403, "FORBIDDEN")
    after = accounts.http.get(f"{BASE}/appointments/{others}", headers=admin).json()
    assert after["status"] == "BOOKED"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/appointments", "book"),
        ("POST", "/appointments/1/cancel", {"cancelled_by": "CLINIC"}),
        ("POST", "/appointments/1/reschedule", {"start_at": "2026-11-02T11:00:00+05:30"}),
        (
            "POST",
            "/patients",
            {"name": "A B", "phone": "9000000099", "date_of_birth": "1990-01-01"},
        ),
        ("PATCH", "/doctors/1", {"daily_cap": 5}),
        ("PATCH", "/policy", {"strikes": 3}),
        ("POST", "/notifications/reminders/run", None),
        ("GET", "/staff", None),
        ("GET", "/patients/1/export", None),
    ],
)
def test_a_doctor_can_do_nothing_else(
    accounts: Api, admin: dict[str, str], method: str, path: str, body: Any
) -> None:
    make(accounts, admin, "dr.rao", "DOCTOR", doctor_id=accounts.clinic.rao)
    doctor = headers_for(accounts, "dr.rao", GOOD)
    payload = book_body(accounts) if body == "book" else body
    response = accounts.http.request(method, f"{BASE}{path}", json=payload, headers=doctor)
    assert_error(response, 403, "FORBIDDEN")


def test_deleting_a_doctor_switches_their_login_off(accounts: Api, admin: dict[str, str]) -> None:
    spare = accounts.http.post(
        f"{BASE}/doctors",
        json={"name": "Dr. Spare", "speciality": "GP", "slot_length_min": 30, "daily_cap": 5},
        headers=admin,
    ).json()["id"]
    make(accounts, admin, "dr.spare", "DOCTOR", doctor_id=spare)
    assert login(accounts, "dr.spare", GOOD).status_code == 200
    assert accounts.http.delete(f"{BASE}/doctors/{spare}", headers=admin).status_code == 204
    assert_error(login(accounts, "dr.spare", GOOD), 401, "UNAUTHENTICATED")


# --------------------------------------------------------------------------------- reset codes


def issue(api: Api, admin: dict[str, str], staff_id: int) -> dict[str, str]:
    response = api.http.post(f"{BASE}/staff/{staff_id}/reset-code", headers=admin)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def reset(api: Api, username: str, code: str, password: str = NEW, now: Any = NOW) -> Any:
    return api.http.post(
        f"{BASE}/auth/reset-password",
        json={"username": username, "code": code, "new_password": password},
        headers=clock(now),
    )


def test_a_reset_code_lets_the_person_choose_a_new_password_once(
    accounts: Api, admin: dict[str, str]
) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    issued = issue(accounts, admin, staff_id)
    assert len(issued["code"]) == 9
    assert issued["code"][4] == "-"

    assert reset(accounts, "meera", issued["code"]).status_code == 204
    assert login(accounts, "meera", GOOD).status_code == 401  # the old password is gone
    assert login(accounts, "meera", NEW).status_code == 200
    assert_error(
        reset(accounts, "meera", issued["code"], "another-new-pass"), 401, "UNAUTHENTICATED"
    )


def test_the_code_is_accepted_in_lower_case_and_without_the_dash(
    accounts: Api, admin: dict[str, str]
) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    code = issue(accounts, admin, staff_id)["code"]
    assert reset(accounts, "meera", code.replace("-", "").lower()).status_code == 204


def test_a_wrong_expired_or_unknown_code_all_get_the_same_answer(
    accounts: Api, admin: dict[str, str]
) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    code = issue(accounts, admin, staff_id)["code"]
    wrong = assert_error(reset(accounts, "meera", "AAAA-AAAA"), 401, "UNAUTHENTICATED")
    unknown = assert_error(reset(accounts, "nobody", code), 401, "UNAUTHENTICATED")
    late = assert_error(
        reset(accounts, "meera", code, now=NOW + timedelta(hours=2)), 401, "UNAUTHENTICATED"
    )
    assert wrong["message"] == unknown["message"] == late["message"]
    assert reset(accounts, "meera", code).status_code == 204  # still valid inside the hour


def test_a_new_code_replaces_the_old_one(accounts: Api, admin: dict[str, str]) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    first = issue(accounts, admin, staff_id)["code"]
    second = issue(accounts, admin, staff_id)["code"]
    assert reset(accounts, "meera", first).status_code == 401
    assert reset(accounts, "meera", second).status_code == 204


def test_five_wrong_codes_lock_resets_for_that_account(
    accounts: Api, admin: dict[str, str]
) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    code = issue(accounts, admin, staff_id)["code"]
    for _ in range(5):
        assert reset(accounts, "meera", "AAAA-AAAA").status_code == 401
    locked = reset(accounts, "meera", code)
    assert_error(locked, 429, "RATE_LIMITED")
    assert "retry-after" in locked.headers


def test_a_short_new_password_is_refused_and_the_code_survives(
    accounts: Api, admin: dict[str, str]
) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    code = issue(accounts, admin, staff_id)["code"]
    assert_error(reset(accounts, "meera", code, "short"), 422, "VALIDATION_ERROR")
    assert reset(accounts, "meera", code).status_code == 204


def test_only_an_administrator_can_issue_a_code(accounts: Api, admin: dict[str, str]) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    desk = headers_for(accounts, "meera", GOOD)
    refused = accounts.http.post(f"{BASE}/staff/{staff_id}/reset-code", headers=desk)
    assert_error(refused, 403, "FORBIDDEN")


def test_a_deactivated_account_cannot_be_reset(accounts: Api, admin: dict[str, str]) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    code = issue(accounts, admin, staff_id)["code"]
    accounts.http.patch(f"{BASE}/staff/{staff_id}", json={"active": False}, headers=admin)
    assert reset(accounts, "meera", code).status_code == 401


# --------------------------------------------------------------------- sessions and passwords


def test_a_session_ends_when_the_password_is_reset(accounts: Api, admin: dict[str, str]) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    old = headers_for(accounts, "meera", GOOD)
    assert (
        accounts.http.get(f"{BASE}/queue", params={"date": "2026-11-02"}, headers=old).status_code
        == 200
    )
    reset(accounts, "meera", issue(accounts, admin, staff_id)["code"])
    ended = accounts.http.get(f"{BASE}/queue", params={"date": "2026-11-02"}, headers=old)
    assert_error(ended, 401, "UNAUTHENTICATED")
    fresh = headers_for(accounts, "meera", NEW)
    assert (
        accounts.http.get(f"{BASE}/queue", params={"date": "2026-11-02"}, headers=fresh).status_code
        == 200
    )


def test_an_administrator_setting_a_password_ends_that_accounts_sessions(
    accounts: Api, admin: dict[str, str]
) -> None:
    staff_id = make(accounts, admin, "meera", "RECEPTIONIST").json()["id"]
    old = headers_for(accounts, "meera", GOOD)
    accounts.http.patch(f"{BASE}/staff/{staff_id}", json={"password": NEW}, headers=admin)
    ended = accounts.http.get(f"{BASE}/queue", params={"date": "2026-11-02"}, headers=old)
    assert_error(ended, 401, "UNAUTHENTICATED")


def test_changing_your_own_password_needs_the_current_one(
    accounts: Api, admin: dict[str, str]
) -> None:
    make(accounts, admin, "meera", "RECEPTIONIST")
    desk = headers_for(accounts, "meera", GOOD)
    wrong = accounts.http.post(
        f"{BASE}/auth/change-password",
        json={"current_password": "not-it-at-all", "new_password": NEW},
        headers=desk,
    )
    assert_error(wrong, 401, "UNAUTHENTICATED")
    done = accounts.http.post(
        f"{BASE}/auth/change-password",
        json={"current_password": GOOD, "new_password": NEW},
        headers=desk,
    )
    assert done.status_code == 204
    assert login(accounts, "meera", NEW).status_code == 200
    assert login(accounts, "meera", GOOD).status_code == 401
    assert_error(
        accounts.http.get(f"{BASE}/queue", params={"date": "2026-11-02"}, headers=desk),
        401,
        "UNAUTHENTICATED",
    )


def test_the_shared_password_session_cannot_change_a_password_here(
    accounts: Api, admin: dict[str, str]
) -> None:
    response = accounts.http.post(
        f"{BASE}/auth/change-password",
        json={"current_password": SHARED, "new_password": NEW},
        headers=admin,
    )
    assert_error(response, 422, "VALIDATION_ERROR")


def test_change_password_needs_a_sign_in(accounts: Api) -> None:
    response = accounts.http.post(
        f"{BASE}/auth/change-password",
        json={"current_password": GOOD, "new_password": NEW},
    )
    assert_error(response, 401, "UNAUTHENTICATED")
