"""Staff login over HTTP: what is open, what is closed, who is named in the audit trail, and how
guessing a password is slowed down."""

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

PASSWORD = "clinic-secret-1"


@pytest.fixture
def locked(clinic: Clinic, database_url: str) -> Iterator[Api]:
    app = create_app(make_settings(database_url, staff_password=PASSWORD))
    with TestClient(app, raise_server_exceptions=False) as http:
        yield Api(http, clinic)


def login(api: Api, name: str = "Meera", password: str = PASSWORD) -> Any:
    return api.http.post(f"{BASE}/auth/login", json={"name": name, "password": password})


def bearer(api: Api, name: str = "Meera") -> dict[str, str]:
    return {"Authorization": f"Bearer {login(api, name).json()['token']}"}


def test_login_is_off_by_default(api: Api) -> None:
    assert api.http.get(f"{BASE}/auth/status").json() == {"required": False, "accounts": False}
    assert api.get("/doctors").status_code == 200  # open, exactly as before
    assert_error(login(api), 422, "VALIDATION_ERROR")


def test_with_login_on_the_status_says_so_and_stays_open(locked: Api) -> None:
    assert locked.http.get(f"{BASE}/auth/status").json() == {"required": True, "accounts": False}


@pytest.mark.parametrize(
    "path",
    [
        "/doctors",
        "/patients",
        "/appointments",
        "/queue?date=2026-11-02",
        "/reports/summary?from=2026-11-01&to=2026-11-02",
    ],
)
def test_every_data_route_refuses_a_caller_without_a_token(locked: Api, path: str) -> None:
    response = locked.http.get(f"{BASE}{path}", headers=clock(NOW))
    assert_error(response, 401, "UNAUTHENTICATED")
    assert response.headers["www-authenticate"] == "Bearer"


def test_writes_are_refused_too(locked: Api) -> None:
    assert_error(locked.post("/appointments", book_body(locked)), 401, "UNAUTHENTICATED")
    assert_error(locked.delete(f"/doctors/{locked.clinic.rao}"), 401, "UNAUTHENTICATED")
    assert_error(locked.post("/triage", {"text": "x"}), 401, "UNAUTHENTICATED")


def test_the_health_checks_the_clock_and_the_login_stay_open(locked: Api) -> None:
    assert locked.http.get("/healthz").status_code == 200
    assert locked.http.get("/readyz").status_code == 200
    assert locked.http.get(f"{BASE}/clock").status_code == 200
    assert locked.http.get(f"{BASE}/auth/status").status_code == 200


def test_a_wrong_password_is_refused_and_a_right_one_returns_a_token(locked: Api) -> None:
    assert_error(login(locked, password="nope-nope-nope"), 401, "UNAUTHENTICATED")
    ok = login(locked)
    assert ok.status_code == 200
    body = ok.json()
    assert body["name"] == "Meera"
    assert body["token"].count(".") == 1
    assert body["expires_at_epoch"] > 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": "Meera"},
        {"password": PASSWORD},
        {"name": "", "password": PASSWORD},
        {"name": "M", "password": 5},
    ],
)
def test_a_malformed_login_is_a_validation_error(locked: Api, body: dict[str, Any]) -> None:
    assert_error(locked.http.post(f"{BASE}/auth/login", json=body), 422, "VALIDATION_ERROR")


def test_a_token_opens_the_routes(locked: Api) -> None:
    headers = bearer(locked)
    response = locked.http.get(f"{BASE}/doctors", headers=headers | clock(NOW))
    assert response.status_code == 200
    booked = locked.http.post(
        f"{BASE}/appointments", json=book_body(locked), headers=headers | clock(NOW)
    )
    assert booked.status_code == 201


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Bearer garbage", "Basic abc", "bearer a.b", "Token x.y"],
)
def test_a_bad_authorization_header_is_refused(locked: Api, header: str) -> None:
    response = locked.http.get(f"{BASE}/doctors", headers={"Authorization": header})
    assert_error(response, 401, "UNAUTHENTICATED")


def test_a_token_from_another_password_is_refused(
    locked: Api, clinic: Clinic, database_url: str
) -> None:
    other = create_app(make_settings(database_url, staff_password="a-different-password"))
    with TestClient(other) as http:
        token = http.post(
            f"{BASE}/auth/login", json={"name": "X", "password": "a-different-password"}
        ).json()["token"]
    response = locked.http.get(f"{BASE}/doctors", headers={"Authorization": f"Bearer {token}"})
    assert_error(response, 401, "UNAUTHENTICATED")


def test_the_audit_trail_names_the_signed_in_person(locked: Api) -> None:
    meera = bearer(locked, "Meera") | clock(NOW)
    ravi = bearer(locked, "Ravi") | clock(NOW)
    booked = locked.http.post(f"{BASE}/appointments", json=book_body(locked), headers=meera).json()
    locked.http.post(
        f"{BASE}/appointments/{booked['id']}/cancel", json={"cancelled_by": "CLINIC"}, headers=ravi
    )
    history = locked.http.get(f"{BASE}/appointments/{booked['id']}/history", headers=meera).json()
    assert [(e["kind"], e["actor"]) for e in history] == [
        ("BOOKED", "Meera"),
        ("CANCELLED", "Ravi"),
    ]


def test_without_login_the_audit_trail_says_anonymous(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    history = api.get(f"/appointments/{booked['id']}/history").json()
    assert [e["actor"] for e in history] == ["anonymous"]


def test_guessing_the_password_is_slowed_to_ten_tries_a_minute(locked: Api) -> None:
    codes = [login(locked, password="wrong-wrong-1").status_code for _ in range(12)]
    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]
    limited = login(locked)
    assert_error(limited, 429, "RATE_LIMITED")  # even the right password waits its turn
    assert int(limited.headers["retry-after"]) >= 1
    # the ordinary API is not affected by the login bucket
    assert locked.http.get(f"{BASE}/auth/status").status_code == 200


def test_a_forged_forwarded_header_does_not_reset_the_login_limit(
    clinic: Clinic, database_url: str
) -> None:
    app = create_app(make_settings(database_url, staff_password=PASSWORD, trusted_proxy_hops=1))
    with TestClient(app) as http:
        results = []
        for n in range(12):  # the attacker invents a new left-hand address every time
            response = http.post(
                f"{BASE}/auth/login",
                json={"name": "A", "password": "wrong-wrong-1"},
                headers={"X-Forwarded-For": f"10.9.9.{n}, 203.0.113.50"},
            )
            results.append(response.status_code)
    assert results[:10] == [401] * 10
    assert results[10:] == [429, 429]


def test_different_real_clients_have_separate_login_limits(
    clinic: Clinic, database_url: str
) -> None:
    app = create_app(make_settings(database_url, staff_password=PASSWORD, trusted_proxy_hops=1))
    with TestClient(app) as http:
        for _ in range(10):
            http.post(
                f"{BASE}/auth/login",
                json={"name": "A", "password": "wrong-wrong-1"},
                headers={"X-Forwarded-For": "203.0.113.1"},
            )
        blocked = http.post(
            f"{BASE}/auth/login",
            json={"name": "A", "password": "wrong-wrong-1"},
            headers={"X-Forwarded-For": "203.0.113.1"},
        )
        other = http.post(
            f"{BASE}/auth/login",
            json={"name": "A", "password": PASSWORD},
            headers={"X-Forwarded-For": "203.0.113.2"},
        )
    assert blocked.status_code == 429
    assert other.status_code == 200
