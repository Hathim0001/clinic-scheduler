"""Hostile and malformed input (T-X01 to T-X13): every case is a clean 4xx in the one error shape.

Each input here made a naive implementation return a 5xx or crash while building its own error
response (plan 14.3.4). The checks are the same for all of them: the status is the expected 4xx, the
body has exactly the four error keys, and nothing the client sent is echoed back.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.conftest import BASE, Api, clock, make_settings
from tests.integration.conftest import NOW

pytestmark = pytest.mark.integration

JSON = {"Content-Type": "application/json"}
ERROR_KEYS = {"code", "message", "details", "request_id"}


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text[:300]
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == ERROR_KEYS
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["x-request-id"]
    assert isinstance(body["error"]["details"], dict)
    return body["error"]  # type: ignore[no-any-return]


def book_body(api: Api, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "doctor_id": api.clinic.rao,
        "patient_id": api.clinic.asha,
        "start_at": "2026-11-02T10:00:00+05:30",
        "reason": "Check-up",
    }
    return body | changes


def post_raw(api: Api, path: str, content: bytes | str, **headers: str) -> Any:
    return api.http.post(f"{BASE}{path}", content=content, headers=JSON | clock(NOW) | headers)


# ---------------------------------------------------------------------------- malformed bodies


@pytest.mark.parametrize(
    "content",
    [b"{", b"", b"not json", b"[1, 2", b"\xff\xfe\x00", b"{'a': 1}", b'{"a": }', b"\x00"],
    ids=["brace", "empty", "words", "unclosed array", "bad utf-8", "single quotes", "hole", "nul"],
)
def test_a_body_that_is_not_json_is_a_400_or_422_never_a_crash(api: Api, content: bytes) -> None:
    """T-X01. An empty body is 'the fields are missing' (422); the rest are not JSON (400)."""
    response = post_raw(api, "/appointments", content)
    expected = ("VALIDATION_ERROR", 422) if content == b"" else ("MALFORMED_JSON", 400)
    assert_error(response, expected[1], expected[0])


def test_deep_nesting_under_the_size_limit_is_refused_cleanly(api: Api) -> None:
    response = post_raw(api, "/appointments", b"[" * 30_000 + b"]" * 30_000)
    assert response.status_code in (400, 422)
    assert set(response.json()["error"]) == ERROR_KEYS


@pytest.mark.parametrize(
    "content",
    [
        b'{"doctor_id": NaN}',
        b'{"doctor_id": Infinity}',
        b'{"doctor_id": -Infinity}',
        b'{"doctor_id": 1e999}',
    ],
)
def test_nan_and_infinity_literals_get_a_json_answer(api: Api, content: bytes) -> None:
    """T-X08: FastAPI once crashed while serialising its own 422 for these."""
    response = post_raw(api, "/appointments", content)
    assert response.status_code == 422
    assert set(response.json()["error"]) == ERROR_KEYS


# ----------------------------------------------------------------------------- wrong shapes


@pytest.mark.parametrize(
    "changes",
    [
        {"doctor_id": "abc"},
        {"doctor_id": "1"},
        {"doctor_id": True},
        {"doctor_id": 1.5},
        {"doctor_id": 0},
        {"doctor_id": -1},
        {"doctor_id": 2_147_483_648},
        {"doctor_id": 99_999_999_999_999_999_999},
        {"doctor_id": None},
        {"patient_id": [1]},
        {"start_at": "2026-11-02T10:00:00"},  # no offset
        {"start_at": "2026-11-02"},  # date only
        {"start_at": 1_700_000_000},  # a Unix number
        {"start_at": "0001-01-01T00:00:00+05:30"},  # year 1
        {"start_at": "9999-12-31T23:59:59+00:00"},  # year 9999
        {"start_at": "2026-11-02T10:00:00+99:00"},
        {"start_at": "tomorrow"},
        {"start_at": "2026-11-02T10:00:00+05:30" + "x" * 100},
        {"reason": ""},
        {"reason": "   "},
        {"reason": "x" * 501},
        {"reason": "bad\x00byte"},
        {"reason": "bell\x07"},
        {"reason": "lone surrogate \ud800"},
        {"reason": 5},
        {"deposit_confirmed": "yes"},
        {"deposit_confirmed": 1},
        {"deposit_confirmed": "true"},
        {"deposit_confirmed": None},
        {"end_at": "2026-11-02T10:30:00+05:30"},
        {"status": "COMPLETED"},
        {"unexpected": 1},
    ],
    ids=lambda changes: ",".join(f"{k}={str(v)[:20]!r}" for k, v in changes.items()),
)
def test_a_booking_with_a_bad_field_is_a_422(api: Api, changes: dict[str, Any]) -> None:
    """T-X02, T-X05 to T-X07, T-X11, T-X12."""
    # ensure_ascii=False would fail on a lone surrogate, so let json escape it as \ud800
    content = json.dumps(book_body(api, **changes))
    error = assert_error(post_raw(api, "/appointments", content), 422, "VALIDATION_ERROR")
    assert error["details"]["fields"]


def test_missing_fields_are_listed(api: Api) -> None:
    response = post_raw(api, "/appointments", "{}")
    error = assert_error(response, 422, "VALIDATION_ERROR")
    missing = {tuple(f["loc"]) for f in error["details"]["fields"]}
    assert {("body", "doctor_id"), ("body", "patient_id"), ("body", "start_at")} <= missing


def test_a_body_that_is_not_an_object_is_a_422(api: Api) -> None:
    for content in ("[]", "42", '"text"', "null", "true"):
        assert_error(post_raw(api, "/appointments", content), 422, "VALIDATION_ERROR")


def test_the_error_never_repeats_what_was_sent(api: Api) -> None:
    marker = "secret-marker-8c1f"
    body = book_body(api, doctor_id=marker, reason=5, start_at=marker, deposit_confirmed=marker)
    response = post_raw(api, "/appointments", json.dumps(body))
    assert response.status_code == 422
    assert marker not in response.text  # values are never echoed
    unknown = post_raw(api, "/appointments", json.dumps(book_body(api, **{marker: 1})))
    assert unknown.status_code == 422
    assert marker in unknown.text  # a key name is reported so the client can find its mistake


def test_a_huge_unknown_key_name_is_truncated_in_the_error(api: Api) -> None:
    response = post_raw(api, "/appointments", json.dumps(book_body(api, **{"k" * 50_000: 1})))
    assert response.status_code in (413, 422)
    assert len(response.text) < 5_000


# ------------------------------------------------------------------------------- body size


def test_a_five_megabyte_body_is_refused_before_it_is_read(api: Api) -> None:
    """T-X10"""
    response = post_raw(api, "/appointments", b'{"reason": "' + b"x" * 5_000_000 + b'"}')
    error = assert_error(response, 413, "PAYLOAD_TOO_LARGE")
    assert "64 KiB" in error["message"]


def padded_body(api: Api, padding_bytes: int) -> str:
    body = json.dumps(book_body(api, reason="x" * 10))
    return body[:-1] + f', "pad": "{"y" * padding_bytes}"}}'


def test_a_body_just_over_the_limit_is_refused_and_just_under_is_read(api: Api) -> None:
    over, under = padded_body(api, 65 * 1024), padded_body(api, 60 * 1024)
    assert_error(post_raw(api, "/appointments", over), 413, "PAYLOAD_TOO_LARGE")
    # 60 KiB is read in full, and then refused for the unknown key
    assert_error(post_raw(api, "/appointments", under), 422, "VALIDATION_ERROR")


def test_the_limit_also_applies_without_a_content_length(api: Api) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(100):
            yield b"x" * 1024

    response = api.http.post(f"{BASE}/appointments", content=chunks(), headers=JSON | clock(NOW))
    assert_error(response, 413, "PAYLOAD_TOO_LARGE")


# --------------------------------------------------------------------------- ids and paging


@pytest.mark.parametrize(
    "bad", ["0", "-1", "2147483648", "99999999999999999999", "abc", "1.5", " "]
)
@pytest.mark.parametrize("path", ["/doctors/{}", "/patients/{}", "/appointments/{}"])
def test_a_bad_id_in_the_path_is_a_422(api: Api, path: str, bad: str) -> None:
    response = api.get(path.format(bad))
    assert response.status_code in (404, 422)
    assert set(response.json()["error"]) == ERROR_KEYS
    if bad not in (" ",):
        assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "-1"},
        {"limit": "abc"},
        {"limit": "99999999999999999999"},
        {"offset": "-1"},
        {"offset": "100001"},
        {"offset": "x"},
        {"status": "DONE"},
        {"doctor_id": "0"},
        {"needs_attention": "yes"},
        {"date": "2026-13-45"},
        {"date": "9999-12-31"},
        {"date": "1999-12-31"},
        {"date": "20261102"},
        {"date": "2026-11-02T00:00:00"},
    ],
    ids=lambda params: ",".join(f"{k}={v}" for k, v in params.items()),
)
def test_bad_query_parameters_are_a_422(api: Api, params: dict[str, str]) -> None:
    """T-X05, T-X06"""
    assert_error(api.get("/appointments", params=params), 422, "VALIDATION_ERROR")


def test_extreme_but_legal_paging_is_fine(api: Api) -> None:
    response = api.get("/appointments", params={"limit": "100", "offset": "100000"})
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 100, "offset": 100000}


def test_dates_for_slots_and_the_queue_are_validated(api: Api) -> None:
    rao = api.clinic.rao
    for date in ("9999-12-31", "0001-01-01", "tomorrow", "2026-02-30", ""):
        assert_error(
            api.get(f"/doctors/{rao}/slots", params={"date": date}), 422, "VALIDATION_ERROR"
        )
        assert_error(api.get("/queue", params={"date": date}), 422, "VALIDATION_ERROR")
    assert_error(api.get(f"/doctors/{rao}/slots"), 422, "VALIDATION_ERROR")  # date is required


# ------------------------------------------------------------------- unknown routes, methods


def test_an_unknown_route_is_a_404_in_the_standard_shape(api: Api) -> None:
    """T-X09"""
    for path in ("/nope", "/doctors/1/nope", "/appointments/1/explode"):
        assert_error(api.get(path), 404, "NOT_FOUND")
    assert_error(api.http.get("/nowhere"), 404, "NOT_FOUND")


def test_a_wrong_method_is_a_405_with_the_allowed_methods(api: Api) -> None:
    response = api.http.delete(f"{BASE}/appointments", headers=clock(NOW))
    assert_error(response, 405, "METHOD_NOT_ALLOWED")
    assert response.headers["allow"]  # Starlette names the method(s) of the matched path
    assert_error(api.http.post(f"{BASE}/clock", headers=clock(NOW)), 405, "METHOD_NOT_ALLOWED")


# ----------------------------------------------------------------------------- test clock


@pytest.mark.parametrize(
    "value",
    [
        "tomorrow",
        "2026-11-02T08:00:00",  # naive
        "2026-11-02",
        "2026-11-02T08:00:00+99:00",
        "",
        "   ",
        "9999-01-01T00:00:00+00:00",
        "1999-12-31T23:59:59+00:00",
        "2100-01-01T00:00:00+00:00",
        "0001-01-01T00:00:00+05:30",
        "1700000000",
        "x" * 500,
    ],
    ids=lambda v: repr(v[:25]),
)
def test_a_bad_test_clock_is_a_400_and_never_silently_ignored(api: Api, value: str) -> None:
    """T-X03: a reviewer must never believe a simulated time was applied when it was not."""
    response = api.http.get(f"{BASE}/clock", headers={"X-Test-Clock": value})
    assert_error(response, 400, "INVALID_TEST_CLOCK")
    response = api.http.post(
        f"{BASE}/appointments", json=book_body(api), headers={"X-Test-Clock": value}
    )
    assert_error(response, 400, "INVALID_TEST_CLOCK")


def test_the_test_clock_is_refused_when_the_server_does_not_allow_it(api: Api) -> None:
    url = api.http.app.state.settings.database_url  # type: ignore[attr-defined]
    with TestClient(create_app(make_settings(url, test_clock_enabled=False))) as strict:
        assert_error(strict.get(f"{BASE}/clock", headers=clock(NOW)), 400, "INVALID_TEST_CLOCK")
        assert strict.get(f"{BASE}/clock").status_code == 200  # no header: the real clock


def test_a_repeated_test_clock_header_is_refused(api: Api) -> None:
    response = api.http.get(
        f"{BASE}/clock",
        headers=[
            ("X-Test-Clock", "2026-11-02T08:00:00+05:30"),
            ("X-Test-Clock", "2026-11-03T08:00:00+05:30"),
        ],
    )
    assert_error(response, 400, "INVALID_TEST_CLOCK")


# ---------------------------------------------------------------------------------- phones


@pytest.mark.parametrize(
    "phone", ["98765 43210", "+91-98765-43210", "09876543210", "919876543210", "9876543210"]
)
def test_phones_in_the_usual_forms_are_normalised(api: Api, phone: str) -> None:
    """T-X13, accepted"""
    body = {"name": "Kiran Bose", "phone": phone, "date_of_birth": "1985-04-02"}
    response = api.post("/patients", body)
    assert response.status_code == 201, response.text
    assert response.json()["phone"] == "+919876543210"


@pytest.mark.parametrize(
    "phone",
    [
        "1234567890",
        "+9198765",
        "' OR 1=1--",
        "".join(chr(0x0660 + int(d)) for d in "9876543210"),
        "9876543210; DROP TABLE patients",
        9876543210,
        None,
    ],
)
def test_bad_phones_are_a_422(api: Api, phone: Any) -> None:
    """T-X13, rejected"""
    body = {"name": "Kiran Bose", "phone": phone, "date_of_birth": "1985-04-02"}
    assert_error(api.post("/patients", body), 422, "VALIDATION_ERROR")
