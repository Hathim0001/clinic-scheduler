"""Individual staff accounts with roles: who may sign in, what each role may do, and what happens
the moment an account is demoted or switched off."""

from __future__ import annotations

from collections.abc import Iterator
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


@pytest.fixture
def accounts(clinic: Clinic, database_url: str) -> Iterator[Api]:
    settings = make_settings(database_url, auth_secret=SECRET, staff_password=SHARED)
    with TestClient(create_app(settings), raise_server_exceptions=False) as http:
        yield Api(http, clinic)


def login(api: Api, name: str, password: str) -> Any:
    return api.http.post(f"{BASE}/auth/login", json={"name": name, "password": password})


def headers_for(api: Api, name: str, password: str) -> dict[str, str]:
    token = login(api, name, password).json()["token"]
    return {"Authorization": f"Bearer {token}", **clock(NOW)}


def create(api: Api, admin: dict[str, str], username: str, role: str, **extra: Any) -> Any:
    body = {
        "username": username,
        "display_name": username.title(),
        "password": GOOD,
        "role": role,
    } | extra
    return api.http.post(f"{BASE}/staff", json=body, headers=admin)


@pytest.fixture
def admin(accounts: Api) -> dict[str, str]:
    """The shared bootstrap password signs in as an administrator, who creates the first account."""
    return headers_for(accounts, "Bootstrap", SHARED)


def test_the_status_says_individual_accounts_are_on(accounts: Api) -> None:
    status = accounts.http.get(f"{BASE}/auth/status").json()
    assert status == {
        "required": True,
        "accounts": True,
        "setup_needed": False,
        "open_access": False,
    }


def test_the_shared_password_signs_in_as_an_administrator(accounts: Api) -> None:
    body = login(accounts, "Bootstrap", SHARED).json()
    assert (body["name"], body["role"]) == ("Bootstrap", "ADMIN")


def test_an_admin_creates_accounts_and_each_signs_in_with_their_own_password(
    accounts: Api, admin: dict[str, str]
) -> None:
    made = create(accounts, admin, "meera", "RECEPTIONIST")
    assert made.status_code == 201
    assert "password" not in made.text
    body = login(accounts, "Meera", GOOD).json()  # the username is case-insensitive
    assert (body["name"], body["role"]) == ("Meera", "RECEPTIONIST")


def test_wrong_passwords_and_unknown_users_get_the_same_answer(
    accounts: Api, admin: dict[str, str]
) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    wrong = login(accounts, "meera", "not-the-password")
    unknown = login(accounts, "nobody", "not-the-password")
    assert_error(wrong, 401, "UNAUTHENTICATED")
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_a_receptionist_does_the_daily_work(accounts: Api, admin: dict[str, str]) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    reception = headers_for(accounts, "meera", GOOD)
    http = accounts.http
    booked = http.post(f"{BASE}/appointments", json=book_body(accounts), headers=reception)
    assert booked.status_code == 201
    assert http.get(f"{BASE}/queue?date=2026-11-02", headers=reception).status_code == 200
    report = f"{BASE}/reports/summary?from=2026-11-01&to=2026-11-02"
    assert http.get(report, headers=reception).status_code == 200


def test_a_receptionist_cannot_do_the_set_up_work(accounts: Api, admin: dict[str, str]) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    reception = headers_for(accounts, "meera", GOOD)
    http, c = accounts.http, accounts.clinic
    new_doctor = {"name": "Dr. X", "speciality": "G", "slot_length_min": 30, "daily_cap": 5}
    leave = {"windows": [], "acknowledge_conflicts": False}
    forbidden = [
        http.post(f"{BASE}/doctors", json=new_doctor, headers=reception),
        http.delete(f"{BASE}/doctors/{c.rao}", headers=reception),
        http.patch(f"{BASE}/doctors/{c.rao}", json={"daily_cap": 3}, headers=reception),
        http.put(f"{BASE}/doctors/{c.rao}/overrides/2026-11-09", json=leave, headers=reception),
        http.get(f"{BASE}/patients/{c.asha}/export", headers=reception),
        http.post(f"{BASE}/patients/{c.asha}/erase", json={}, headers=reception),
        http.post(f"{BASE}/diagnostics/proof", headers=reception),
        http.get(f"{BASE}/staff", headers=reception),
    ]
    for response in forbidden:
        assert_error(response, 403, "FORBIDDEN")


def test_an_admin_can_do_the_set_up_work(accounts: Api, admin: dict[str, str]) -> None:
    c = accounts.clinic
    assert accounts.http.get(f"{BASE}/patients/{c.asha}/export", headers=admin).status_code == 200
    changed = accounts.http.patch(f"{BASE}/doctors/{c.rao}", json={"daily_cap": 5}, headers=admin)
    assert changed.status_code == 200


def test_the_audit_trail_names_the_person_not_the_shared_password(
    accounts: Api, admin: dict[str, str]
) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    reception = headers_for(accounts, "meera", GOOD)
    booked = accounts.http.post(f"{BASE}/appointments", json=book_body(accounts), headers=reception)
    history = accounts.http.get(f"{BASE}/appointments/{booked.json()['id']}/history", headers=admin)
    assert {event["actor"] for event in history.json()} == {"Meera"}


def test_deactivating_an_account_cuts_off_its_token_at_once(
    accounts: Api, admin: dict[str, str]
) -> None:
    made = create(accounts, admin, "meera", "RECEPTIONIST").json()
    reception = headers_for(accounts, "meera", GOOD)
    assert accounts.http.get(f"{BASE}/doctors", headers=reception).status_code == 200
    accounts.http.patch(f"{BASE}/staff/{made['id']}", json={"active": False}, headers=admin)
    assert_error(accounts.http.get(f"{BASE}/doctors", headers=reception), 401, "UNAUTHENTICATED")
    assert_error(login(accounts, "meera", GOOD), 401, "UNAUTHENTICATED")


def test_a_demotion_applies_to_the_token_already_issued(
    accounts: Api, admin: dict[str, str]
) -> None:
    create(accounts, admin, "chief", "ADMIN")  # someone else stays administrator
    made = create(accounts, admin, "dev", "ADMIN").json()
    other = headers_for(accounts, "dev", GOOD)
    assert accounts.http.get(f"{BASE}/staff", headers=other).status_code == 200
    accounts.http.patch(f"{BASE}/staff/{made['id']}", json={"role": "RECEPTIONIST"}, headers=admin)
    assert_error(accounts.http.get(f"{BASE}/staff", headers=other), 403, "FORBIDDEN")


def test_the_last_active_administrator_cannot_be_removed(
    accounts: Api, admin: dict[str, str]
) -> None:
    only = create(accounts, admin, "boss", "ADMIN").json()
    for change in ({"active": False}, {"role": "RECEPTIONIST"}):
        refused = accounts.http.patch(f"{BASE}/staff/{only['id']}", json=change, headers=admin)
        assert_error(refused, 409, "LAST_ADMIN")
    second = create(accounts, admin, "boss2", "ADMIN").json()
    ok = accounts.http.patch(f"{BASE}/staff/{second['id']}", json={"active": False}, headers=admin)
    assert ok.status_code == 200


def test_usernames_are_unique_and_passwords_have_a_minimum(
    accounts: Api, admin: dict[str, str]
) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    assert_error(create(accounts, admin, "meera", "RECEPTIONIST"), 409, "STAFF_USERNAME_TAKEN")
    short = create(accounts, admin, "other", "RECEPTIONIST", password="short")
    assert_error(short, 422, "VALIDATION_ERROR")
    assert_error(create(accounts, admin, "Bad Name!", "RECEPTIONIST"), 422, "VALIDATION_ERROR")
    missing = accounts.http.patch(f"{BASE}/staff/9999", json={"active": True}, headers=admin)
    assert_error(missing, 404, "STAFF_NOT_FOUND")


def test_a_reset_password_replaces_the_old_one(accounts: Api, admin: dict[str, str]) -> None:
    made = create(accounts, admin, "meera", "RECEPTIONIST").json()
    accounts.http.patch(
        f"{BASE}/staff/{made['id']}", json={"password": "brand-new-pass"}, headers=admin
    )
    assert_error(login(accounts, "meera", GOOD), 401, "UNAUTHENTICATED")
    assert login(accounts, "meera", "brand-new-pass").status_code == 200


def test_password_hashes_never_leave_the_server(accounts: Api, admin: dict[str, str]) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    listing = accounts.http.get(f"{BASE}/staff", headers=admin).text
    assert "scrypt" not in listing
    assert "password" not in listing


def test_staff_routes_need_a_token_at_all(accounts: Api) -> None:
    assert_error(accounts.http.get(f"{BASE}/staff"), 401, "UNAUTHENTICATED")


def test_without_any_sign_in_everything_stays_open_as_before(api: Api) -> None:
    assert api.get("/staff").status_code == 200
    assert api.post("/diagnostics/proof").status_code == 200


@pytest.mark.parametrize(
    "body",
    [{}, {"role": None}, {"active": None}, {"password": None}, {"display_name": None}],
)
def test_a_staff_patch_with_nothing_or_a_null_is_refused_not_a_500(
    accounts: Api, admin: dict[str, str], body: dict[str, Any]
) -> None:
    made = create(accounts, admin, "meera", "RECEPTIONIST").json()
    response = accounts.http.patch(f"{BASE}/staff/{made['id']}", json=body, headers=admin)
    assert_error(response, 422, "VALIDATION_ERROR")


def test_five_wrong_passwords_lock_one_account_but_not_the_others(
    accounts: Api, admin: dict[str, str]
) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    create(accounts, admin, "ravi", "RECEPTIONIST")
    for _ in range(5):
        assert_error(login(accounts, "meera", "wrong-wrong"), 401, "UNAUTHENTICATED")
    locked = login(accounts, "meera", GOOD)  # even the right password is refused for a while
    assert_error(locked, 429, "RATE_LIMITED")
    assert int(locked.headers["retry-after"]) >= 1
    assert login(accounts, "ravi", GOOD).status_code == 200


def test_a_successful_sign_in_clears_the_count_of_wrong_passwords(
    accounts: Api, admin: dict[str, str]
) -> None:
    create(accounts, admin, "meera", "RECEPTIONIST")
    for _ in range(3):
        login(accounts, "meera", "wrong-wrong")
    assert login(accounts, "meera", GOOD).status_code == 200
    for _ in range(3):
        login(accounts, "meera", "wrong-wrong")
    assert login(accounts, "meera", GOOD).status_code == 200  # not locked: the count restarted


def test_an_unknown_username_is_throttled_the_same_way(accounts: Api) -> None:
    for _ in range(5):
        login(accounts, "nobody", "wrong-wrong")
    assert_error(login(accounts, "nobody", "wrong-wrong"), 429, "RATE_LIMITED")
