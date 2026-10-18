"""Doctors, availability, patients and the clock through the HTTP API."""

from __future__ import annotations

from typing import Any

import pytest

from app.persistence.models import AppMeta
from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body
from tests.integration.conftest import NOW

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------------------------ doctors


def test_a_doctor_is_created_read_and_changed(api: Api) -> None:
    created = api.post(
        "/doctors",
        {"name": "Dr. Iyer", "speciality": "ENT", "slot_length_min": 15, "daily_cap": 12},
    )
    assert created.status_code == 201
    doctor = created.json()
    assert doctor == {
        "id": 3,
        "name": "Dr. Iyer",
        "speciality": "ENT",
        "slot_length_min": 15,
        "daily_cap": 12,
        "accepting_bookings": True,
    }
    assert api.get("/doctors/3").json() == doctor
    changed = api.patch("/doctors/3", {"daily_cap": 8, "name": "Dr. R. Iyer"}).json()
    assert (changed["daily_cap"], changed["name"], changed["speciality"]) == (
        8,
        "Dr. R. Iyer",
        "ENT",
    )
    assert len(api.get("/doctors").json()) == 3


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Dr. A", "speciality": "ENT", "slot_length_min": 20, "daily_cap": 10},
        {"name": "Dr. A", "speciality": "ENT", "slot_length_min": 30, "daily_cap": 0},
        {"name": "Dr. A", "speciality": "ENT", "slot_length_min": 30, "daily_cap": 97},
        {"name": "Dr. A", "speciality": "ENT", "slot_length_min": 30.0, "daily_cap": 10},
        {"name": "Dr. A", "speciality": "ENT", "slot_length_min": 30},
        {"name": "   ", "speciality": "ENT", "slot_length_min": 30, "daily_cap": 10},
        {"name": "x" * 101, "speciality": "ENT", "slot_length_min": 30, "daily_cap": 10},
        {"name": "Dr. A\n", "speciality": "EN\x00T", "slot_length_min": 30, "daily_cap": 10},
    ],
)
def test_an_invalid_doctor_is_a_422(api: Api, body: dict[str, Any]) -> None:
    assert_error(api.post("/doctors", body), 422, "VALIDATION_ERROR")
    assert len(api.get("/doctors").json()) == 2


def test_a_patch_may_be_empty_but_never_null(api: Api) -> None:
    assert api.patch(f"/doctors/{api.clinic.rao}", {}).status_code == 200
    assert_error(api.patch(f"/doctors/{api.clinic.rao}", {"name": None}), 422, "VALIDATION_ERROR")
    assert_error(api.patch(f"/doctors/{api.clinic.rao}", {"id": 5}), 422, "VALIDATION_ERROR")
    assert_error(api.patch("/doctors/999", {"name": "Nobody"}), 404, "DOCTOR_NOT_FOUND")


def test_the_slot_length_is_locked_while_bookings_exist(api: Api) -> None:
    api.post(
        "/appointments",
        book_body(api, doctor_id=api.clinic.menon, start_at="2026-11-02T10:15:00+05:30"),
    )
    error = assert_error(
        api.patch(f"/doctors/{api.clinic.menon}", {"slot_length_min": 30}),
        409,
        "SLOT_LENGTH_LOCKED",
    )
    assert error["details"]["reason"] == "FUTURE_APPOINTMENTS"


# ------------------------------------------------------------------------------ weekly hours


def test_the_weekly_pattern_is_read_and_replaced(api: Api) -> None:
    rao = api.clinic.rao
    pattern = api.get(f"/doctors/{rao}/weekly-windows").json()
    assert pattern["windows"][0] == {"weekday": 0, "start": "09:00", "end": "13:00"}
    assert len(pattern["windows"]) == 5

    new = {
        "windows": [
            {"weekday": 5, "start": "10:00", "end": "12:00"},
            {"weekday": 5, "start": "14:00", "end": "24:00"},
        ]
    }
    saved = api.put(f"/doctors/{rao}/weekly-windows", new).json()
    assert saved["windows"] == [
        {"weekday": 5, "start": "10:00", "end": "12:00"},
        {"weekday": 5, "start": "14:00", "end": "24:00"},
    ]
    assert saved["needs_attention"] == []
    assert api.get(f"/doctors/{rao}/weekly-windows").json()["windows"] == saved["windows"]


@pytest.mark.parametrize(
    ("windows", "code"),
    [
        (
            [
                {"weekday": 0, "start": "09:00", "end": "13:00"},
                {"weekday": 0, "start": "12:00", "end": "14:00"},
            ],
            "WINDOW_OVERLAP",
        ),
        ([{"weekday": 0, "start": "09:00", "end": "13:10"}], "WINDOW_OFF_GRID"),
        ([{"weekday": 0, "start": "13:00", "end": "09:00"}], "VALIDATION_ERROR"),
        ([{"weekday": 7, "start": "09:00", "end": "13:00"}], "VALIDATION_ERROR"),
        ([{"weekday": 0, "start": "9:00", "end": "13:00"}], "VALIDATION_ERROR"),
        ([{"weekday": 0, "start": "09:00", "end": "25:00"}], "VALIDATION_ERROR"),
        ([{"weekday": 0, "start": "09:60", "end": "13:00"}], "VALIDATION_ERROR"),
        ([{"weekday": "0", "start": "09:00", "end": "13:00"}], "VALIDATION_ERROR"),
    ],
)
def test_bad_weekly_windows_are_a_422(api: Api, windows: list[dict[str, Any]], code: str) -> None:
    rao = api.clinic.rao
    assert_error(api.put(f"/doctors/{rao}/weekly-windows", {"windows": windows}), 422, code)
    assert len(api.get(f"/doctors/{rao}/weekly-windows").json()["windows"]) == 5


def test_a_change_that_orphans_a_booking_needs_acknowledging(api: Api) -> None:
    rao = api.clinic.rao
    booked = api.post("/appointments", book_body(api)).json()["id"]
    afternoon = {"windows": [{"weekday": 0, "start": "11:00", "end": "13:00"}]}
    error = assert_error(
        api.put(f"/doctors/{rao}/weekly-windows", afternoon), 409, "AVAILABILITY_CONFLICTS"
    )
    assert error["details"]["appointments"][0]["id"] == booked
    assert error["details"]["appointments"][0]["patient_name"] == "Asha Iyer"
    assert error["details"]["appointments"][0]["start_at_ist"] == "2026-11-02T10:00:00+05:30"

    saved = api.put(f"/doctors/{rao}/weekly-windows", afternoon | {"acknowledge_conflicts": True})
    assert saved.status_code == 200
    assert [a["id"] for a in saved.json()["needs_attention"]] == [booked]
    assert api.get(f"/appointments/{booked}").json()["needs_attention"] is True


# ------------------------------------------------------------------------------- overrides


def test_an_override_is_saved_listed_and_removed(api: Api) -> None:
    rao = api.clinic.rao
    saved = api.put(
        f"/doctors/{rao}/overrides/2026-11-07",
        {"windows": [{"start": "10:00", "end": "12:00"}], "note": "Camp"},
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "date": "2026-11-07",
        "note": "Camp",
        "windows": [{"start": "10:00", "end": "12:00"}],
        "needs_attention": [],
    }
    api.put(f"/doctors/{rao}/overrides/2026-11-09", {"windows": []})
    listed = api.get(
        f"/doctors/{rao}/overrides", params={"from": "2026-11-01", "to": "2026-11-30"}
    ).json()
    assert [(o["date"], o["windows"]) for o in listed] == [
        ("2026-11-07", [{"start": "10:00", "end": "12:00"}]),
        ("2026-11-09", []),
    ]
    assert api.delete(f"/doctors/{rao}/overrides/2026-11-07").status_code == 204
    assert (
        api.delete(f"/doctors/{rao}/overrides/2026-11-07").status_code == 204
    )  # nothing there: fine
    assert (
        len(
            api.get(
                f"/doctors/{rao}/overrides", params={"from": "2026-11-01", "to": "2026-11-30"}
            ).json()
        )
        == 1
    )


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-30", "to": "2026-11-01"},
        {"from": "2026-01-01", "to": "2026-12-31"},
        {"from": "2026-11-01"},
        {"from": "soon", "to": "later"},
    ],
)
def test_the_override_range_is_checked(api: Api, params: dict[str, str]) -> None:
    assert_error(
        api.get(f"/doctors/{api.clinic.rao}/overrides", params=params), 422, "VALIDATION_ERROR"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"windows": [{"start": "09:00", "end": "13:00"}], "note": "x" * 201},
        {"windows": [{"start": "09:00", "end": "13:00"}], "note": "bad\x00"},
        {"windows": [{"start": "09:00", "end": "13:00"}] * 21},
        {"note": "no windows key"},
        {"windows": [{"start": "09:00", "end": "13:00"}], "acknowledge_conflicts": "yes"},
    ],
)
def test_a_bad_override_body_is_a_422(api: Api, body: dict[str, Any]) -> None:
    assert_error(
        api.put(f"/doctors/{api.clinic.rao}/overrides/2026-11-09", body), 422, "VALIDATION_ERROR"
    )


def test_a_leave_day_over_a_booking_follows_the_conflict_protocol(api: Api) -> None:
    rao = api.clinic.rao
    booked = api.post("/appointments", book_body(api)).json()["id"]
    error = assert_error(
        api.put(f"/doctors/{rao}/overrides/2026-11-02", {"windows": []}),
        409,
        "AVAILABILITY_CONFLICTS",
    )
    assert error["details"]["date"] == "2026-11-02"
    saved = api.put(
        f"/doctors/{rao}/overrides/2026-11-02", {"windows": [], "acknowledge_conflicts": True}
    )
    assert [a["id"] for a in saved.json()["needs_attention"]] == [booked]

    day = api.get(f"/doctors/{rao}/schedule", params={"date": "2026-11-02"}).json()
    assert day["slots"] == []
    assert [a["id"] for a in day["outside_availability"]] == [booked]
    assert day["unavailable_reason"] == "NO_AVAILABILITY"


def test_removing_an_override_has_its_own_acknowledgement_flag(api: Api) -> None:
    rao = api.clinic.rao
    api.put(
        f"/doctors/{rao}/overrides/2026-11-07", {"windows": [{"start": "10:00", "end": "12:00"}]}
    )
    api.post("/appointments", book_body(api, start_at="2026-11-07T10:00:00+05:30"))
    assert_error(api.delete(f"/doctors/{rao}/overrides/2026-11-07"), 409, "AVAILABILITY_CONFLICTS")
    assert_error(
        api.delete(f"/doctors/{rao}/overrides/2026-11-07", params={"acknowledge_conflicts": "yes"}),
        422,
        "VALIDATION_ERROR",
    )
    ok = api.delete(
        f"/doctors/{rao}/overrides/2026-11-07", params={"acknowledge_conflicts": "true"}
    )
    assert ok.status_code == 204


# --------------------------------------------------------------------------- slots, schedule


def test_the_slot_list_has_windows_slots_and_a_reason_when_empty(api: Api) -> None:
    rao = api.clinic.rao
    day = api.get(f"/doctors/{rao}/slots", params={"date": "2026-11-02"}).json()
    assert (day["doctor_id"], day["date"], day["slot_length_min"], day["source"]) == (
        rao,
        "2026-11-02",
        30,
        "WEEKLY",
    )
    assert day["windows"] == [{"start": "09:00", "end": "13:00"}]
    assert day["slots"][0] == {
        "start_at_utc": "2026-11-02T03:30:00Z",
        "start_at_ist": "2026-11-02T09:00:00+05:30",
        "end_at_utc": "2026-11-02T04:00:00Z",
        "end_at_ist": "2026-11-02T09:30:00+05:30",
    }
    assert day["unavailable_reason"] is None
    sunday = api.get(f"/doctors/{rao}/slots", params={"date": "2026-11-08"}).json()
    assert (sunday["slots"], sunday["unavailable_reason"]) == ([], "NO_AVAILABILITY")
    past = api.get(f"/doctors/{rao}/slots", params={"date": "2026-10-30"}).json()
    assert past["unavailable_reason"] == "DATE_IN_PAST"


def test_the_schedule_marks_booked_free_and_busy_slots(api: Api) -> None:
    rao, asha = api.clinic.rao, api.clinic.asha
    booked = api.post("/appointments", book_body(api, start_at="2026-11-02T10:00:00+05:30")).json()
    api.post(
        "/appointments",
        book_body(api, doctor_id=api.clinic.menon, start_at="2026-11-02T11:00:00+05:30"),
    )
    day = api.get(
        f"/doctors/{rao}/schedule", params={"date": "2026-11-02", "patient_id": asha}
    ).json()
    states = {s["start_at_ist"][11:16]: s["state"] for s in day["slots"]}
    assert states["09:00"] == "FREE"
    assert states["10:00"] == "BOOKED"
    assert states["11:00"] == "BUSY"  # Asha is with Dr. Menon then
    cell = next(s for s in day["slots"] if s["state"] == "BOOKED")
    assert cell["appointment"]["id"] == booked["id"]
    assert all(s["appointment"] is None for s in day["slots"] if s["state"] != "BOOKED")
    assert_error(
        api.get(f"/doctors/{rao}/schedule", params={"date": "2026-11-02", "patient_id": "0"}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        api.get(f"/doctors/{rao}/schedule", params={"date": "2026-11-02", "patient_id": "999"}),
        404,
        "PATIENT_NOT_FOUND",
    )
    assert_error(
        api.get("/doctors/999/schedule", params={"date": "2026-11-02"}), 404, "DOCTOR_NOT_FOUND"
    )


# ---------------------------------------------------------------------------------- patients


def test_a_patient_is_registered_once_per_phone(api: Api) -> None:
    body = {"name": " Kiran Bose ", "phone": "98765 43210", "date_of_birth": "1985-04-02"}
    created = api.post("/patients", body)
    assert created.status_code == 201
    patient = created.json()
    assert (patient["name"], patient["phone"], patient["date_of_birth"]) == (
        "Kiran Bose",
        "+919876543210",
        "1985-04-02",
    )
    assert patient["deposit"]["required"] is False
    duplicate = assert_error(
        api.post("/patients", body | {"phone": "+91-98765-43210"}), 409, "PHONE_TAKEN"
    )
    assert duplicate["details"]["patient_id"] == patient["id"]


@pytest.mark.parametrize(
    "born", ["1899-12-31", "2026-11-03", "2026-02-30", "02/04/1985", 19850402, None]
)
def test_a_bad_date_of_birth_is_a_422(api: Api, born: Any) -> None:
    body = {"name": "Kiran Bose", "phone": "9876543210", "date_of_birth": born}
    assert_error(api.post("/patients", body), 422, "VALIDATION_ERROR")


def test_patients_are_found_by_phone_or_name_prefix_with_paging(api: Api) -> None:
    by_phone = api.get("/patients", params={"phone": "090000 00002"}).json()
    assert [p["name"] for p in by_phone["items"]] == ["Ravi Kumar"]
    assert by_phone["items"][0]["deposit"] is None  # search results do not compute it
    by_name = api.get("/patients", params={"q": "m"}).json()
    assert [p["name"] for p in by_name["items"]] == ["Meena Das"]
    assert api.get("/patients", params={"phone": "9811111111"}).json()["items"] == []
    page = api.get("/patients", params={"limit": 2, "offset": 1}).json()
    assert (page["total"], [p["name"] for p in page["items"]]) == (3, ["Meena Das", "Ravi Kumar"])
    assert_error(api.get("/patients", params={"phone": "12345"}), 422, "VALIDATION_ERROR")
    assert_error(api.get("/patients", params={"q": "x" * 101}), 422, "VALIDATION_ERROR")


def test_a_patient_shows_the_deposit_block_and_404_for_unknown(api: Api) -> None:
    body = api.get(f"/patients/{api.clinic.asha}").json()
    assert body["deposit"]["required"] is False
    assert_error(api.get("/patients/999"), 404, "PATIENT_NOT_FOUND")


# ------------------------------------------------------------------------------------ clock


def test_the_clock_reports_what_the_seed_recorded(api: Api) -> None:
    with api.clinic.factory() as session, session.begin():
        session.add_all(
            [
                AppMeta(key="seed_anchor_date", value="2026-10-17"),
                AppMeta(key="seed_queue_day", value="2026-10-19"),
            ]
        )
    body = api.get("/clock", now=NOW).json()
    assert (body["seed_anchor_date"], body["seed_queue_day"]) == ("2026-10-17", "2026-10-19")


def test_a_taken_phone_names_no_one_but_gives_the_id_to_search_by(api: Api) -> None:
    """Telling a caller who owns a number is a privacy leak, so only the id comes back."""
    taken = api.get(f"/patients/{api.clinic.asha}").json()["phone"]
    body = {"name": "Someone New", "phone": taken, "date_of_birth": "2010-01-01"}
    error = assert_error(api.post("/patients", body), 409, "PHONE_TAKEN")
    assert error["details"] == {"patient_id": api.clinic.asha}
    assert "Asha" not in error["message"]


def test_a_phone_cannot_be_moved_onto_another_patients_number(api: Api) -> None:
    taken = api.get(f"/patients/{api.clinic.ravi}").json()["phone"]
    assert_error(api.patch(f"/patients/{api.clinic.asha}", {"phone": taken}), 409, "PHONE_TAKEN")
    assert api.get(f"/patients/{api.clinic.asha}").json()["phone"] != taken
