"""The delivery summary and the run-reminders endpoint, with and without staff sign-in."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.views import BookCommand
from tests.api.conftest import BASE, Api, clock, make_settings
from tests.api.test_hostile_input import assert_error
from tests.integration.conftest import NOW, Clinic, at

pytestmark = pytest.mark.integration

SID = "AC0123456789abcdef"
TOKEN = "secret-auth-token"
SECRET = "a-long-random-signing-secret"
SHARED = "bootstrap-password"


def test_the_delivery_summary_says_no_gateway_and_the_reminder_hours(api: Api) -> None:
    body = api.get("/notifications/delivery").json()
    assert body["gateway"] is None
    assert body["channel"] is None
    assert (body["reminder_first_hours"], body["reminder_second_hours"]) == (24, 2)
    assert body["counts"]["PENDING"] == 0


def test_the_delivery_summary_names_a_twilio_whatsapp_gateway(
    clinic: Clinic, database_url: str
) -> None:
    configured = make_settings(
        database_url,
        twilio_account_sid=SID,
        twilio_auth_token=TOKEN,
        twilio_from="+14155238886",
        notify_channel="whatsapp",
    )
    with TestClient(create_app(configured), raise_server_exceptions=False) as http:
        body = http.get(f"{BASE}/notifications/delivery", headers=clock(NOW)).json()
    assert (body["gateway"], body["channel"]) == ("twilio", "whatsapp")


def test_an_admin_can_queue_due_reminders_on_demand_under_the_test_clock(api: Api) -> None:
    api.clinic.patients.record_consent(api.clinic.asha, NOW)
    api.clinic.booking.book(BookCommand(api.clinic.rao, api.clinic.asha, at(10, day=4), "x"), NOW)
    assert api.post("/notifications/reminders/run", now=at(9, day=3)).json() == {"queued": 0}
    assert api.post("/notifications/reminders/run", now=at(10, 30, day=3)).json() == {"queued": 1}
    assert api.post("/notifications/reminders/run", now=at(10, 45, day=3)).json() == {"queued": 0}
    kinds = [m["kind"] for m in api.get("/notifications").json()["items"]]
    assert "REMINDER_FIRST" in kinds


def test_only_an_administrator_can_run_reminders(clinic: Clinic, database_url: str) -> None:
    configured = make_settings(database_url, auth_secret=SECRET, staff_password=SHARED)
    with TestClient(create_app(configured), raise_server_exceptions=False) as http:

        def headers(name: str, password: str) -> dict[str, str]:
            token = http.post(
                f"{BASE}/auth/login", json={"name": name, "password": password}
            ).json()["token"]
            return {"Authorization": f"Bearer {token}", **clock(NOW)}

        admin = headers("Boss", SHARED)
        http.post(
            f"{BASE}/staff",
            json={
                "username": "meera",
                "display_name": "Meera",
                "password": "a-good-password",
                "role": "RECEPTIONIST",
            },
            headers=admin,
        )
        desk = headers("meera", "a-good-password")
        refused = http.post(f"{BASE}/notifications/reminders/run", headers=desk)
        assert_error(refused, 403, "FORBIDDEN")
        assert http.post(f"{BASE}/notifications/reminders/run", headers=admin).status_code == 200
