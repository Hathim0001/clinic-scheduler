"""The trends endpoints over HTTP."""

from __future__ import annotations

import pytest

from tests.api.conftest import Api
from tests.api.test_hostile_input import assert_error, book_body

pytestmark = pytest.mark.integration


def test_the_trends_endpoint_returns_days_weekdays_hours_and_the_reminder_comparison(
    api: Api,
) -> None:
    api.post("/appointments", book_body(api))
    body = api.get("/reports/trends", params={"from": "2026-11-02", "to": "2026-11-04"}).json()
    assert [d["date"] for d in body["days"]] == ["2026-11-02", "2026-11-03", "2026-11-04"]
    assert body["days"][0]["scheduled"] == 1
    assert body["days"][0]["upcoming"] == 1
    assert len(body["weekdays"]) == 7
    assert [h["key"] for h in body["hours"]] == [10]
    assert set(body["reminder_effect"]) == {
        "reminded_visits",
        "reminded_no_shows",
        "other_visits",
        "other_no_shows",
    }
    assert body["doctor_id"] is None


def test_a_doctor_filter_narrows_the_series(api: Api) -> None:
    api.post("/appointments", book_body(api))
    params = {"from": "2026-11-02", "to": "2026-11-02"}
    rao = api.get("/reports/trends", params=params | {"doctor_id": api.clinic.rao}).json()
    menon = api.get("/reports/trends", params=params | {"doctor_id": api.clinic.menon}).json()
    assert rao["days"][0]["scheduled"] == 1
    assert menon["days"][0]["scheduled"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-04", "to": "2026-11-02"},
        {"from": "2026-01-01", "to": "2026-12-31"},
        {"from": "not-a-date", "to": "2026-11-02"},
        {"from": "2026-11-02", "to": "2026-11-03", "doctor_id": "0"},
    ],
)
def test_a_bad_range_is_a_clean_422(api: Api, params: dict[str, str]) -> None:
    assert_error(api.get("/reports/trends", params=params), 422, "VALIDATION_ERROR")


def test_the_trends_csv_has_one_row_per_day(api: Api) -> None:
    api.post("/appointments", book_body(api))
    response = api.get("/reports/trends.csv", params={"from": "2026-11-02", "to": "2026-11-03"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().split("\r\n")
    assert lines[0] == "date,scheduled,completed,no_show,cancelled,upcoming"
    assert lines[1] == "2026-11-02,1,0,0,0,1"
    assert len(lines) == 3
