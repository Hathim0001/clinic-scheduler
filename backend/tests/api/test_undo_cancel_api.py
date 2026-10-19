"""Taking back a cancellation made a few minutes ago, with every booking rule checked again."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body
from tests.api.test_waitlist_series import join
from tests.integration.conftest import NOW

pytestmark = pytest.mark.integration


def cancel(api: Api, appointment_id: int, minutes: int = 0, by: str = "PATIENT") -> dict[str, Any]:
    response = api.post(
        f"/appointments/{appointment_id}/cancel",
        {"cancelled_by": by},
        now=NOW + timedelta(minutes=minutes),
    )
    assert response.status_code == 200, response.text
    return response.json()["appointment"]  # type: ignore[no-any-return]


def test_a_fresh_cancellation_offers_undo_and_undo_restores_the_booking(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    cancelled = cancel(api, booked["id"])
    assert cancelled["status"] == "CANCELLED"
    assert "undo-cancel" in cancelled["allowed_actions"]

    undone = api.post(f"/appointments/{booked['id']}/undo-cancel", now=NOW + timedelta(minutes=3))

    assert undone.status_code == 200, undone.text
    body = undone.json()
    assert body["status"] == "BOOKED"
    assert body["cancelled_by"] is None
    assert body["cancelled_at_utc"] is None
    kinds = [e["kind"] for e in api.get(f"/appointments/{booked['id']}/history").json()]
    assert kinds[-2:] == ["CANCELLED", "CANCEL_UNDONE"]


def test_undoing_a_late_cancellation_removes_the_strike(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    # 10:00 visit cancelled at 08:30 is inside the 2 hours, so it is a late cancellation
    late = cancel(api, booked["id"], minutes=30)
    assert late["status"] == "LATE_CANCELLED"

    undone = api.post(f"/appointments/{booked['id']}/undo-cancel", now=NOW + timedelta(minutes=35))

    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "BOOKED"


def test_a_clinic_cancellation_tells_the_patient_when_it_is_undone(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    cancel(api, booked["id"], by="CLINIC")
    api.post(f"/appointments/{booked['id']}/undo-cancel", now=NOW + timedelta(minutes=1))

    messages = api.get("/notifications", params={"limit": 50}).json()["items"]
    assert "APPOINTMENT_RESTORED" in {m["kind"] for m in messages}


def test_undo_is_refused_after_the_ten_minutes(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    cancelled = cancel(api, booked["id"])
    assert "undo-cancel" in cancelled["allowed_actions"]

    late = api.post(f"/appointments/{booked['id']}/undo-cancel", now=NOW + timedelta(minutes=11))

    assert_error(late, 409, "UNDO_NOT_POSSIBLE")
    assert api.get(f"/appointments/{booked['id']}").json()["status"] == "CANCELLED"


def test_undo_is_refused_when_the_slot_was_taken_meanwhile(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    cancel(api, booked["id"])
    api.post("/appointments", book_body(api, patient_id=api.clinic.ravi))

    refused = api.post(f"/appointments/{booked['id']}/undo-cancel", now=NOW + timedelta(minutes=2))

    assert_error(refused, 409, "SLOT_TAKEN")


def test_undo_is_refused_when_the_slot_was_offered_to_the_waitlist(api: Api) -> None:
    booked = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi)).json()
    join(api, api.clinic.asha)
    cancel(api, booked["id"])

    refused = api.post(f"/appointments/{booked['id']}/undo-cancel", now=NOW + timedelta(minutes=1))

    assert_error(refused, 409, "UNDO_NOT_POSSIBLE")


def test_a_booked_appointment_has_nothing_to_undo(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    assert "undo-cancel" not in booked["allowed_actions"]
    assert_error(api.post(f"/appointments/{booked['id']}/undo-cancel"), 409, "UNDO_NOT_POSSIBLE")


def test_a_moved_appointment_cannot_be_undone(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    moved = api.post(
        f"/appointments/{booked['id']}/reschedule", {"start_at": "2026-11-02T11:00:00+05:30"}
    ).json()
    assert "undo-cancel" not in moved["old"]["allowed_actions"]
    assert_error(api.post(f"/appointments/{booked['id']}/undo-cancel"), 409, "UNDO_NOT_POSSIBLE")
