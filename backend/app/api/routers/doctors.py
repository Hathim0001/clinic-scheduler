"""Doctors: list, create, read and update."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from app.api.deps import NowDep, ServicesDep
from app.api.params import DoctorId
from app.api.presenters import doctor_out
from app.api.schemas.requests import DoctorCreate, DoctorPatch
from app.api.schemas.responses import DoctorOut

router = APIRouter(prefix="/doctors", tags=["doctors"])
log = structlog.get_logger()


@router.get("", response_model=list[DoctorOut], summary="List doctors")
def list_doctors(services: ServicesDep) -> list[DoctorOut]:
    return [doctor_out(d) for d in services.doctors.list()]


@router.post("", response_model=DoctorOut, status_code=201, summary="Create a doctor")
def create_doctor(body: DoctorCreate, services: ServicesDep) -> DoctorOut:
    view = services.doctors.create(body.name, body.speciality, body.slot_length_min, body.daily_cap)
    log.info("doctor.created", doctor_id=view.id)
    return doctor_out(view)


@router.get("/{doctor_id}", response_model=DoctorOut, summary="Get a doctor")
def get_doctor(doctor_id: DoctorId, services: ServicesDep) -> DoctorOut:
    return doctor_out(services.doctors.get(doctor_id))


@router.patch(
    "/{doctor_id}",
    response_model=DoctorOut,
    summary="Change a doctor's name, speciality, daily cap or slot length",
)
def update_doctor(
    doctor_id: DoctorId, body: DoctorPatch, services: ServicesDep, now: NowDep
) -> DoctorOut:
    """The slot length is locked while future bookings exist or windows would leave the grid."""
    view = services.doctors.update(doctor_id, now, **body.model_dump(exclude_unset=True))
    log.info("doctor.updated", doctor_id=view.id, fields=sorted(body.model_fields_set))
    return doctor_out(view)
