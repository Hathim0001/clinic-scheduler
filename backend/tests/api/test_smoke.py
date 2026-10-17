"""A first end-to-end pass through the HTTP layer."""

from __future__ import annotations

import pytest

from tests.api.conftest import Api
from tests.integration.conftest import at

pytestmark = pytest.mark.integration


def test_the_app_answers_and_books_an_appointment(api: Api) -> None:
    assert api.http.get("/healthz").json() == {"status": "ok"}
    assert api.http.get("/readyz").json() == {"status": "ready"}
    doctors = api.get("/doctors").json()
    assert [d["name"] for d in doctors] == ["Dr. Rao", "Dr. Menon"]

    body = {
        "doctor_id": api.clinic.rao,
        "patient_id": api.clinic.asha,
        "start_at": "2026-11-02T10:00:00+05:30",
        "reason": "Fever, 3 days",
    }
    created = api.post("/appointments", body)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["start_at_utc"] == "2026-11-02T04:30:00Z"
    assert data["end_at_ist"] == "2026-11-02T10:30:00+05:30"
    assert data["allowed_actions"] == ["cancel", "reschedule"]
    assert created.headers["x-effective-now"] == "2026-11-02T02:30:00Z"
    assert created.headers["x-request-id"]

    slots = api.get(f"/doctors/{api.clinic.rao}/slots", params={"date": "2026-11-02"}).json()
    assert at(10).strftime("%Y-%m-%dT%H:%M:%SZ") not in [s["start_at_utc"] for s in slots["slots"]]
