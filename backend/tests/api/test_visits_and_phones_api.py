"""The three lifted limits over HTTP: visit length, shared phones, and moving an appointment inside
two hours."""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.model import Status
from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body
from tests.factories import add_appointment
from tests.integration.conftest import at

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------------------ longer visits


def test_booking_a_two_slot_visit_returns_its_length(api: Api) -> None:
    response = api.post("/appointments", book_body(api, slots=2))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["slots"], body["duration_min"]) == (2, 60)
    assert body["end_at_ist"].startswith("2026-11-02T11:00")


def test_a_booking_without_a_length_is_one_slot(api: Api) -> None:
    body = api.post("/appointments", book_body(api)).json()
    assert (body["slots"], body["duration_min"]) == (1, 30)


@pytest.mark.parametrize("slots", [0, 5, -1, "2", 1.5, None])
def test_a_bad_length_is_a_validation_error(api: Api, slots: Any) -> None:
    assert_error(api.post("/appointments", book_body(api, slots=slots)), 422, "VALIDATION_ERROR")


def test_a_visit_that_runs_past_the_hours_is_refused_with_its_length(api: Api) -> None:
    response = api.post(
        "/appointments", book_body(api, start_at="2026-11-02T12:30:00+05:30", slots=2)
    )
    error = assert_error(response, 422, "OUTSIDE_AVAILABILITY")
    assert "60-minute visit" in error["message"]


def test_the_free_times_depend_on_the_length(api: Api) -> None:
    api.post("/appointments", book_body(api, patient_id=api.clinic.ravi))  # 10:00 is taken
    one = api.get(f"/doctors/{api.clinic.rao}/slots", params={"date": "2026-11-02"}).json()
    two = api.get(
        f"/doctors/{api.clinic.rao}/slots", params={"date": "2026-11-02", "slots": 2}
    ).json()
    starts_one = {s["start_at_ist"][11:16] for s in one["slots"]}
    starts_two = {s["start_at_ist"][11:16] for s in two["slots"]}
    assert "09:30" in starts_one
    assert "09:30" not in starts_two
    assert (one["duration_min"], two["duration_min"]) == (30, 60)
    assert two["slots"][0]["end_at_ist"][11:16] == "10:00"  # 09:00 plus a 60-minute visit


@pytest.mark.parametrize("slots", ["0", "5", "x"])
def test_a_bad_length_in_the_query_is_refused(api: Api, slots: str) -> None:
    response = api.get(
        f"/doctors/{api.clinic.rao}/slots", params={"date": "2026-11-02", "slots": slots}
    )
    assert_error(response, 422, "VALIDATION_ERROR")


def test_a_series_of_long_visits(api: Api) -> None:
    response = api.post(
        "/appointments/recurring",
        book_body(api, slots=2) | {"every_days": 7, "count": 2},
    )
    assert response.status_code == 201
    assert [a["duration_min"] for a in response.json()["appointments"]] == [60, 60]


def test_the_idempotency_key_covers_the_length(api: Api) -> None:
    headers = {"Idempotency-Key": "k-len"}
    api.post("/appointments", book_body(api), headers=headers)
    assert_error(
        api.post("/appointments", book_body(api, slots=2), headers=headers),
        409,
        "IDEMPOTENCY_KEY_REUSED",
    )


# ------------------------------------------------------------------------ shared phone numbers


def patient_body(phone: str, **extra: Any) -> dict[str, Any]:
    return {"name": "Child One", "phone": phone, "date_of_birth": "2012-04-04"} | extra


def test_a_taken_number_lists_who_has_it_and_a_confirmed_share_is_created(api: Api) -> None:
    phone = api.get(f"/patients/{api.clinic.asha}").json()["phone"]
    refused = api.post("/patients", patient_body(phone))
    error = assert_error(refused, 409, "PHONE_TAKEN")
    assert error["details"]["patients"][0]["patient_id"] == api.clinic.asha
    assert error["details"]["patients"][0]["name"] == "Asha Iyer"

    created = api.post("/patients", patient_body(phone, shares_phone=True))
    assert created.status_code == 201
    found = api.get("/patients", params={"phone": phone}).json()
    assert found["total"] == 2


def test_the_confirmation_must_be_a_real_boolean(api: Api) -> None:
    phone = api.get(f"/patients/{api.clinic.asha}").json()["phone"]
    assert_error(
        api.post("/patients", patient_body(phone, shares_phone="yes")), 422, "VALIDATION_ERROR"
    )


def test_changing_a_phone_onto_a_shared_number(api: Api) -> None:
    taken = api.get(f"/patients/{api.clinic.ravi}").json()["phone"]
    url = f"/patients/{api.clinic.asha}"
    assert_error(api.patch(url, {"phone": taken}), 409, "PHONE_TAKEN")
    ok = api.patch(url, {"phone": taken, "shares_phone": True})
    assert ok.status_code == 200
    assert ok.json()["phone"] == taken


def test_a_patch_with_only_the_confirmation_is_empty(api: Api) -> None:
    assert_error(
        api.patch(f"/patients/{api.clinic.asha}", {"shares_phone": True}), 422, "VALIDATION_ERROR"
    )


# --------------------------------------------------------------- moving it inside two hours


def seed(api: Api, hour: int = 10) -> int:
    with api.clinic.factory() as session, session.begin():
        return add_appointment(session, api.clinic.rao, api.clinic.asha, at(hour)).id


def test_a_late_patient_move_asks_for_confirmation_then_goes_through(api: Api) -> None:
    old = seed(api)
    url = f"/appointments/{old}/reschedule"
    body = {"start_at": "2026-11-02T11:00:00+05:30"}
    error = assert_error(
        api.post(url, body, now=at(8, 30)), 409, "LATE_RESCHEDULE_NEEDS_CONFIRMATION"
    )
    assert error["details"]["minutes_until_start"] == 90
    assert api.get(f"/appointments/{old}").json()["status"] == "BOOKED"

    confirmed = api.post(url, body | {"acknowledge_late": True}, now=at(8, 30))
    assert confirmed.status_code == 200
    assert confirmed.json()["old"]["status"] == Status.LATE_CANCELLED.value


def test_a_clinic_move_is_never_late(api: Api) -> None:
    old = seed(api)
    response = api.post(
        f"/appointments/{old}/reschedule",
        {"start_at": "2026-11-02T11:00:00+05:30", "by": "CLINIC"},
        now=at(9, 30),
    )
    assert response.status_code == 200
    assert response.json()["old"]["status"] == Status.CANCELLED.value
    assert response.json()["old"]["cancelled_by"] == "CLINIC"


@pytest.mark.parametrize("extra", [{"by": "NOBODY"}, {"by": None}, {"acknowledge_late": "yes"}])
def test_bad_reschedule_options_are_validation_errors(api: Api, extra: dict[str, Any]) -> None:
    old = seed(api)
    body = {"start_at": "2026-11-02T11:00:00+05:30"} | extra
    assert_error(api.post(f"/appointments/{old}/reschedule", body), 422, "VALIDATION_ERROR")


def test_the_default_mover_is_the_patient(api: Api) -> None:
    old = seed(api)
    response = api.post(
        f"/appointments/{old}/reschedule", {"start_at": "2026-11-02T11:00:00+05:30"}
    )
    assert response.status_code == 200
    assert response.json()["old"]["cancelled_by"] == "PATIENT"
