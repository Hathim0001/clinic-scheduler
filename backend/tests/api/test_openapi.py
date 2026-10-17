"""The OpenAPI document at /openapi.json is what a reviewer reads first, so it must describe the
requests the API really accepts. The custom parsers take text (an instant, a date, HH:MM), and the
generated schema once called them numbers; these tests tie the documentation to the behaviour."""

from __future__ import annotations

from typing import Any

import pytest

from app.api.schemas.requests import (
    BookRequest,
    DoctorCreate,
    PatientCreate,
    WeeklyWindowIn,
    WindowIn,
)
from tests.api.conftest import Api

pytestmark = pytest.mark.integration


@pytest.fixture
def schemas(api: Api) -> dict[str, Any]:
    return api.http.get("/openapi.json").json()["components"]["schemas"]  # type: ignore[no-any-return]


def test_instants_dates_and_times_are_documented_as_text(schemas: dict[str, Any]) -> None:
    book = schemas["BookRequest"]["properties"]
    assert (book["start_at"]["type"], book["start_at"]["format"]) == ("string", "date-time")
    assert schemas["PatientCreate"]["properties"]["date_of_birth"]["format"] == "date"
    window = schemas["WindowIn"]["properties"]
    assert window["start"]["type"] == window["end"]["type"] == "string"
    assert "pattern" in window["start"]
    assert schemas["DoctorCreate"]["properties"]["slot_length_min"]["enum"] == [15, 30]


def test_the_documented_examples_are_accepted_by_the_request_models(
    schemas: dict[str, Any],
) -> None:
    start_at = schemas["BookRequest"]["properties"]["start_at"]["examples"][0]
    time_of_day = schemas["WindowIn"]["properties"]["start"]["examples"][0]
    born = schemas["PatientCreate"]["properties"]["date_of_birth"]["examples"][0]
    phone = schemas["PatientCreate"]["properties"]["phone"]["examples"][0]

    BookRequest.model_validate(
        {"doctor_id": 1, "patient_id": 1, "start_at": start_at, "reason": "Check-up"}
    )
    WindowIn.model_validate({"start": time_of_day, "end": "24:00"})
    WeeklyWindowIn.model_validate({"weekday": 0, "start": time_of_day, "end": "13:00"})
    PatientCreate.model_validate({"name": "Kiran Bose", "phone": phone, "date_of_birth": born})
    DoctorCreate.model_validate(
        {"name": "Dr. A", "speciality": "ENT", "slot_length_min": 15, "daily_cap": 10}
    )


def test_every_operation_has_a_summary_and_a_success_response(api: Api) -> None:
    document = api.http.get("/openapi.json").json()
    missing = []
    for path, methods in document["paths"].items():
        for method, operation in methods.items():
            has_success = any(code.startswith("2") for code in operation["responses"])
            if not operation.get("summary") or not has_success:
                missing.append(f"{method.upper()} {path}")
    assert missing == []


def test_the_api_is_versioned_in_its_paths(api: Api) -> None:
    paths = api.http.get("/openapi.json").json()["paths"]
    outside = [
        p for p in paths if not p.startswith("/api/v1/") and p not in ("/healthz", "/readyz")
    ]
    assert outside == []
