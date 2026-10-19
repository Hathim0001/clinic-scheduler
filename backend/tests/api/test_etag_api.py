"""If-Match on appointment actions: act only if nobody changed the appointment since it was read."""

from __future__ import annotations

import pytest

from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body

pytestmark = pytest.mark.integration


def test_an_appointment_carries_an_etag_that_matches_the_header(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    response = api.get(f"/appointments/{booked['id']}")
    assert response.headers["etag"] == f'"{booked["etag"]}"'


def test_the_etag_changes_when_the_appointment_does(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    changed = api.post(f"/appointments/{booked['id']}/confirmed-by-phone").json()
    assert changed["etag"] != booked["etag"]


def test_a_current_etag_lets_the_action_through(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    done = api.post(
        f"/appointments/{booked['id']}/cancel", headers={"If-Match": f'"{booked["etag"]}"'}
    )
    assert done.status_code == 200


def test_a_stale_etag_is_refused_and_nothing_changes(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    api.post(f"/appointments/{booked['id']}/confirmed-by-phone")

    stale = api.post(
        f"/appointments/{booked['id']}/cancel", headers={"If-Match": f'"{booked["etag"]}"'}
    )

    error = assert_error(stale, 412, "PRECONDITION_FAILED")
    assert error["details"]["current_etag"] != booked["etag"]
    assert api.get(f"/appointments/{booked['id']}").json()["status"] == "BOOKED"


@pytest.mark.parametrize("action", ["complete", "no-show", "check-in", "confirmed-by-phone"])
def test_every_action_honours_if_match(api: Api, action: str) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    refused = api.post(f"/appointments/{booked['id']}/{action}", headers={"If-Match": '"old"'})
    assert_error(refused, 412, "PRECONDITION_FAILED")


def test_reschedule_honours_if_match(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    body = {"start_at": "2026-11-02T11:00:00+05:30"}
    refused = api.post(
        f"/appointments/{booked['id']}/reschedule", body, headers={"If-Match": '"old"'}
    )
    assert_error(refused, 412, "PRECONDITION_FAILED")


def test_a_star_or_no_header_means_act_regardless(api: Api) -> None:
    booked = api.post("/appointments", book_body(api)).json()
    api.post(f"/appointments/{booked['id']}/confirmed-by-phone")
    assert (
        api.post(f"/appointments/{booked['id']}/cancel", headers={"If-Match": "*"}).status_code
        == 200
    )
