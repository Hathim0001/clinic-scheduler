"""Where to go when the time asked for is not available."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import NowDep, ServicesDep
from app.api.params import DayQuery, DoctorIdQuery, OptionalId
from app.api.presenters import alternative_out
from app.api.schemas.responses import AlternativeOut
from app.domain.model import MAX_APPOINTMENT_SLOTS

router = APIRouter(tags=["availability"])


@router.get(
    "/alternatives",
    response_model=list[AlternativeOut],
    summary="The nearest bookable times when the asked-for day is full",
)
def get_alternatives(
    doctor_id: DoctorIdQuery,
    day: DayQuery,
    services: ServicesDep,
    now: NowDep,
    patient_id: OptionalId = None,
    slots: Annotated[int, Query(ge=1, le=MAX_APPOINTMENT_SLOTS)] = 1,
    limit: Annotated[int, Query(ge=1, le=12)] = 6,
) -> list[AlternativeOut]:
    """The same doctor's next free days first, then other doctors (same speciality first). Every
    option passed the same checks as booking, for this patient and visit length."""
    options = services.alternatives.nearest(doctor_id, day, patient_id, now, slots, limit)
    return [alternative_out(option) for option in options]
