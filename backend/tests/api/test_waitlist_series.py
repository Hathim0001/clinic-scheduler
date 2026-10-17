"""The waitlist, recurring bookings, doctor deletion and the patient's deposit_required flag."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from app.domain.model import Status
from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body
from tests.factories import add_appointment
from tests.integration.conftest import NOW, at

pytestmark = pytest.mark.integration


def join(
    api: Api, patient: int, doctor: int | None = None, day: str = "2026-11-02"
) -> dict[str, Any]:
    response = api.post(
        f"/doctors/{doctor or api.clinic.rao}/waitlist", {"patient_id": patient, "date": day}
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


# ------------------------------------------------------------------------------------ waitlist


def test_the_whole_waitlist_flow_over_http(api: Api) -> None:
    booked = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi)).json()
    entry = join(api, api.clinic.asha)
    assert (entry["status"], entry["position"], entry["date"]) == ("WAITING", 1, "2026-11-02")

    api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "PATIENT"})

    [offer] = api.get(f"/patients/{api.clinic.asha}/waitlist").json()
    assert offer["status"] == "OFFERED"
    assert offer["offered_start_at_ist"].startswith("2026-11-02T10:00")
    queue = api.get(f"/doctors/{api.clinic.rao}/waitlist", params={"date": "2026-11-02"}).json()
    assert [e["id"] for e in queue] == [entry["id"]]

    accepted = api.post(f"/waitlist/{entry['id']}/accept", {"reason": "Fever"})
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["entry"]["status"] == "BOOKED"
    assert body["appointment"]["status"] == "BOOKED"
    assert body["appointment"]["patient_id"] == api.clinic.asha
    assert api.get(f"/patients/{api.clinic.asha}/waitlist").json() == []


def test_waitlist_errors_use_the_standard_shape(api: Api) -> None:
    join(api, api.clinic.asha)
    again = api.post(
        f"/doctors/{api.clinic.rao}/waitlist",
        {"patient_id": api.clinic.asha, "date": "2026-11-02"},
    )
    assert assert_error(again, 409, "ALREADY_WAITING")["details"]["waitlist_id"]

    past = {"patient_id": api.clinic.meena, "date": "2026-11-01"}
    assert_error(api.post(f"/doctors/{api.clinic.rao}/waitlist", past), 422, "BOOKING_IN_PAST")
    far = {"patient_id": api.clinic.meena, "date": "2027-02-01"}
    assert_error(api.post(f"/doctors/{api.clinic.rao}/waitlist", far), 422, "BOOKING_TOO_FAR")
    unknown = {"patient_id": 999, "date": "2026-11-02"}
    assert_error(api.post(f"/doctors/{api.clinic.rao}/waitlist", unknown), 404, "PATIENT_NOT_FOUND")
    assert_error(api.post("/doctors/999/waitlist", unknown), 404, "DOCTOR_NOT_FOUND")
    assert_error(
        api.post(f"/doctors/{api.clinic.rao}/waitlist", {"patient_id": 1}), 422, "VALIDATION_ERROR"
    )
    assert_error(
        api.get("/doctors/999/waitlist", params={"date": "2026-11-02"}), 404, "DOCTOR_NOT_FOUND"
    )
    assert_error(api.get("/patients/999/waitlist"), 404, "PATIENT_NOT_FOUND")
    assert_error(api.delete("/waitlist/999"), 404, "WAITLIST_ENTRY_NOT_FOUND")
    assert_error(api.post("/waitlist/999/accept", {"reason": "x"}), 404, "WAITLIST_ENTRY_NOT_FOUND")
    assert_error(api.delete("/waitlist/abc"), 422, "VALIDATION_ERROR")


def test_accepting_with_no_offer_or_after_expiry_is_a_conflict(api: Api) -> None:
    waiting = join(api, api.clinic.asha)
    assert_error(
        api.post(f"/waitlist/{waiting['id']}/accept", {"reason": "Fever"}),
        409,
        "INVALID_TRANSITION",
    )
    api.delete(f"/waitlist/{waiting['id']}")

    booked = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi)).json()
    entry = join(api, api.clinic.asha)
    api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "CLINIC"})
    late = NOW + timedelta(minutes=45)
    assert_error(
        api.post(f"/waitlist/{entry['id']}/accept", {"reason": "Fever"}, now=late),
        409,
        "OFFER_EXPIRED",
    )


def test_a_taken_slot_fails_the_accept_and_the_patient_keeps_waiting(api: Api) -> None:
    booked = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi)).json()
    entry = join(api, api.clinic.asha)
    api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "CLINIC"})
    assert api.post("/appointments", book_body(api, patient_id=api.clinic.meena)).status_code == 201

    assert_error(
        api.post(f"/waitlist/{entry['id']}/accept", {"reason": "Fever"}), 409, "SLOT_TAKEN"
    )
    [still] = api.get(f"/patients/{api.clinic.asha}/waitlist").json()
    assert still["status"] == "WAITING"


def test_leaving_the_waitlist(api: Api) -> None:
    entry = join(api, api.clinic.asha)
    assert api.delete(f"/waitlist/{entry['id']}").json()["status"] == "CANCELLED"
    assert_error(api.delete(f"/waitlist/{entry['id']}"), 409, "INVALID_TRANSITION")


def test_a_flagged_patient_must_acknowledge_the_deposit_to_accept(api: Api) -> None:
    with api.clinic.factory() as session, session.begin():
        for hour in (9, 10):
            add_appointment(
                session, api.clinic.rao, api.clinic.asha, at(hour, day=1), status=Status.NO_SHOW
            )
    booked = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi)).json()
    entry = join(api, api.clinic.asha)
    api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "PATIENT"})

    refused = api.post(f"/waitlist/{entry['id']}/accept", {"reason": "Fever"})
    assert_error(refused, 422, "DEPOSIT_REQUIRED")
    ok = api.post(f"/waitlist/{entry['id']}/accept", {"reason": "Fever", "deposit_confirmed": True})
    assert ok.status_code == 200
    assert ok.json()["appointment"]["deposit_confirmed"] is True


# ---------------------------------------------------------------------------------- recurring


def recurring(api: Api, **changes: object) -> object:
    body = book_body(api) | {"every_days": 7, "count": 3} | changes
    return api.post("/appointments/recurring", body)


def test_a_weekly_series_books_every_occurrence(api: Api) -> None:
    response = recurring(api)
    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    starts = [a["start_at_ist"][:16] for a in response.json()["appointments"]]  # type: ignore[attr-defined]
    assert starts == ["2026-11-02T10:00", "2026-11-09T10:00", "2026-11-16T10:00"]
    assert len(api.get("/appointments", params={"limit": 50}).json()["items"]) == 3


def test_a_series_is_all_or_nothing(api: Api) -> None:
    api.post(
        "/appointments",
        book_body(api, start_at="2026-11-09T10:00:00+05:30", patient_id=api.clinic.ravi),
    )
    response = recurring(api)
    error = assert_error(response, 409, "SLOT_TAKEN")
    assert error["details"]["occurrence"] == 2
    assert error["message"].startswith("Occurrence 2 of 3")
    assert len(api.get("/appointments", params={"limit": 50}).json()["items"]) == 1


def test_series_bounds_are_validated(api: Api) -> None:
    for changes in ({"count": 1}, {"count": 13}, {"every_days": 0}, {"every_days": 61}):
        assert_error(recurring(api, **changes), 422, "VALIDATION_ERROR")
    far = recurring(api, every_days=30, count=4)  # the third occurrence is past the 60 day window
    assert_error(far, 422, "BOOKING_TOO_FAR")


def test_a_series_on_a_flagged_patient_needs_the_deposit_acknowledged_once(api: Api) -> None:
    with api.clinic.factory() as session, session.begin():
        for hour in (9, 10):
            add_appointment(
                session, api.clinic.rao, api.clinic.asha, at(hour, day=1), status=Status.NO_SHOW
            )
    assert_error(recurring(api), 422, "DEPOSIT_REQUIRED")
    assert recurring(api, deposit_confirmed=True).status_code == 201  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- doctors, patients


def test_deleting_a_doctor(api: Api) -> None:
    created = api.post(
        "/doctors", {"name": "Dr. New", "speciality": "ENT", "slot_length_min": 15, "daily_cap": 5}
    ).json()
    assert api.delete(f"/doctors/{created['id']}").status_code == 204
    assert_error(api.get(f"/doctors/{created['id']}"), 404, "DOCTOR_NOT_FOUND")
    assert_error(api.delete(f"/doctors/{created['id']}"), 404, "DOCTOR_NOT_FOUND")


def test_a_doctor_with_appointments_cannot_be_deleted(api: Api) -> None:
    api.post("/appointments", book_body(api))
    error = assert_error(api.delete(f"/doctors/{api.clinic.rao}"), 409, "DOCTOR_HAS_APPOINTMENTS")
    assert error["details"]["appointments"] == 1
    assert api.get(f"/doctors/{api.clinic.rao}").status_code == 200


def test_the_patient_record_carries_a_literal_deposit_flag(api: Api) -> None:
    plain = api.get(f"/patients/{api.clinic.asha}").json()
    assert plain["deposit_required"] is False
    with api.clinic.factory() as session, session.begin():
        for hour in (9, 10):
            add_appointment(
                session, api.clinic.rao, api.clinic.asha, at(hour, day=1), status=Status.NO_SHOW
            )
    flagged = api.get(f"/patients/{api.clinic.asha}").json()
    assert flagged["deposit_required"] is True
    assert flagged["deposit"]["required"] is True
    search = api.get("/patients", params={"q": "Asha"}).json()["items"][0]
    assert search["deposit_required"] is None  # search results do not compute it
