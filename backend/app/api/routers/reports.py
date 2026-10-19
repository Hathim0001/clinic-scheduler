"""A summary report, and the urgent-symptom check used by the booking form."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import ServicesDep
from app.api.params import OptionalId, RangeEnd, RangeStart
from app.api.presenters import report_out
from app.api.schemas.requests import TriageRequest
from app.api.schemas.responses import ReportOut, TriageOut
from app.domain.triage import EMERGENCY_MESSAGE, looks_urgent
from app.services.trends_service import TrendsView

router = APIRouter(tags=["reports"])

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: object) -> object:
    """A spreadsheet runs a cell that starts with = + - @ as a formula; a doctor's name must not."""
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        return "'" + value
    return value


@router.get(
    "/reports/summary",
    response_model=ReportOut,
    summary="Appointments, outcomes and utilisation per doctor for a range of India dates",
)
def summary(start: RangeStart, end: RangeEnd, services: ServicesDep) -> ReportOut:
    """At most 92 days. A rescheduled appointment counts once, as "rescheduled", never as a
    cancellation, and its replacement is not a new booking. The README gives every definition."""
    return report_out(services.records.summary(start, end))


@router.get(
    "/reports/summary.csv",
    response_class=Response,
    summary="The same report as a CSV file, one row per doctor and a total",
)
def summary_csv(start: RangeStart, end: RangeEnd, services: ServicesDep) -> Response:
    """For a spreadsheet. Names that could be read as formulas are quoted, so opening the file
    cannot run anything."""
    report = services.records.summary(start, end)
    rows = [asdict(d) for d in (*report.doctors, report.total)]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _safe_cell(value) for key, value in row.items()})
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report-{start}-{end}.csv"'},
    )


class DayTrendOut(BaseModel):
    date: date
    scheduled: int
    completed: int
    no_show: int
    cancelled: int
    upcoming: int


class BucketOut(BaseModel):
    key: int  # weekday (Monday is 0) or hour of the India day
    scheduled: int
    completed: int
    no_show: int
    no_show_rate: float | None


class ReminderEffectOut(BaseModel):
    reminded_visits: int
    reminded_no_shows: int
    other_visits: int
    other_no_shows: int


class TrendsOut(BaseModel):
    start: date
    end: date
    doctor_id: int | None
    days: list[DayTrendOut]
    weekdays: list[BucketOut]
    hours: list[BucketOut]
    reminder_effect: ReminderEffectOut


def trends_out(view: TrendsView) -> TrendsOut:
    return TrendsOut(
        start=view.start,
        end=view.end,
        doctor_id=view.doctor_id,
        days=[
            DayTrendOut(
                date=d.day,
                scheduled=d.scheduled,
                completed=d.completed,
                no_show=d.no_show,
                cancelled=d.cancelled,
                upcoming=d.upcoming,
            )
            for d in view.days
        ],
        weekdays=[BucketOut(**asdict(b)) for b in view.weekdays],
        hours=[BucketOut(**asdict(b)) for b in view.hours],
        reminder_effect=ReminderEffectOut(**asdict(view.reminder_effect)),
    )


@router.get(
    "/reports/trends",
    response_model=TrendsOut,
    summary="How each day went, the busiest weekdays and hours, and the effect of reminders",
)
def trends(
    start: RangeStart, end: RangeEnd, services: ServicesDep, doctor_id: OptionalId = None
) -> TrendsOut:
    """At most 92 days, for every doctor or one (`doctor_id`). A moved visit is left out of every
    outcome. The no-show rate is no-shows out of completed plus no-shows. `reminder_effect`
    compares visits whose patient was sent a reminder with the rest."""
    return trends_out(services.trends.trends(start, end, doctor_id))


@router.get(
    "/reports/trends.csv",
    response_class=Response,
    summary="The per-day series of the trends report as a CSV file",
)
def trends_csv(
    start: RangeStart, end: RangeEnd, services: ServicesDep, doctor_id: OptionalId = None
) -> Response:
    view = services.trends.trends(start, end, doctor_id)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["date", "scheduled", "completed", "no_show", "cancelled", "upcoming"])
    for d in view.days:
        writer.writerow([d.day, d.scheduled, d.completed, d.no_show, d.cancelled, d.upcoming])
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trends-{start}-{end}.csv"'},
    )


@router.post(
    "/triage",
    response_model=TriageOut,
    summary="Does this text describe symptoms that may need emergency care?",
)
def triage(body: TriageRequest) -> TriageOut:
    """A keyword check only: it never blocks a booking, it lets the form show a warning."""
    urgent = looks_urgent(body.text)
    return TriageOut(urgent=urgent, message=EMERGENCY_MESSAGE if urgent else None)
