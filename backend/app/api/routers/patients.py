"""Patients: register, look up by phone or name, and see a patient's deposit status and history."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Query, Response

from app.api.deps import AdminOnly, NowDep, ServicesDep
from app.api.ics import calendar_text
from app.api.params import Limit, Offset, PatientId
from app.api.presenters import appointment_out, export_out, patient_out
from app.api.schemas.requests import PatientCreate, PatientPatch
from app.api.schemas.responses import AppointmentOut, PageOut, PatientExportOut, PatientOut
from app.domain.model import Status

router = APIRouter(prefix="/patients", tags=["patients"])
log = structlog.get_logger()


@router.get("", response_model=PageOut[PatientOut], summary="Search patients")
def search_patients(
    services: ServicesDep,
    phone: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=100, description="Name prefix")] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PageOut[PatientOut]:
    """`phone` matches exactly after normalisation; `q` is a case-insensitive name prefix. An
    unknown phone is an empty page, not a 404."""
    page = services.patients.search(phone=phone, name_prefix=q, limit=limit, offset=offset)
    return PageOut[PatientOut](
        items=[patient_out(p) for p in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "",
    response_model=PatientOut,
    status_code=201,
    summary="Register a patient",
    responses={
        409: {"description": "PHONE_TAKEN, or POSSIBLE_DUPLICATE with the matching patients"}
    },
)
def create_patient(body: PatientCreate, services: ServicesDep, now: NowDep) -> PatientOut:
    view = services.patients.create(
        body.name, body.phone, body.date_of_birth, now, body.allow_duplicate, body.consent
    )
    log.info("patient.created", patient_id=view.id)
    return patient_out(view)


@router.get("/{patient_id}", response_model=PatientOut, summary="A patient with the deposit status")
def get_patient(patient_id: PatientId, services: ServicesDep, now: NowDep) -> PatientOut:
    return patient_out(services.patients.get(patient_id, now))


@router.get(
    "/{patient_id}/appointments",
    response_model=PageOut[AppointmentOut],
    summary="A patient's appointments, newest first",
)
def patient_appointments(
    patient_id: PatientId,
    services: ServicesDep,
    now: NowDep,
    status: Status | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PageOut[AppointmentOut]:
    page = services.queries.for_patient(patient_id, status, limit, offset, now)
    return PageOut[AppointmentOut](
        items=[appointment_out(a) for a in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{patient_id}/calendar.ics",
    summary="Download a patient's upcoming booked appointments as a calendar (iCalendar)",
    response_class=Response,
)
def patient_calendar(patient_id: PatientId, services: ServicesDep, now: NowDep) -> Response:
    page = services.queries.for_patient(patient_id, Status.BOOKED, 100, 0, now)
    upcoming = [a for a in page.items if a.start_at >= now]
    return Response(
        calendar_text(upcoming, now),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="patient-{patient_id}.ics"'},
    )


@router.patch(
    "/{patient_id}",
    response_model=PatientOut,
    summary="Correct a patient's name, phone number or date of birth",
    responses={409: {"description": "PHONE_TAKEN or POSSIBLE_DUPLICATE"}},
)
def update_patient(
    patient_id: PatientId, body: PatientPatch, services: ServicesDep, now: NowDep
) -> PatientOut:
    """Appointments follow the patient. Only the fields that are sent change."""
    changes = body.model_dump(exclude_unset=True)
    view = services.patients.update(patient_id, now, **changes)
    log.info("patient.updated", patient_id=patient_id, fields=sorted(changes))
    return patient_out(view)


@router.post(
    "/{patient_id}/consent",
    response_model=PatientOut,
    summary="Record that the patient accepted the privacy notice",
)
def record_consent(patient_id: PatientId, services: ServicesDep, now: NowDep) -> PatientOut:
    view = services.patients.record_consent(patient_id, now)
    log.info("patient.consent_recorded", patient_id=patient_id)
    return patient_out(view)


@router.post(
    "/{patient_id}/erase",
    response_model=PatientOut,
    summary="Erase a patient's personal data on request",
    responses={409: {"description": "PATIENT_HAS_UPCOMING: cancel or complete those first"}},
    dependencies=[AdminOnly],
)
def erase_patient(patient_id: PatientId, services: ServicesDep, now: NowDep) -> PatientOut:
    """Name, phone, date of birth and appointment reasons are replaced; the appointments stay as
    anonymous history. Repeating it changes nothing."""
    view = services.patients.erase(patient_id, now)
    log.info("patient.erased", patient_id=patient_id)
    return patient_out(view)


@router.get(
    "/{patient_id}/export",
    response_model=PatientExportOut,
    summary="Everything held about a patient: details, every appointment and its history",
    dependencies=[AdminOnly],
)
def export_patient(patient_id: PatientId, services: ServicesDep, now: NowDep) -> PatientExportOut:
    patient = services.patients.get(patient_id, now)
    return export_out(services.records.patient_export(patient_id, patient, now))
