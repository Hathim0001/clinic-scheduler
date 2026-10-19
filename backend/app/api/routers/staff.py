"""Staff accounts (administrators only)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import NowDep, ServicesDep
from app.api.params import StaffId
from app.api.schemas.requests import StaffCreate, StaffPatch
from app.domain.model import Role
from app.domain.timeutil import utc_iso
from app.services.staff_service import StaffView

router = APIRouter(prefix="/staff", tags=["staff"])
log = structlog.get_logger()


class StaffOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    active: bool
    doctor_id: int | None = None


class ResetCodeOut(BaseModel):
    code: str  # shown once; only a hash is kept
    expires_at_utc: str


def staff_out(view: StaffView) -> StaffOut:
    return StaffOut(
        id=view.id,
        username=view.username,
        display_name=view.display_name,
        role=view.role.value,
        active=view.active,
        doctor_id=view.doctor_id,
    )


@router.get("", response_model=list[StaffOut], summary="List staff accounts")
def list_staff(services: ServicesDep) -> list[StaffOut]:
    return [staff_out(v) for v in services.staff.list()]


@router.post(
    "",
    response_model=StaffOut,
    status_code=201,
    summary="Create a staff account",
    responses={409: {"description": "STAFF_USERNAME_TAKEN"}},
)
def create_staff(body: StaffCreate, services: ServicesDep) -> StaffOut:
    view = services.staff.create(
        body.username, body.display_name, body.password, Role(body.role), body.doctor_id
    )
    log.info("staff.created", staff_id=view.id, role=view.role.value)
    return staff_out(view)


@router.patch(
    "/{staff_id}",
    response_model=StaffOut,
    summary="Change a role, deactivate or reactivate, or reset a password",
    responses={409: {"description": "LAST_ADMIN: the clinic needs one active administrator"}},
)
def update_staff(
    staff_id: StaffId, body: StaffPatch, services: ServicesDep, now: NowDep
) -> StaffOut:
    changes = body.model_dump(exclude_unset=True)
    if "role" in changes:
        changes["role"] = Role(changes["role"])
    if "doctor_id" in changes:
        changes["doctor_id_given"] = True
    view = services.staff.update(staff_id, now, **changes)
    log.info("staff.updated", staff_id=staff_id, fields=sorted(changes))
    return staff_out(view)


@router.post(
    "/{staff_id}/reset-code",
    response_model=ResetCodeOut,
    summary="Issue a single-use code so this person can choose a new password",
    responses={404: {"description": "STAFF_NOT_FOUND"}},
)
def issue_reset_code(staff_id: StaffId, services: ServicesDep, now: NowDep) -> ResetCodeOut:
    """Valid for one hour and works once. Give it to the person yourself (in person or by phone):
    it is shown only in this response, and a new code replaces any earlier one."""
    issued = services.staff.issue_reset_code(staff_id, now)
    log.info("staff.reset_code_issued", staff_id=staff_id)
    return ResetCodeOut(code=issued.code, expires_at_utc=utc_iso(issued.expires_at))
