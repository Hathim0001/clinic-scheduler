"""The day's queue: everything booked for one India date, in time order."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import NowDep, ServicesDep
from app.api.params import BoolQuery, OptionalDayQuery, OptionalId
from app.api.presenters import appointment_out
from app.api.schemas.responses import AppointmentOut
from app.domain.timeutil import ist_date

router = APIRouter(tags=["queue"])


@router.get("/queue", response_model=list[AppointmentOut], summary="The queue for one day")
def get_queue(
    services: ServicesDep,
    now: NowDep,
    day: OptionalDayQuery = None,
    doctor_id: OptionalId = None,
    include_cancelled: Annotated[BoolQuery, Query()] = False,
) -> list[AppointmentOut]:
    """`date` defaults to today in India by the effective clock. Cancelled appointments are hidden
    unless `include_cancelled=true`. The UI enables each button from `allowed_actions`."""
    queue_day = day if day is not None else ist_date(now)
    views = services.queries.queue(queue_day, doctor_id, include_cancelled, now)
    return [appointment_out(v) for v in views]
