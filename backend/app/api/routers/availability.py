"""A doctor's hours and what they mean for a day: weekly windows, date overrides, free slots and the
day schedule."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Query, Response

from app.api.deps import NowDep, ServicesDep
from app.api.errors import ApiError
from app.api.params import (
    BoolQuery,
    DayPath,
    DayQuery,
    DoctorId,
    OptionalId,
    RangeEnd,
    RangeStart,
)
from app.api.presenters import override_out, schedule_out, slots_out, weekly_out, weekly_window_out
from app.api.schemas.requests import OverridePut, WeeklyWindowsPut
from app.api.schemas.responses import (
    OverrideOut,
    ScheduleOut,
    SlotsOut,
    WeeklyOut,
)
from app.domain.errors import ErrorCode
from app.domain.model import MAX_APPOINTMENT_SLOTS, WeeklyWindow, Window

router = APIRouter(prefix="/doctors/{doctor_id}", tags=["availability"])
log = structlog.get_logger()

MAX_OVERRIDE_RANGE_DAYS = 90


@router.get("/weekly-windows", response_model=WeeklyOut, summary="The weekly pattern")
def get_weekly_windows(doctor_id: DoctorId, services: ServicesDep) -> WeeklyOut:
    windows = services.availability.weekly_windows(doctor_id)
    return WeeklyOut(windows=[weekly_window_out(w) for w in windows], needs_attention=[])


@router.put(
    "/weekly-windows",
    response_model=WeeklyOut,
    summary="Replace the weekly pattern",
    responses={409: {"description": "AVAILABILITY_CONFLICTS: future bookings would be orphaned"}},
)
def put_weekly_windows(
    doctor_id: DoctorId, body: WeeklyWindowsPut, services: ServicesDep, now: NowDep
) -> WeeklyOut:
    """Without `acknowledge_conflicts`, a change that leaves future bookings outside the new hours
    is refused with the list of those bookings; with it, they stay booked and need attention."""
    windows = [WeeklyWindow(w.weekday, w.start, w.end) for w in body.windows]
    view = services.availability.replace_weekly_windows(
        doctor_id, windows, body.acknowledge_conflicts, now
    )
    log.info(
        "availability.changed",
        doctor_id=doctor_id,
        kind="weekly",
        acknowledged=body.acknowledge_conflicts,
        orphaned=len(view.needs_attention),
    )
    return weekly_out(view)


@router.get("/overrides", response_model=list[OverrideOut], summary="Date overrides in a range")
def list_overrides(
    doctor_id: DoctorId,
    services: ServicesDep,
    first: RangeStart,
    last: RangeEnd,
) -> list[OverrideOut]:
    if last < first or last - first > timedelta(days=MAX_OVERRIDE_RANGE_DAYS):
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"The range must run forward and cover at most {MAX_OVERRIDE_RANGE_DAYS} days.",
            {"fields": [{"loc": ["query", "to"], "msg": "range out of bounds", "type": "range"}]},
        )
    return [override_out(o) for o in services.availability.overrides(doctor_id, first, last)]


@router.put(
    "/overrides/{day}",
    response_model=OverrideOut,
    summary="Create or replace the override for one date (no windows means leave)",
    responses={409: {"description": "AVAILABILITY_CONFLICTS: future bookings would be orphaned"}},
)
def put_override(
    doctor_id: DoctorId,
    day: DayPath,
    body: OverridePut,
    services: ServicesDep,
    now: NowDep,
) -> OverrideOut:
    windows = [Window(w.start, w.end) for w in body.windows]
    change = services.availability.put_override(
        doctor_id, day, windows, body.note or None, body.acknowledge_conflicts, now
    )
    log.info(
        "availability.changed",
        doctor_id=doctor_id,
        kind="override",
        date=day.isoformat(),
        leave=not windows,
        acknowledged=body.acknowledge_conflicts,
        orphaned=len(change.needs_attention),
    )
    return override_out(change)


@router.delete(
    "/overrides/{day}",
    status_code=204,
    summary="Remove the override for one date, back to the weekly pattern",
    responses={409: {"description": "AVAILABILITY_CONFLICTS: future bookings would be orphaned"}},
)
def delete_override(
    doctor_id: DoctorId,
    day: DayPath,
    services: ServicesDep,
    now: NowDep,
    acknowledge_conflicts: Annotated[BoolQuery, Query()] = False,
) -> Response:
    change = services.availability.delete_override(doctor_id, day, acknowledge_conflicts, now)
    log.info(
        "availability.changed",
        doctor_id=doctor_id,
        kind="override_removed",
        date=day.isoformat(),
        acknowledged=acknowledge_conflicts,
        orphaned=len(change.needs_attention),
    )
    return Response(status_code=204)


@router.get("/slots", response_model=SlotsOut, summary="Free slots on one India date")
def get_slots(
    doctor_id: DoctorId,
    day: DayQuery,
    services: ServicesDep,
    now: NowDep,
    patient_id: OptionalId = None,
    slots: Annotated[
        int, Query(ge=1, le=MAX_APPOINTMENT_SLOTS, description="Visit length in slots")
    ] = 1,
) -> SlotsOut:
    """With `patient_id`, times that overlap that patient's other appointments are left out. With
    `slots`, only starts where a visit of that many of the doctor's slots fits are listed."""
    return slots_out(services.availability.free_slots(doctor_id, day, patient_id, now, slots))


@router.get("/schedule", response_model=ScheduleOut, summary="Every slot of one day with its state")
def get_schedule(
    doctor_id: DoctorId,
    day: DayQuery,
    services: ServicesDep,
    now: NowDep,
    patient_id: OptionalId = None,
) -> ScheduleOut:
    return schedule_out(services.availability.day_schedule(doctor_id, day, patient_id, now))
