"""A summary report, and the urgent-symptom check used by the booking form."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ServicesDep
from app.api.params import RangeEnd, RangeStart
from app.api.presenters import report_out
from app.api.schemas.requests import TriageRequest
from app.api.schemas.responses import ReportOut, TriageOut
from app.domain.triage import EMERGENCY_MESSAGE, looks_urgent

router = APIRouter(tags=["reports"])


@router.get(
    "/reports/summary",
    response_model=ReportOut,
    summary="Appointments, outcomes and utilisation per doctor for a range of India dates",
)
def summary(start: RangeStart, end: RangeEnd, services: ServicesDep) -> ReportOut:
    """At most 92 days. A rescheduled appointment counts once, as "rescheduled", never as a
    cancellation, and its replacement is not a new booking. The README gives every definition."""
    return report_out(services.records.summary(start, end))


@router.post(
    "/triage",
    response_model=TriageOut,
    summary="Does this text describe symptoms that may need emergency care?",
)
def triage(body: TriageRequest) -> TriageOut:
    """A keyword check only: it never blocks a booking, it lets the form show a warning."""
    urgent = looks_urgent(body.text)
    return TriageOut(urgent=urgent, message=EMERGENCY_MESSAGE if urgent else None)
