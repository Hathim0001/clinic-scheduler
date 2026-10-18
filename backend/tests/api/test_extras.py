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


def test_alternatives_offer_other_days_and_doctors_when_the_doctor_is_away(api: Api) -> None:
    api.put(f"/doctors/{api.clinic.rao}/overrides/2026-11-02", {"windows": [], "note": "leave"})
    response = api.get(
        "/alternatives",
        params={"doctor_id": api.clinic.rao, "date": "2026-11-02", "patient_id": api.clinic.asha},
    )
    assert response.status_code == 200
    options = response.json()
    assert options[0]["same_doctor"] is True
    assert options[0]["start_at_ist"] == "2026-11-03T09:00:00+05:30"
    assert any(o["doctor_id"] == api.clinic.menon for o in options)
    assert set(options[0]) >= {"doctor_name", "speciality", "start_at_utc", "end_at_ist"}


@pytest.mark.parametrize(
    "params",
    [
        {"date": "2026-11-02"},
        {"doctor_id": 0, "date": "2026-11-02"},
        {"doctor_id": 1, "date": "tomorrow"},
        {"doctor_id": 1, "date": "2026-11-02", "slots": 9},
        {"doctor_id": 1, "date": "2026-11-02", "limit": 0},
    ],
)
def test_alternatives_reject_malformed_queries_with_422(
    api: Api, params: dict[str, object]
) -> None:
    assert_error(api.get("/alternatives", params=params), 422, "VALIDATION_ERROR")


def test_alternatives_for_an_unknown_doctor_is_404(api: Api) -> None:
    assert_error(
        api.get("/alternatives", params={"doctor_id": 999, "date": "2026-11-02"}),
        404,
        "DOCTOR_NOT_FOUND",
    )


def test_the_rule_proof_passes_over_http_and_leaves_the_clinic_untouched(api: Api) -> None:
    before = api.get("/patients", params={"q": "A"}).json()["total"]
    response = api.post("/diagnostics/proof")
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["rows_before"] == body["rows_after"]
    assert len(body["cases"]) >= 15
    assert all(case["passed"] for case in body["cases"])
    assert api.get("/patients", params={"q": "A"}).json()["total"] == before


def test_messages_are_queued_listed_and_marked_sent_over_http(api: Api) -> None:
    api.post(f"/patients/{api.clinic.asha}/consent", {})
    api.post("/appointments", book_body(api))
    pending = api.get("/notifications/pending").json()
    assert pending == {"count": 1}
    page = api.get("/notifications", params={"status": "PENDING"}).json()
    message = page["items"][0]
    assert (page["total"], message["kind"]) == (1, "APPOINTMENT_BOOKED")
    assert "Dr. Rao" in message["body"]

    done = api.post(f"/notifications/{message['id']}/sent", {})
    assert done.json()["status"] == "SENT"
    assert done.json()["sent_via"] == "MANUAL"
    assert api.get("/notifications/pending").json() == {"count": 0}
    assert_error(api.post(f"/notifications/{message['id']}/sent", {}), 409, "INVALID_TRANSITION")
    assert_error(api.post("/notifications/9999/sent", {}), 404, "NOTIFICATION_NOT_FOUND")


def test_the_messages_list_rejects_an_unknown_status(api: Api) -> None:
    assert_error(api.get("/notifications", params={"status": "LOST"}), 422, "VALIDATION_ERROR")


def test_the_audit_check_reports_an_intact_history_and_a_broken_one(api: Api) -> None:
    api.post("/appointments", book_body(api))
    clean = api.get("/diagnostics/audit").json()
    assert clean["intact"] is True
    assert clean["events_checked"] >= 1
    assert clean["broken_event_ids"] == []

    from sqlalchemy import text

    with api.clinic.factory() as session, session.begin():
        session.execute(
            text("ALTER TABLE appointment_events DISABLE TRIGGER appointment_events_no_change")
        )
        session.execute(text("UPDATE appointment_events SET actor = 'forged'"))
        session.execute(
            text("ALTER TABLE appointment_events ENABLE TRIGGER appointment_events_no_change")
        )
    forged = api.get("/diagnostics/audit").json()
    assert forged["intact"] is False
    assert forged["broken_event_ids"]
