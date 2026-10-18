"""Staff accounts (administrators only)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ServicesDep
from app.api.schemas.requests import StaffCreate, StaffPatch
from app.domain.model import Role
from app.services.staff_service import StaffView

router = APIRouter(prefix="/staff", tags=["staff"])
log = structlog.get_logger()


class StaffOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    active: bool


def staff_out(view: StaffView) -> StaffOut:
    return StaffOut(
        id=view.id,
        username=view.username,
        display_name=view.display_name,
        role=view.role.value,
        active=view.active,
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
    view = services.staff.create(body.username, body.display_name, body.password, Role(body.role))
    log.info("staff.created", staff_id=view.id, role=view.role.value)
    return staff_out(view)


@router.patch(
    "/{staff_id}",
    response_model=StaffOut,
    summary="Change a role, deactivate or reactivate, or reset a password",
    responses={409: {"description": "LAST_ADMIN: the clinic needs one active administrator"}},
)
def update_staff(staff_id: int, body: StaffPatch, services: ServicesDep) -> StaffOut:
    changes = body.model_dump(exclude_unset=True)
    if "role" in changes:
        changes["role"] = Role(changes["role"])
    view = services.staff.update(staff_id, **changes)
    log.info("staff.updated", staff_id=staff_id, fields=sorted(changes))
    return staff_out(view)
