"""The clinic's editable rules over HTTP: reading them, changing them, and each change doing what
it says to a real booking, cancellation, strike count, undo and waitlist offer."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.conftest import BASE, Api, clock, make_settings
from tests.api.test_hostile_input import assert_error, book_body
from tests.api.test_waitlist_series import join
from tests.integration.conftest import NOW, Clinic

pytestmark = pytest.mark.integration


def set_policy(api: Api, **values: Any) -> Any:
    response = api.patch("/policy", values)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_clinic_has_the_assignments_numbers(api: Api) -> None:
    body = api.get("/policy").json()
    assert (body["horizon_days"], body["late_cancel_hours"], body["strikes"]) == (60, 2, 2)
    assert (body["strike_lookback_days"], body["undo_minutes"]) == (30, 10)
    assert body["offer_hold_minutes"] == 30
    assert body["defaults"] == {k: body[k] for k in body["defaults"]}
    assert body["updated_at_utc"] is None
    assert body["bounds"]["late_cancel_hours"] == [0, 72]


def test_changes_are_saved_and_say_who_made_them(api: Api) -> None:
    body = set_policy(api, late_cancel_hours=4, strikes=3)
    assert (body["late_cancel_hours"], body["strikes"]) == (4, 3)
    assert body["horizon_days"] == 60  # what was not sent did not change
    assert body["updated_by"] == "anonymous"
    assert body["updated_at_utc"] is not None
    assert api.get("/policy").json()["late_cancel_hours"] == 4


@pytest.mark.parametrize(
    "bad",
    [
        {"horizon_days": 0},
        {"horizon_days": 366},
        {"late_cancel_hours": -1},
        {"strikes": 0},
        {"undo_minutes": 61},
        {"offer_hold_minutes": 4},
        {"horizon_days": "60"},
        {"horizon_days": 60.5},
        {"horizon_days": None},
        {"colour": "blue"},
    ],
)
def test_a_value_outside_its_range_or_of_the_wrong_kind_is_refused(
    api: Api, bad: dict[str, Any]
) -> None:
    assert_error(api.patch("/policy", bad), 422, "VALIDATION_ERROR")
    assert api.get("/policy").json()["horizon_days"] == 60


def test_two_reminders_at_the_same_hour_are_refused_and_nothing_is_saved(api: Api) -> None:
    refused = api.patch("/policy", {"reminder_first_hours": 3, "reminder_second_hours": 3})
    assert_error(refused, 422, "VALIDATION_ERROR")
    assert api.get("/policy").json()["reminder_first_hours"] == 24


def _book_and_cancel_three_hours_before(api: Api) -> str:
    booked = api.post("/appointments", book_body(api)).json()  # Monday 10:00
    cancelled = api.post(
        f"/appointments/{booked['id']}/cancel",
        {"cancelled_by": "PATIENT"},
        now=NOW - timedelta(hours=1),  # 07:00, three hours before
    )
    assert cancelled.status_code == 200, cancelled.text
    return str(cancelled.json()["appointment"]["status"])


def test_the_late_cancel_window_decides_a_three_hour_cancellation(api: Api) -> None:
    assert _book_and_cancel_three_hours_before(api) == "CANCELLED"


def test_a_four_hour_window_makes_the_same_cancellation_late(api: Api) -> None:
    set_policy(api, late_cancel_hours=4)
    assert _book_and_cancel_three_hours_before(api) == "LATE_CANCELLED"


def test_a_shorter_horizon_refuses_a_booking_the_default_allows(api: Api) -> None:
    far = book_body(api, start_at="2026-11-12T10:00:00+05:30")  # ten days ahead, a Thursday
    assert api.post("/appointments", far).status_code == 201
    set_policy(api, horizon_days=7)
    refused = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi) | far)
    body = assert_error(refused, 422, "BOOKING_TOO_FAR")
    assert body["details"]["horizon_days"] == 7
    assert "7 days" in body["message"]


def test_the_free_slot_list_follows_the_horizon(api: Api) -> None:
    set_policy(api, horizon_days=7)
    day = api.get(f"/doctors/{api.clinic.rao}/slots", params={"date": "2026-11-12"}).json()
    assert day["slots"] == []
    assert day["unavailable_reason"] == "DATE_TOO_FAR"


def _no_show_then_book_again(api: Api) -> Any:
    first = api.post("/appointments", book_body(api)).json()
    after = NOW + timedelta(hours=3)  # 11:00, after the 10:00 visit began
    assert api.post(f"/appointments/{first['id']}/no-show", now=after).status_code == 200
    again = book_body(api, start_at="2026-11-03T10:00:00+05:30")
    return api.post("/appointments", again, now=after)


def test_one_strike_is_not_enough_by_default(api: Api) -> None:
    assert _no_show_then_book_again(api).status_code == 201


def test_one_strike_requires_a_deposit_when_the_clinic_sets_one_strike(api: Api) -> None:
    set_policy(api, strikes=1)
    body = assert_error(_no_show_then_book_again(api), 422, "DEPOSIT_REQUIRED")
    assert "30 days" in body["message"]


def test_the_deposit_message_names_the_clinics_own_look_back(api: Api) -> None:
    set_policy(api, strikes=1, strike_lookback_days=14)
    body = assert_error(_no_show_then_book_again(api), 422, "DEPOSIT_REQUIRED")
    assert "14 days" in body["message"]


def test_the_patient_flag_follows_the_clinics_strike_count(api: Api) -> None:
    set_policy(api, strikes=1)
    first = api.post("/appointments", book_body(api)).json()
    after = NOW + timedelta(hours=3)
    api.post(f"/appointments/{first['id']}/no-show", now=after)
    flagged = api.get(f"/patients/{api.clinic.asha}", now=after).json()
    assert flagged["deposit_required"] is True


def test_undo_can_be_switched_off(api: Api) -> None:
    set_policy(api, undo_minutes=0)
    booked = api.post("/appointments", book_body(api)).json()
    cancelled = api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "PATIENT"})
    assert "undo-cancel" not in cancelled.json()["appointment"]["allowed_actions"]
    refused = api.post(f"/appointments/{booked['id']}/undo-cancel")
    assert_error(refused, 409, "UNDO_NOT_POSSIBLE")


def test_a_longer_undo_window_keeps_the_button_for_longer(api: Api) -> None:
    set_policy(api, undo_minutes=30)
    booked = api.post("/appointments", book_body(api)).json()
    api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "PATIENT"})
    undone = api.post(f"/appointments/{booked['id']}/undo-cancel", now=NOW + timedelta(minutes=25))
    assert undone.status_code == 200, undone.text


def test_the_hold_on_a_freed_slot_follows_the_policy(api: Api) -> None:
    set_policy(api, offer_hold_minutes=60)
    booked = api.post("/appointments", book_body(api, patient_id=api.clinic.ravi)).json()
    join(api, api.clinic.asha)
    api.post(f"/appointments/{booked['id']}/cancel", {"cancelled_by": "CLINIC"})
    [offer] = api.get(f"/patients/{api.clinic.asha}/waitlist").json()
    assert offer["status"] == "OFFERED"
    assert offer["offer_expires_at_utc"] == "2026-11-02T03:30:00Z"  # 09:00 IST, an hour after 08:00


def test_the_waitlist_opens_only_as_far_ahead_as_the_horizon(api: Api) -> None:
    set_policy(api, horizon_days=7)
    refused = api.post(
        f"/doctors/{api.clinic.rao}/waitlist",
        {"patient_id": api.clinic.asha, "date": "2026-11-12"},
    )
    assert_error(refused, 422, "BOOKING_TOO_FAR")


# ----------------------------------------------------------------------------- who may change it

SECRET = "a-long-random-signing-secret"
SHARED = "bootstrap-password"


@pytest.fixture
def accounts(clinic: Clinic, database_url: str) -> Iterator[Api]:
    settings = make_settings(database_url, auth_secret=SECRET, staff_password=SHARED)
    with TestClient(create_app(settings), raise_server_exceptions=False) as http:
        yield Api(http, clinic)


def _headers(api: Api, name: str, password: str) -> dict[str, str]:
    token = api.http.post(f"{BASE}/auth/login", json={"name": name, "password": password}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}", **clock(NOW)}


def test_a_receptionist_can_read_the_rules_but_not_change_them(accounts: Api) -> None:
    admin = _headers(accounts, "Boss", SHARED)
    created = accounts.http.post(
        f"{BASE}/staff",
        json={
            "username": "meera",
            "display_name": "Meera",
            "password": "a-good-password",
            "role": "RECEPTIONIST",
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    desk = _headers(accounts, "meera", "a-good-password")

    assert accounts.http.get(f"{BASE}/policy", headers=desk).status_code == 200
    refused = accounts.http.patch(f"{BASE}/policy", json={"strikes": 3}, headers=desk)
    assert_error(refused, 403, "FORBIDDEN")

    changed = accounts.http.patch(f"{BASE}/policy", json={"strikes": 3}, headers=admin)
    assert changed.status_code == 200
    assert changed.json()["updated_by"] == "Boss"
