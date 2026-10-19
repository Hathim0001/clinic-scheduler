"""Sign-in is required unless open access is chosen on purpose, and a clinic with no accounts yet
gets its first administrator from the environment."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from tests.api.conftest import BASE, Api, clock, make_settings
from tests.api.test_hostile_input import assert_error
from tests.integration.conftest import NOW, Clinic

pytestmark = pytest.mark.integration

SECRET = "a-long-random-signing-secret"


def serve(clinic: Clinic, database_url: str, **values: Any) -> Generator[Api, None, None]:
    with TestClient(
        create_app(make_settings(database_url, **values)), raise_server_exceptions=False
    ) as http:
        yield Api(http, clinic)


@pytest.fixture
def unconfigured(clinic: Clinic, database_url: str) -> Iterator[Api]:
    """What a fresh deployment is: no secret, and open access not chosen."""
    yield from serve(clinic, database_url, allow_open_access=False)


@pytest.fixture
def chosen_open(clinic: Clinic, database_url: str) -> Iterator[Api]:
    yield from serve(clinic, database_url, allow_open_access=True)


def test_a_server_with_nothing_set_up_says_so_instead_of_serving_patient_data(
    unconfigured: Api,
) -> None:
    status = unconfigured.http.get(f"{BASE}/auth/status").json()
    assert status["required"] is True
    assert status["setup_needed"] is True
    assert status["open_access"] is False
    assert status["accounts"] is False

    refused = unconfigured.http.get(f"{BASE}/patients", headers=clock(NOW))
    error = assert_error(refused, 401, "UNAUTHENTICATED")
    assert error["details"] == {"setup_needed": True}
    assert "AUTH_SECRET" in error["message"]


@pytest.mark.parametrize("path", ["/doctors", "/queue", "/appointments", "/policy", "/staff"])
def test_nothing_clinical_is_readable_when_sign_in_is_not_set_up(
    unconfigured: Api, path: str
) -> None:
    assert unconfigured.http.get(f"{BASE}{path}", headers=clock(NOW)).status_code == 401


def test_the_health_checks_and_the_clock_stay_open(unconfigured: Api) -> None:
    assert unconfigured.http.get("/healthz").status_code == 200
    assert unconfigured.http.get("/readyz").status_code == 200
    assert unconfigured.http.get(f"{BASE}/clock", headers=clock(NOW)).status_code == 200


def test_signing_in_is_refused_with_a_clear_message_when_it_is_not_set_up(
    unconfigured: Api,
) -> None:
    refused = unconfigured.http.post(
        f"{BASE}/auth/login", json={"name": "admin", "password": "whatever-it-is"}
    )
    assert refused.status_code == 422
    assert "not switched on" in refused.json()["error"]["message"]


def test_open_access_can_be_chosen_on_purpose_and_says_so(chosen_open: Api) -> None:
    status = chosen_open.http.get(f"{BASE}/auth/status").json()
    assert (status["required"], status["open_access"], status["setup_needed"]) == (
        False,
        True,
        False,
    )
    assert chosen_open.http.get(f"{BASE}/doctors", headers=clock(NOW)).status_code == 200


def test_a_secret_requires_sign_in_even_when_open_access_is_also_set(
    clinic: Clinic, database_url: str
) -> None:
    gen = serve(clinic, database_url, allow_open_access=True, auth_secret=SECRET)
    api = next(gen)
    assert api.http.get(f"{BASE}/auth/status").json()["required"] is True
    assert api.http.get(f"{BASE}/doctors", headers=clock(NOW)).status_code == 401
    gen.close()


def test_a_shared_password_requires_sign_in_without_any_other_setting(
    clinic: Clinic, database_url: str
) -> None:
    gen = serve(clinic, database_url, allow_open_access=False, staff_password="clinic-secret-1")
    api = next(gen)
    status = api.http.get(f"{BASE}/auth/status").json()
    assert (status["required"], status["setup_needed"]) == (True, False)
    gen.close()


# ------------------------------------------------------------------------- the first administrator


def boot(clinic: Clinic, database_url: str, **values: Any) -> Api:
    gen = serve(clinic, database_url, allow_open_access=False, auth_secret=SECRET, **values)
    return next(gen)


def sign_in(api: Api, name: str, password: str) -> Any:
    return api.http.post(f"{BASE}/auth/login", json={"name": name, "password": password})


def test_the_first_administrator_is_created_from_the_environment(
    clinic: Clinic, database_url: str
) -> None:
    api = boot(
        clinic,
        database_url,
        bootstrap_admin_username="boss",
        bootstrap_admin_password="first-admin-pass",
    )
    signed = sign_in(api, "boss", "first-admin-pass")
    assert signed.status_code == 200
    assert signed.json()["role"] == "ADMIN"
    headers = {"Authorization": f"Bearer {signed.json()['token']}", **clock(NOW)}
    assert api.http.get(f"{BASE}/staff", headers=headers).status_code == 200


def test_the_bootstrap_does_nothing_once_any_account_exists(
    clinic: Clinic, database_url: str
) -> None:
    boot(
        clinic,
        database_url,
        bootstrap_admin_username="boss",
        bootstrap_admin_password="first-admin-pass",
    )
    # a restart with a different password in the environment must not touch the existing account
    again = boot(
        clinic,
        database_url,
        bootstrap_admin_username="boss",
        bootstrap_admin_password="a-different-password",
    )
    assert sign_in(again, "boss", "first-admin-pass").status_code == 200
    assert sign_in(again, "boss", "a-different-password").status_code == 401
    token = sign_in(again, "boss", "first-admin-pass").json()["token"]
    listing = again.http.get(
        f"{BASE}/staff", headers={"Authorization": f"Bearer {token}", **clock(NOW)}
    ).json()
    assert [a["username"] for a in listing] == ["boss"]


def test_without_a_bootstrap_no_account_is_made(clinic: Clinic, database_url: str) -> None:
    api = boot(clinic, database_url)
    assert sign_in(api, "boss", "first-admin-pass").status_code == 401


def test_the_bootstrap_needs_both_a_username_and_a_password() -> None:
    with pytest.raises(ValidationError, match="must be set together"):
        make_settings("postgresql+psycopg://x:y@localhost/z", bootstrap_admin_username="boss")
    with pytest.raises(ValidationError, match="must be set together"):
        make_settings(
            "postgresql+psycopg://x:y@localhost/z", bootstrap_admin_password="long-enough-pass"
        )


def test_a_bootstrap_username_and_password_must_be_well_formed() -> None:
    url = "postgresql+psycopg://x:y@localhost/z"
    with pytest.raises(ValidationError):
        make_settings(
            url, bootstrap_admin_username="Boss!", bootstrap_admin_password="long-enough-pass"
        )
    with pytest.raises(ValidationError):
        make_settings(url, bootstrap_admin_username="boss", bootstrap_admin_password="short")


def test_blank_bootstrap_variables_mean_off() -> None:
    settings = make_settings(
        "postgresql+psycopg://x:y@localhost/z",
        bootstrap_admin_username="",
        bootstrap_admin_password="",
    )
    assert settings.bootstrap_admin_username is None
