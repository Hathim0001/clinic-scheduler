"""A summary report, and the urgent-symptom check used by the booking form."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import ServicesDep
from app.api.params import RangeEnd, RangeStart
from app.api.presenters import report_out
from app.api.schemas.requests import TriageRequest
from app.api.schemas.responses import ReportOut, TriageOut
from app.domain.triage import EMERGENCY_MESSAGE, looks_urgent

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


@router.post(
    "/triage",
    response_model=TriageOut,
    summary="Does this text describe symptoms that may need emergency care?",
)
def triage(body: TriageRequest) -> TriageOut:
    """A keyword check only: it never blocks a booking, it lets the form show a warning."""
    urgent = looks_urgent(body.text)
    return TriageOut(urgent=urgent, message=EMERGENCY_MESSAGE if urgent else None)
