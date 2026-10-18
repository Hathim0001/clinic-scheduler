"""Headers, CORS, request ids, health, logging and the catch-all 500 (T-H01 to T-H04, T-X04)."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.conftest import BASE, ORIGIN, Api, clock, make_settings
from tests.api.test_hostile_input import ERROR_KEYS, assert_error, book_body
from tests.integration.conftest import NOW

pytestmark = pytest.mark.integration

PREFLIGHT = {
    "Origin": ORIGIN,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type,x-test-clock,x-request-id",
}


# ---------------------------------------------------------------------------------------- CORS


def test_the_preflight_allows_the_ui_origin_and_the_headers_it_sends(api: Api) -> None:
    """T-H01: without X-Test-Clock in the allowed headers the hosted UI breaks while curl works."""
    response = api.http.options(f"{BASE}/appointments", headers=PREFLIGHT)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    allowed = response.headers["access-control-allow-headers"].lower()
    assert {"content-type", "x-test-clock", "x-request-id"} <= set(
        allowed.replace(" ", "").split(",")
    )
    assert "POST" in response.headers["access-control-allow-methods"]


def test_the_preflight_allows_the_sign_in_and_retry_headers(api: Api) -> None:
    """A signed-in UI on another origin sends Authorization; without this every call is blocked."""
    wanted = "authorization,idempotency-key,content-type,x-test-clock"
    response = api.http.options(
        f"{BASE}/appointments",
        headers=PREFLIGHT | {"Access-Control-Request-Headers": wanted},
    )
    assert response.status_code == 200
    allowed = set(
        response.headers["access-control-allow-headers"].lower().replace(" ", "").split(",")
    )
    assert {"authorization", "idempotency-key"} <= allowed


def test_a_preflight_from_another_origin_or_for_another_header_is_refused(api: Api) -> None:
    stranger = api.http.options(
        f"{BASE}/appointments", headers=PREFLIGHT | {"Origin": "https://evil.example"}
    )
    assert stranger.status_code == 400
    assert "access-control-allow-origin" not in stranger.headers
    sneaky = api.http.options(
        f"{BASE}/appointments",
        headers=PREFLIGHT | {"Access-Control-Request-Headers": "x-admin-override"},
    )
    assert sneaky.status_code == 400


def test_errors_carry_the_cors_header_so_the_browser_can_read_them(api: Api) -> None:
    """T-H02: a 4xx, and a forced 500, must both be readable by the UI."""
    rejected = api.http.post(
        f"{BASE}/appointments", json={}, headers={"Origin": ORIGIN} | clock(NOW)
    )
    assert rejected.status_code == 422
    assert rejected.headers["access-control-allow-origin"] == ORIGIN
    exposed = rejected.headers["access-control-expose-headers"].lower()
    assert "x-request-id" in exposed
    assert "x-effective-now" in exposed


def test_a_forced_500_is_the_standard_body_with_the_cors_header(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode() -> list[Any]:
        raise RuntimeError("secret internal detail: db password hunter2")

    monkeypatch.setattr(api.http.app.state.services.doctors, "list", explode)  # type: ignore[attr-defined]
    response = api.http.get(f"{BASE}/doctors", headers={"Origin": ORIGIN})
    error = assert_error(response, 500, "INTERNAL_ERROR")
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    assert error["details"] == {}
    assert "request id" in error["message"]


def test_an_origin_that_is_not_allowed_gets_no_cors_header(api: Api) -> None:
    response = api.http.get(f"{BASE}/doctors", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


# ------------------------------------------------------------------------------- request ids


def test_a_sane_request_id_is_echoed_in_the_header_and_in_errors(api: Api) -> None:
    response = api.http.get(f"{BASE}/nope", headers={"X-Request-ID": "reviewer-test_1.2"})
    assert response.headers["x-request-id"] == "reviewer-test_1.2"
    assert response.json()["error"]["request_id"] == "reviewer-test_1.2"


@pytest.mark.parametrize(
    "hostile",
    ["x" * 10_000, "<script>alert(1)</script>", "a b", "a\tb", "id;drop", "", "é" * 5],
    ids=["10 KB", "script", "space", "tab", "semicolon", "empty", "non-ascii"],
)
def test_a_hostile_request_id_is_replaced_not_reflected(api: Api, hostile: str) -> None:
    """T-H03"""
    headers = {b"X-Request-ID": hostile.encode("latin-1")}  # bytes: send it exactly as written
    response = api.http.get(f"{BASE}/doctors", headers=headers)
    issued = response.headers["x-request-id"]
    assert issued != hostile
    assert 1 <= len(issued) <= 64
    assert not hostile or hostile[:20] not in response.text


def test_every_response_has_a_distinct_request_id(api: Api) -> None:
    ids = {api.http.get(f"{BASE}/doctors").headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5


# ------------------------------------------------------------------------------------ health


def test_health_checks_are_at_the_root(api: Api) -> None:
    assert api.http.get("/healthz").json() == {"status": "ok"}
    assert api.http.get("/readyz").json() == {"status": "ready"}
    assert api.http.get(f"{BASE}/healthz").status_code == 404


def test_with_the_database_down_liveness_stays_up_and_readiness_says_503() -> None:
    """T-H04: a database outage must not make the platform restart a healthy process."""
    unreachable = "postgresql+psycopg://clinic:clinic@127.0.0.1:1/clinic"
    app = create_app(make_settings(unreachable, db_connect_timeout_s=1))
    with TestClient(app, raise_server_exceptions=False) as http:
        assert http.get("/healthz").status_code == 200
        ready = http.get("/readyz")
        error = assert_error(ready, 503, "SERVICE_UNAVAILABLE")
        assert ready.headers["retry-after"] == "1"
        assert error["message"]
        data = http.get(f"{BASE}/doctors")  # a data request fails the same way, not as a 500
        assert_error(data, 503, "SERVICE_UNAVAILABLE")
        assert data.headers["retry-after"] == "1"


# ----------------------------------------------------------------------------- the clock


def test_the_clock_endpoint_reports_the_header_time_in_both_zones(api: Api) -> None:
    response = api.get("/clock")
    assert response.status_code == 200
    body = response.json()
    assert (body["now_utc"], body["now_ist"]) == (
        "2026-11-02T02:30:00Z",
        "2026-11-02T08:00:00+05:30",
    )
    assert (body["source"], body["test_clock_enabled"]) == ("HEADER", True)
    assert response.headers["x-effective-now"] == "2026-11-02T02:30:00Z"


def test_without_the_header_the_clock_is_the_real_one(api: Api) -> None:
    response = api.http.get(f"{BASE}/clock")
    body = response.json()
    assert body["source"] == "REAL"
    assert "x-effective-now" not in response.headers
    assert body["seed_anchor_date"] is None  # nothing seeded in the test database


# ----------------------------------------------------------------------------------- logging


@pytest.fixture
def logged(api: Api, caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


def events(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [r.msg for r in caplog.records if isinstance(r.msg, dict)]


def test_a_rejected_booking_is_logged_with_the_code_and_ids_but_no_personal_data(
    api: Api, logged: pytest.LogCaptureFixture
) -> None:
    """T-X04"""
    body = book_body(api, start_at="2026-11-01T10:00:00+05:30", reason="Fever, secret symptoms")
    response = api.post("/appointments", body)
    request_id = response.headers["x-request-id"]
    assert response.status_code == 422

    mine = [e for e in events(logged) if e.get("request_id") == request_id]
    rejected = next(e for e in mine if e["event"] == "request.rejected")
    assert (rejected["code"], rejected["status"], rejected["level"]) == (
        "BOOKING_IN_PAST",
        422,
        "warning",
    )
    assert (rejected["doctor_id"], rejected["patient_id"]) == (api.clinic.rao, api.clinic.asha)
    access = next(e for e in mine if e["event"] == "request")
    assert (access["method"], access["path"], access["status"]) == (
        "POST",
        f"{BASE}/appointments",
        422,
    )
    assert access["effective_now"] == "2026-11-02T02:30:00Z"
    assert isinstance(access["duration_ms"], float)

    everything = json.dumps(events(logged))
    for private in ("Asha Iyer", "+919000000001", "secret symptoms", "Fever"):
        assert private not in everything


def test_a_booking_logs_the_state_change_at_info(
    api: Api, logged: pytest.LogCaptureFixture
) -> None:
    response = api.post("/appointments", book_body(api))
    assert response.status_code == 201
    booked = next(e for e in events(logged) if e["event"] == "appointment.booked")
    assert booked["appointment_id"] == response.json()["id"]
    assert booked["level"] == "info"


def test_query_strings_and_bodies_are_never_logged(
    api: Api, logged: pytest.LogCaptureFixture
) -> None:
    api.get("/patients", params={"phone": "9000000001", "q": "Asha"})
    text = json.dumps(events(logged))
    assert "9000000001" not in text
    assert "Asha" not in text


def test_the_health_check_is_not_logged_at_info(api: Api, logged: pytest.LogCaptureFixture) -> None:
    api.http.get("/healthz")
    probes = [e for e in events(logged) if e.get("path") == "/healthz"]
    assert probes
    assert {e["level"] for e in probes} == {"debug"}


def test_a_server_error_is_logged_with_its_stack_trace_server_side_only(
    api: Api, logged: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode() -> list[Any]:
        raise RuntimeError("boom-marker")

    monkeypatch.setattr(api.http.app.state.services.doctors, "list", explode)  # type: ignore[attr-defined]
    response = api.http.get(f"{BASE}/doctors")
    assert response.status_code == 500
    failed = next(e for e in events(logged) if e["event"] == "request.failed")
    assert failed["level"] == "error"
    assert "boom-marker" in str(failed.get("exception", failed.get("exc_info", "")))
    assert "boom-marker" not in response.text


# --------------------------------------------------------------------------------- the docs


def test_the_openapi_description_lists_the_endpoints(api: Api) -> None:
    schema = api.http.get("/openapi.json").json()
    assert f"{BASE}/appointments" in schema["paths"]
    assert "/healthz" in schema["paths"]
    assert api.http.get("/docs").status_code == 200
    assert set(ERROR_KEYS) == {"code", "message", "details", "request_id"}
