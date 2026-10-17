"""Patients: register, look up by phone or name, and see a patient's deposit status and history."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Query

from app.api.deps import NowDep, ServicesDep
from app.api.params import Limit, Offset, PatientId
from app.api.presenters import appointment_out, patient_out
from app.api.schemas.requests import PatientCreate
from app.api.schemas.responses import AppointmentOut, PageOut, PatientOut
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


@router.post("", response_model=PatientOut, status_code=201, summary="Register a patient")
def create_patient(body: PatientCreate, services: ServicesDep, now: NowDep) -> PatientOut:
    view = services.patients.create(body.name, body.phone, body.date_of_birth, now)
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
