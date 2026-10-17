"""The operations endpoints over HTTP: idempotent booking, history, check-in, corrections, patient
edits, doctors not accepting, waitlist decline, reports, triage and the patient export."""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.model import Status
from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body
from tests.factories import add_appointment
from tests.helpers import ist
from tests.integration.conftest import NOW, at

pytestmark = pytest.mark.integration

KEY = {"Idempotency-Key": "retry-me-1"}


# ----------------------------------------------------------------------------- idempotency


def test_a_retried_booking_returns_the_original_with_200_and_a_replay_header(api: Api) -> None:
    first = api.post("/appointments", book_body(api), headers=KEY)
    assert first.status_code == 201
    assert "idempotent-replay" not in first.headers

    retry = api.post("/appointments", book_body(api), headers=KEY)

    assert retry.status_code == 200
    assert retry.headers["idempotent-replay"] == "true"
    assert retry.json() == first.json()
    assert api.get("/appointments").json()["total"] == 1


def test_the_same_key_with_another_body_is_a_409(api: Api) -> None:
    api.post("/appointments", book_body(api), headers=KEY)
    other = api.post(
        "/appointments", book_body(api, start_at="2026-11-02T11:00:00+05:30"), headers=KEY
    )
    assert_error(other, 409, "IDEMPOTENCY_KEY_REUSED")


def test_without_a_key_a_second_identical_booking_is_a_slot_conflict(api: Api) -> None:
    api.post("/appointments", book_body(api))
    again = api.post("/appointments", book_body(api))
    assert assert_error(again, 409, "SLOT_TAKEN")["details"]["same_patient"] is True


@pytest.mark.parametrize("key", ["", "x" * 101])
def test_a_bad_key_is_a_validation_error(api: Api, key: str) -> None:
    assert_error(
        api.post("/appointments", book_body(api), headers={"Idempotency-Key": key}),
        422,
        "VALIDATION_ERROR",
    )


# ----------------------------------------------------------------------------- history, check-in


def test_check_in_and_history_over_http(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    assert "check-in" in booked["allowed_actions"]
    assert booked["checked_in_at_utc"] is None

    arrived = api.post(f"/appointments/{booked['id']}/check-in", now=at(9, 45))
    assert arrived.status_code == 200
    assert arrived.json()["checked_in_at_ist"].startswith("2026-11-02T09:45")
    assert "check-in" not in arrived.json()["allowed_actions"]
    assert api.post(f"/appointments/{booked['id']}/check-in", now=at(9, 50)).status_code == 200

    history = api.get(f"/appointments/{booked['id']}/history").json()
    assert [e["kind"] for e in history] == ["BOOKED", "CHECKED_IN"]
    assert history[1]["at_ist"].startswith("2026-11-02T09:45")


def test_a_checked_in_patient_cannot_cancel_but_the_clinic_can(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    api.post(f"/appointments/{booked['id']}/check-in", now=at(9, 45))
    refused = api.post(
        f"/appointments/{booked['id']}/cancel", {"cancelled_by": "PATIENT"}, now=at(9, 46)
    )
    assert_error(refused, 409, "ALREADY_CHECKED_IN")
    ok = api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "CLINIC"}, now=at(9, 46))
    assert ok.status_code == 200


def test_check_in_errors(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    assert_error(
        api.post(f"/appointments/{booked['id']}/check-in", now=at(9, day=1)),
        409,
        "TOO_EARLY_TO_MARK",
    )
    assert_error(api.post("/appointments/999/check-in"), 404, "APPOINTMENT_NOT_FOUND")
    assert_error(api.get("/appointments/999/history"), 404, "APPOINTMENT_NOT_FOUND")


# ----------------------------------------------------------------------------- corrections


def seeded(api: Api, status: Status) -> int:
    with api.clinic.factory() as session, session.begin():
        return add_appointment(
            session, api.clinic.rao, api.clinic.asha, at(9, day=1), status=status
        ).id


def test_correcting_an_outcome_over_http(api: Api) -> None:
    appointment_id = seeded(api, Status.NO_SHOW)
    fixed = api.post(
        f"/appointments/{appointment_id}/correct",
        {"status": "COMPLETED", "note": "Seen by the covering doctor"},
    )
    assert fixed.status_code == 200
    assert fixed.json()["status"] == "COMPLETED"
    assert fixed.json()["allowed_actions"] == ["correct"]
    last = api.get(f"/appointments/{appointment_id}/history").json()[-1]
    assert last["kind"] == "CORRECTED"
    assert last["detail"]["note"] == "Seen by the covering doctor"


def test_a_correction_needs_a_valid_target_and_a_note(api: Api) -> None:
    appointment_id = seeded(api, Status.NO_SHOW)
    url = f"/appointments/{appointment_id}/correct"
    assert_error(api.post(url, {"status": "COMPLETED", "note": ""}), 422, "VALIDATION_ERROR")
    assert_error(api.post(url, {"status": "COMPLETED"}), 422, "VALIDATION_ERROR")
    assert_error(api.post(url, {"status": "BOOKED", "note": "x"}), 422, "VALIDATION_ERROR")
    assert_error(api.post(url, {"status": "CANCELLED", "note": "x"}), 409, "INVALID_CORRECTION")
    assert_error(
        api.post("/appointments/999/correct", {"status": "COMPLETED", "note": "x"}),
        404,
        "APPOINTMENT_NOT_FOUND",
    )


# ----------------------------------------------------------------------------- patients


def test_changing_a_phone_number(api: Api) -> None:
    changed = api.patch(f"/patients/{api.clinic.asha}", {"phone": "98765 43210"})
    assert changed.status_code == 200
    assert changed.json()["phone"] == "+919876543210"
    assert api.get("/patients", params={"phone": "9876543210"}).json()["total"] == 1


def test_patient_edit_errors(api: Api) -> None:
    taken = api.get(f"/patients/{api.clinic.ravi}").json()["phone"]
    assert_error(api.patch(f"/patients/{api.clinic.asha}", {"phone": taken}), 409, "PHONE_TAKEN")
    assert_error(api.patch(f"/patients/{api.clinic.asha}", {}), 422, "VALIDATION_ERROR")
    assert_error(api.patch(f"/patients/{api.clinic.asha}", {"name": None}), 422, "VALIDATION_ERROR")
    assert_error(
        api.patch(f"/patients/{api.clinic.asha}", {"allow_duplicate": True}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        api.patch(f"/patients/{api.clinic.asha}", {"phone": "123"}), 422, "VALIDATION_ERROR"
    )
    assert_error(api.patch("/patients/999", {"name": "Nobody"}), 404, "PATIENT_NOT_FOUND")


def test_registering_a_likely_duplicate_needs_confirmation(api: Api) -> None:
    original = api.get(f"/patients/{api.clinic.asha}").json()
    body: dict[str, Any] = {
        "name": "ASHA IYER",
        "phone": "9123456780",
        "date_of_birth": original["date_of_birth"],
    }
    refused = api.post("/patients", body)
    error = assert_error(refused, 409, "POSSIBLE_DUPLICATE")
    assert error["details"]["candidates"][0]["patient_id"] == api.clinic.asha
    assert api.post("/patients", body | {"allow_duplicate": True}).status_code == 201


def test_a_patient_export_over_http(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    export = api.get(f"/patients/{api.clinic.asha}/export")
    assert export.status_code == 200
    body = export.json()
    assert body["patient"]["id"] == api.clinic.asha
    assert [a["id"] for a in body["appointments"]] == [booked["id"]]
    assert [e["kind"] for e in body["events"]] == ["BOOKED"]
    assert_error(api.get("/patients/999/export"), 404, "PATIENT_NOT_FOUND")


# ----------------------------------------------------------------------------- doctors


def test_a_doctor_who_is_not_accepting_over_http(api: Api) -> None:
    kept = api.post("/appointments", book_body(api)).json()
    changed = api.patch(f"/doctors/{api.clinic.rao}", {"accepting_bookings": False})
    assert changed.json()["accepting_bookings"] is False

    refused = api.post("/appointments", book_body(api, patient_id=api.clinic.meena))
    assert_error(refused, 409, "DOCTOR_NOT_ACCEPTING")
    slots = api.get(f"/doctors/{api.clinic.rao}/slots", params={"date": "2026-11-03"}).json()
    assert (slots["slots"], slots["unavailable_reason"]) == ([], "NOT_ACCEPTING")
    schedule = api.get(f"/doctors/{api.clinic.rao}/schedule", params={"date": "2026-11-03"}).json()
    assert {s["state"] for s in schedule["slots"]} == {"CLOSED"}

    assert api.get(f"/appointments/{kept['id']}").json()["status"] == "BOOKED"
    assert_error(
        api.patch(f"/doctors/{api.clinic.rao}", {"accepting_bookings": None}),
        422,
        "VALIDATION_ERROR",
    )
    api.patch(f"/doctors/{api.clinic.rao}", {"accepting_bookings": True})
    assert (
        api.post(
            "/appointments",
            book_body(api, patient_id=api.clinic.meena, start_at="2026-11-02T11:00:00+05:30"),
        ).status_code
        == 201
    )


# ----------------------------------------------------------------------------- waitlist


def test_declining_an_offer_over_http(api: Api) -> None:
    booked = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi)).json()
    first = api.post(
        f"/doctors/{api.clinic.rao}/waitlist", {"patient_id": api.clinic.asha, "date": "2026-11-02"}
    ).json()
    api.post(
        f"/doctors/{api.clinic.rao}/waitlist",
        {"patient_id": api.clinic.meena, "date": "2026-11-02"},
    )
    api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "CLINIC"})

    declined = api.post(f"/waitlist/{first['id']}/decline")
    assert declined.status_code == 200
    assert declined.json()["status"] == "WAITING"
    meena = api.get(f"/patients/{api.clinic.meena}/waitlist").json()
    assert [e["status"] for e in meena] == ["OFFERED"]

    assert_error(api.post(f"/waitlist/{first['id']}/decline"), 409, "INVALID_TRANSITION")
    assert_error(api.post("/waitlist/999/decline"), 404, "WAITLIST_ENTRY_NOT_FOUND")


# ----------------------------------------------------------------------------- reports, triage


def test_the_summary_report_over_http(api: Api) -> None:
    api.post("/appointments", book_body(api))
    report = api.get("/reports/summary", params={"from": "2026-11-02", "to": "2026-11-02"})
    assert report.status_code == 200
    body = report.json()
    rao = next(d for d in body["doctors"] if d["doctor_id"] == api.clinic.rao)
    assert (rao["booked"], rao["appointments"], rao["capacity_slots"]) == (1, 1, 8)
    assert rao["utilisation"] == 0.125
    assert body["total"]["appointments"] == 1


def test_report_input_errors(api: Api) -> None:
    assert_error(
        api.get("/reports/summary", params={"from": "2026-11-05", "to": "2026-11-02"}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        api.get("/reports/summary", params={"from": "2026-01-01", "to": "2026-11-02"}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        api.get("/reports/summary", params={"from": "2026-11-02"}), 422, "VALIDATION_ERROR"
    )


def test_the_triage_check_warns_without_blocking(api: Api) -> None:
    urgent = api.post("/triage", {"text": "Severe chest pain and shortness of breath"}).json()
    assert urgent["urgent"] is True
    assert "112" in urgent["message"]
    calm = api.post("/triage", {"text": "Routine check-up"}).json()
    assert calm == {"urgent": False, "message": None}
    assert_error(api.post("/triage", {"text": "x" * 1001}), 422, "VALIDATION_ERROR")
    assert_error(api.post("/triage", {}), 422, "VALIDATION_ERROR")


def test_a_booking_for_urgent_symptoms_goes_through_but_is_marked(api: Api) -> None:
    booked = api.post("/appointments", book_body(api, reason="Chest pain since last night"))
    assert booked.status_code == 201
    assert booked.json()["urgent_symptoms"] is True
    ordinary = api.post(
        "/appointments",
        book_body(api, patient_id=api.clinic.ravi, start_at="2026-11-02T11:00:00+05:30"),
    )
    assert ordinary.json()["urgent_symptoms"] is False


def test_the_clock_header_drives_check_in_day(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    # the evening before is too early; the morning of the visit is fine
    eve = ist(2026, 11, 1, 20, 0)
    assert_error(
        api.post(f"/appointments/{booked['id']}/check-in", now=eve), 409, "TOO_EARLY_TO_MARK"
    )
    assert api.post(f"/appointments/{booked['id']}/check-in", now=NOW).status_code == 200
