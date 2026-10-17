"""Rate limiting, the full Allow header of a 405, and calendar export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.ics import calendar_text
from app.main import create_app
from tests.api.conftest import BASE, Api, make_settings
from tests.api.test_hostile_input import assert_error, book_body
from tests.helpers import ist
from tests.integration.conftest import NOW

pytestmark = pytest.mark.integration


def test_a_405_lists_every_method_of_the_path(api: Api) -> None:
    response = api.http.delete(f"{BASE}/appointments")
    assert_error(response, 405, "METHOD_NOT_ALLOWED")
    assert response.headers["allow"] == "GET, POST"


def test_a_client_over_the_limit_gets_429_with_retry_after(api: Api) -> None:
    url = api.http.app.state.settings.database_url  # type: ignore[attr-defined]
    with TestClient(create_app(make_settings(url, rate_limit_per_minute=3))) as limited:
        statuses = [limited.get(f"{BASE}/doctors").status_code for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]
        blocked = limited.get(f"{BASE}/doctors")
        error = assert_error(blocked, 429, "RATE_LIMITED")
        assert int(blocked.headers["retry-after"]) >= 1
        assert error["details"]["retry_after_seconds"] >= 1
        assert limited.get("/healthz").status_code == 200  # health checks are exempt


def test_the_limit_can_be_switched_off(api: Api) -> None:
    url = api.http.app.state.settings.database_url  # type: ignore[attr-defined]
    with TestClient(create_app(make_settings(url, rate_limit_per_minute=0))) as open_door:
        assert {open_door.get("/healthz").status_code for _ in range(20)} == {200}
        assert all(open_door.get(f"{BASE}/doctors").status_code == 200 for _ in range(20))


def test_an_appointment_downloads_as_a_calendar_event(api: Api) -> None:
    booked = api.post("/appointments", book_body(api, reason="Fever, 3 days; cough")).json()
    response = api.get(f"/appointments/{booked['id']}/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "attachment" in response.headers["content-disposition"]
    body = response.text
    assert "\r\n" in body
    assert "DTSTART:20261102T043000Z" in body
    assert "DTEND:20261102T050000Z" in body
    assert "SUMMARY:Appointment with Dr. Rao" in body
    assert r"DESCRIPTION:Fever\, 3 days\; cough" in body
    assert_error(api.get("/appointments/999/calendar.ics"), 404, "APPOINTMENT_NOT_FOUND")


def test_a_patient_calendar_has_only_upcoming_booked_appointments(api: Api) -> None:
    keep = api.post("/appointments", book_body(api)).json()["id"]
    drop = api.post("/appointments", book_body(api, start_at="2026-11-02T11:00:00+05:30")).json()[
        "id"
    ]
    api.post(f"/appointments/{drop}/cancel")
    body = api.get(f"/patients/{api.clinic.asha}/calendar.ics").text
    assert body.count("BEGIN:VEVENT") == 1
    assert f"UID:appointment-{keep}@clinic-scheduler" in body
    assert_error(api.get("/patients/999/calendar.ics"), 404, "PATIENT_NOT_FOUND")


def test_long_lines_are_folded_without_splitting_a_character() -> None:
    from app.domain.model import Status
    from app.services.views import AppointmentView

    start = ist(2026, 11, 2, 10)
    view = AppointmentView(
        1,
        1,
        "Dr. Rao",
        1,
        "A",
        "+919000000001",
        Status.BOOKED,
        start,
        start,
        "é" * 100,
        False,
        False,
        None,
        None,
        None,
        None,
        False,
        (),
    )
    for line in calendar_text([view], NOW).split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    unfolded = calendar_text([view], NOW).replace("\r\n ", "")
    assert "é" * 100 in unfolded
