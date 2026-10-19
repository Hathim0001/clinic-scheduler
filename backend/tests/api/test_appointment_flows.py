"""Appointments through the HTTP API: booking and its refusals, cancelling, rescheduling, marking,
listing and the day queue. The rules themselves are tested in the domain and service layers; here
the point is the status code, the error code, the payload shape and the headers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from app.domain.model import Status
from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body
from tests.factories import add_appointment, add_override
from tests.helpers import ist
from tests.integration.conftest import MONDAY, NOW, at

pytestmark = pytest.mark.integration


def book(api: Api, start: datetime | str = "2026-11-02T10:00:00+05:30", **changes: Any) -> Any:
    when = start if isinstance(start, str) else start.astimezone(at(0).tzinfo).isoformat()
    now = changes.pop("now", NOW)
    return api.post("/appointments", book_body(api, start_at=when, **changes), now=now)


def seed(api: Api, start: datetime, *, patient: int | None = None, **extra: Any) -> int:
    with api.clinic.factory() as session, session.begin():
        return add_appointment(
            session, api.clinic.rao, patient or api.clinic.asha, start, **extra
        ).id


# ------------------------------------------------------------------------------------ booking


def test_a_booking_returns_201_with_both_time_zones_and_the_allowed_actions(api: Api) -> None:
    response = book(api)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "BOOKED"
    assert (body["start_at_utc"], body["start_at_ist"]) == (
        "2026-11-02T04:30:00Z",
        "2026-11-02T10:00:00+05:30",
    )
    assert (body["end_at_utc"], body["end_at_ist"]) == (
        "2026-11-02T05:00:00Z",
        "2026-11-02T10:30:00+05:30",
    )
    assert (body["doctor_name"], body["patient_name"]) == ("Dr. Rao", "Asha Iyer")
    assert body["allowed_actions"] == ["check-in", "cancel", "reschedule"]
    assert body["needs_attention"] is False
    assert body["cancelled_at_utc"] is None
    assert response.headers["x-effective-now"] == "2026-11-02T02:30:00Z"


@pytest.mark.parametrize(
    "start",
    [
        "2026-11-02T04:30:00Z",
        "2026-11-02T04:30:00+00:00",
        "2026-11-02T10:00:00+05:30",
        "2026-11-02T15:30:00+11:00",
    ],
)
def test_every_spelling_of_the_same_instant_books_the_same_slot(api: Api, start: str) -> None:
    """T-B15: offsets are normalised, so 04:30 UTC is 10:00 in India whichever way it is written."""
    body = book(api, start).json()
    assert body["start_at_ist"] == "2026-11-02T10:00:00+05:30"


@pytest.mark.parametrize(
    ("start", "status", "code"),
    [
        ("2026-11-02T07:59:00+05:30", 422, "BOOKING_IN_PAST"),
        ("2026-11-02T08:00:00+05:30", 422, "BOOKING_IN_PAST"),  # a start equal to now is past
        ("2027-01-02T10:00:00+05:30", 422, "BOOKING_TOO_FAR"),
        ("2026-11-02T10:15:00+05:30", 422, "OFF_GRID"),
        ("2026-11-02T10:00:30+05:30", 422, "OFF_GRID"),
        ("2026-11-02T13:00:00+05:30", 422, "OUTSIDE_AVAILABILITY"),
        ("2026-11-07T10:00:00+05:30", 422, "OUTSIDE_AVAILABILITY"),  # a Saturday
    ],
)
def test_the_rules_answer_with_their_status_and_code(
    api: Api, start: str, status: int, code: str
) -> None:
    error = assert_error(book(api, start), status, code)
    assert error["message"].endswith(".")


def test_unknown_doctors_and_patients_are_404(api: Api) -> None:
    assert_error(book(api, doctor_id=999), 404, "DOCTOR_NOT_FOUND")
    assert_error(book(api, patient_id=999), 404, "PATIENT_NOT_FOUND")


def test_a_slot_taken_is_a_409_that_says_whose(api: Api) -> None:
    assert book(api).status_code == 201
    other = assert_error(book(api, patient_id=api.clinic.ravi), 409, "SLOT_TAKEN")
    assert other["details"]["same_patient"] is False
    double_click = assert_error(book(api), 409, "SLOT_TAKEN")
    assert double_click["details"]["same_patient"] is True


def test_a_patient_in_two_places_is_a_409(api: Api) -> None:
    assert book(api).status_code == 201
    error = assert_error(
        book(api, "2026-11-02T10:15:00+05:30", doctor_id=api.clinic.menon), 409, "PATIENT_OVERLAP"
    )
    assert isinstance(error["details"]["appointment_id"], int)


def test_a_full_day_is_a_409_with_the_cap(api: Api) -> None:
    api.patch(f"/doctors/{api.clinic.rao}", {"daily_cap": 1})
    assert book(api).status_code == 201
    error = assert_error(
        book(api, "2026-11-02T11:00:00+05:30", patient_id=api.clinic.ravi), 409, "DAILY_CAP_REACHED"
    )
    assert error["details"] == {"daily_cap": 1}


def strike_the_patient(api: Api, patient: int) -> None:
    with api.clinic.factory() as session, session.begin():
        add_appointment(
            session, api.clinic.rao, patient, ist(2026, 10, 29, 10), status=Status.NO_SHOW
        )
        add_appointment(
            session,
            api.clinic.rao,
            patient,
            ist(2026, 10, 28, 16, 30),
            status=Status.LATE_CANCELLED,
            cancelled_at=ist(2026, 10, 28, 15, 10),
            status_changed_at=ist(2026, 10, 28, 15, 10),
        )


def test_a_flagged_patient_needs_the_deposit_and_the_error_explains_why(api: Api) -> None:
    strike_the_patient(api, api.clinic.ravi)
    error = assert_error(book(api, patient_id=api.clinic.ravi), 422, "DEPOSIT_REQUIRED")
    assert error["details"]["required_until"] == "2026-11-27T15:10:00+05:30"
    assert [r["type"] for r in error["details"]["reasons"]] == ["NO_SHOW", "LATE_CANCELLED"]
    assert "2 late cancellations or no-shows in the last 30 days" in error["message"]

    accepted = book(api, patient_id=api.clinic.ravi, deposit_confirmed=True)
    assert accepted.status_code == 201
    assert (
        accepted.json()["deposit_required_at_booking"],
        accepted.json()["deposit_confirmed"],
    ) == (True, True)


# ---------------------------------------------------------------------------------- cancelling


def test_cancelling_with_no_body_is_a_patient_cancellation(api: Api) -> None:
    appointment_id = book(api).json()["id"]
    response = api.post(f"/appointments/{appointment_id}/cancel")
    assert response.status_code == 200
    body = response.json()
    assert (body["appointment"]["status"], body["late"]) == ("CANCELLED", False)
    assert body["appointment"]["cancelled_by"] == "PATIENT"
    assert body["appointment"]["cancelled_at_utc"] == "2026-11-02T02:30:00Z"
    assert body["appointment"]["allowed_actions"] == ["undo-cancel"]
    assert body["deposit"] == {
        "required": False,
        "required_until_utc": None,
        "required_until_ist": None,
        "reasons": [],
    }


def test_cancelling_under_two_hours_ahead_is_late_and_counts(api: Api) -> None:
    appointment_id = seed(api, at(10))
    response = api.post(
        f"/appointments/{appointment_id}/cancel", {"cancelled_by": "PATIENT"}, now=at(9)
    )
    assert response.json()["late"] is True
    assert response.json()["appointment"]["status"] == "LATE_CANCELLED"
    assert [r["type"] for r in response.json()["deposit"]["reasons"]] == ["LATE_CANCELLED"]


def test_the_clinic_cancelling_late_is_not_late(api: Api) -> None:
    appointment_id = seed(api, at(10))
    response = api.post(
        f"/appointments/{appointment_id}/cancel", {"cancelled_by": "CLINIC"}, now=at(9, 45)
    )
    assert (response.json()["late"], response.json()["appointment"]["status"]) == (
        False,
        "CANCELLED",
    )
    assert response.json()["deposit"]["reasons"] == []


@pytest.mark.parametrize(
    "body", [{"cancelled_by": "NOBODY"}, {"cancelled_by": None}, {"reason": "x"}, [], 5]
)
def test_a_bad_cancel_body_is_a_422(api: Api, body: Any) -> None:
    appointment_id = seed(api, at(12))
    assert_error(api.post(f"/appointments/{appointment_id}/cancel", body), 422, "VALIDATION_ERROR")


def test_cancelling_twice_and_cancelling_after_the_start_are_409s(api: Api) -> None:
    appointment_id = seed(api, at(12))
    assert api.post(f"/appointments/{appointment_id}/cancel").status_code == 200
    assert_error(api.post(f"/appointments/{appointment_id}/cancel"), 409, "INVALID_TRANSITION")


def test_cancelling_after_the_start_is_a_late_cancellation(api: Api) -> None:
    """Rule 5 read literally: later than 2 hours before the start, even after it, is late."""
    started = seed(api, at(9))
    body = api.post(f"/appointments/{started}/cancel", now=at(9, 10)).json()
    assert (body["late"], body["appointment"]["status"]) == (True, "LATE_CANCELLED")
    clinic = seed(api, at(9, 30), patient=api.clinic.ravi)
    by_clinic = api.post(
        f"/appointments/{clinic}/cancel", {"cancelled_by": "CLINIC"}, now=at(9, 40)
    )
    assert by_clinic.json()["late"] is False


def test_a_started_appointment_cannot_be_rescheduled(api: Api) -> None:
    started = seed(api, at(9))
    assert_error(
        api.post(
            f"/appointments/{started}/reschedule",
            {"start_at": "2026-11-02T11:00:00+05:30"},
            now=at(9, 5),
        ),
        409,
        "APPOINTMENT_ALREADY_STARTED",
    )


def test_cancelling_an_unknown_appointment_is_404(api: Api) -> None:
    assert_error(api.post("/appointments/999/cancel"), 404, "APPOINTMENT_NOT_FOUND")


# ----------------------------------------------------------------------------------- marking


def test_marking_follows_the_clock(api: Api) -> None:
    appointment_id = seed(api, at(12))
    assert_error(
        api.post(f"/appointments/{appointment_id}/no-show", now=at(11, 59)),
        409,
        "TOO_EARLY_TO_MARK",
    )
    assert_error(
        api.post(f"/appointments/{appointment_id}/complete", now=at(11, 59)),
        409,
        "TOO_EARLY_TO_MARK",
    )
    done = api.post(f"/appointments/{appointment_id}/complete", now=at(12))
    assert done.status_code == 200
    assert (done.json()["status"], done.json()["allowed_actions"]) == ("COMPLETED", ["correct"])
    assert_error(
        api.post(f"/appointments/{appointment_id}/no-show", now=at(12, 5)),
        409,
        "INVALID_TRANSITION",
    )


def test_a_no_show_is_marked_and_counts_as_a_strike_from_the_start_time(api: Api) -> None:
    appointment_id = seed(api, at(9))
    marked = api.post(f"/appointments/{appointment_id}/no-show", now=at(9, 20))
    assert marked.status_code == 200
    assert (marked.json()["status"], marked.json()["allowed_actions"]) == ("NO_SHOW", ["correct"])
    patient = api.get(f"/patients/{api.clinic.asha}", now=at(9, 30)).json()
    assert [r["type"] for r in patient["deposit"]["reasons"]] == ["NO_SHOW"]
    assert patient["deposit"]["reasons"][0]["at_ist"] == "2026-11-02T09:00:00+05:30"


def test_the_allowed_actions_change_when_the_appointment_starts(api: Api) -> None:
    appointment_id = seed(api, at(12))
    before = api.get(f"/appointments/{appointment_id}", now=at(11, 59)).json()
    after = api.get(f"/appointments/{appointment_id}", now=at(12)).json()
    assert before["allowed_actions"] == ["check-in", "cancel", "reschedule"]
    assert after["allowed_actions"] == ["check-in", "complete", "no-show", "cancel"]


# -------------------------------------------------------------------------------- rescheduling


def test_rescheduling_returns_the_old_and_the_new_appointment(api: Api) -> None:
    old_id = book(api).json()["id"]
    response = api.post(
        f"/appointments/{old_id}/reschedule", {"start_at": "2026-11-02T11:00:00+05:30"}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["old"]["status"], body["old"]["rescheduled_to_id"]) == (
        "CANCELLED",
        body["new"]["id"],
    )
    assert (body["new"]["status"], body["new"]["start_at_ist"]) == (
        "BOOKED",
        "2026-11-02T11:00:00+05:30",
    )


def test_rescheduling_to_another_doctor(api: Api) -> None:
    old_id = book(api).json()["id"]
    body = {"start_at": "2026-11-02T10:15:00+05:30", "doctor_id": api.clinic.menon}
    moved = api.post(f"/appointments/{old_id}/reschedule", body).json()
    assert moved["new"]["doctor_name"] == "Dr. Menon"


def test_a_failed_reschedule_leaves_the_old_appointment_booked(api: Api) -> None:
    old_id = book(api).json()["id"]
    book(api, "2026-11-02T11:00:00+05:30", patient_id=api.clinic.ravi)
    assert_error(
        api.post(f"/appointments/{old_id}/reschedule", {"start_at": "2026-11-02T11:00:00+05:30"}),
        409,
        "SLOT_TAKEN",
    )
    assert api.get(f"/appointments/{old_id}").json()["status"] == "BOOKED"


def test_rescheduling_to_the_same_slot_is_refused(api: Api) -> None:
    old_id = book(api).json()["id"]
    body = {"start_at": "2026-11-02T10:00:00+05:30"}
    assert_error(api.post(f"/appointments/{old_id}/reschedule", body), 422, "RESCHEDULE_NO_CHANGE")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"start_at": "2026-11-02T11:00:00"},
        {"start_at": "2026-11-02T11:00:00+05:30", "status": "BOOKED"},
    ],
)
def test_a_bad_reschedule_body_is_a_422(api: Api, body: dict[str, Any]) -> None:
    old_id = book(api).json()["id"]
    assert_error(api.post(f"/appointments/{old_id}/reschedule", body), 422, "VALIDATION_ERROR")


# ----------------------------------------------------------------------------- reading lists


def test_one_appointment_by_id(api: Api) -> None:
    appointment_id = book(api).json()["id"]
    body = api.get(f"/appointments/{appointment_id}").json()
    assert (body["id"], body["patient_phone"]) == (appointment_id, "+919000000001")
    assert_error(api.get("/appointments/999"), 404, "APPOINTMENT_NOT_FOUND")


def test_lists_are_paginated_and_filterable(api: Api) -> None:
    book(api)
    book(api, "2026-11-02T10:30:00+05:30", patient_id=api.clinic.ravi)
    book(api, "2026-11-03T09:00:00+05:30")
    everything = api.get("/appointments").json()
    assert (everything["total"], everything["limit"], everything["offset"]) == (3, 20, 0)
    assert [a["start_at_ist"][:16] for a in everything["items"]] == [
        "2026-11-02T10:00",
        "2026-11-02T10:30",
        "2026-11-03T09:00",
    ]
    assert api.get("/appointments", params={"date": "2026-11-03"}).json()["total"] == 1
    assert api.get("/appointments", params={"doctor_id": api.clinic.menon}).json()["total"] == 0
    assert api.get("/appointments", params={"status": "CANCELLED"}).json()["total"] == 0
    page = api.get("/appointments", params={"limit": 1, "offset": 2}).json()
    assert (page["total"], len(page["items"])) == (3, 1)


def test_the_needs_attention_list_finds_orphans(api: Api) -> None:
    appointment_id = book(api).json()["id"]
    with api.clinic.factory() as session, session.begin():
        add_override(session, api.clinic.rao, MONDAY, [])
    flagged = api.get("/appointments", params={"needs_attention": "true"}).json()
    assert [(a["id"], a["needs_attention"]) for a in flagged["items"]] == [(appointment_id, True)]
    assert api.get("/appointments", params={"needs_attention": "false"}).json()["total"] == 0


def test_a_patients_history_is_newest_first(api: Api) -> None:
    book(api)
    book(api, "2026-11-03T09:00:00+05:30")
    history = api.get(f"/patients/{api.clinic.asha}/appointments").json()
    assert [a["start_at_ist"][:10] for a in history["items"]] == ["2026-11-03", "2026-11-02"]
    assert_error(api.get("/patients/999/appointments"), 404, "PATIENT_NOT_FOUND")


def test_the_queue_defaults_to_today_by_the_clock_and_hides_cancelled_ones(api: Api) -> None:
    keep = book(api).json()["id"]
    drop = book(api, "2026-11-02T10:30:00+05:30", patient_id=api.clinic.ravi).json()["id"]
    api.post(f"/appointments/{drop}/cancel")
    queue = api.get("/queue").json()
    assert [a["id"] for a in queue] == [keep]
    with_cancelled = api.get("/queue", params={"include_cancelled": "true"}).json()
    assert [a["id"] for a in with_cancelled] == [keep, drop]
    assert api.get("/queue", now=NOW + timedelta(days=1)).json() == []  # tomorrow is empty


def test_every_slot_the_api_offers_is_accepted_by_the_api(api: Api) -> None:
    """T-P02 over HTTP: offer and accept cannot disagree. Each booking is undone afterwards."""
    book(api, "2026-11-02T10:00:00+05:30", patient_id=api.clinic.ravi)
    offered = api.get(
        f"/doctors/{api.clinic.rao}/slots",
        params={"date": "2026-11-02", "patient_id": api.clinic.asha},
        now=at(9, 10),
    ).json()["slots"]
    assert offered
    for slot in offered:
        response = book(api, slot["start_at_ist"], now=at(9, 10))
        assert response.status_code == 201, (slot, response.text)
        api.post(
            f"/appointments/{response.json()['id']}/cancel",
            {"cancelled_by": "CLINIC"},
            now=at(9, 10),
        )
