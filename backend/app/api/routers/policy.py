"""The clinic's own rules: how far ahead people book, the late-cancel window, the strike count,
the undo window, how long a freed slot is held and when reminders go out."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field, StrictInt, model_validator

from app.api.deps import AdminOnly, NowDep, ServicesDep
from app.api.schemas.types import StrictModel
from app.domain.policy import BOUNDS, DEFAULT_POLICY, FIELD_NAMES, Policy
from app.domain.timeutil import utc_iso
from app.services.policy_service import PolicyView

router = APIRouter(prefix="/policy", tags=["policy"])


# The ranges repeat domain/policy.BOUNDS; a test keeps the two in step.
HorizonDays = Annotated[StrictInt, Field(ge=1, le=365)]
LateCancelHours = Annotated[StrictInt, Field(ge=0, le=72)]
LookbackDays = Annotated[StrictInt, Field(ge=1, le=180)]
Strikes = Annotated[StrictInt, Field(ge=1, le=10)]
UndoMinutes = Annotated[StrictInt, Field(ge=0, le=60)]
OfferHoldMinutes = Annotated[StrictInt, Field(ge=5, le=240)]
FirstReminderHours = Annotated[StrictInt, Field(ge=0, le=168)]
SecondReminderHours = Annotated[StrictInt, Field(ge=0, le=48)]


class PolicyPatch(StrictModel):
    """Only the settings that are sent change. Each has an allowed range, shown in GET /policy."""

    horizon_days: HorizonDays | None = None
    late_cancel_hours: LateCancelHours | None = None
    strike_lookback_days: LookbackDays | None = None
    strikes: Strikes | None = None
    undo_minutes: UndoMinutes | None = None
    offer_hold_minutes: OfferHoldMinutes | None = None
    reminder_first_hours: FirstReminderHours | None = None
    reminder_second_hours: SecondReminderHours | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> PolicyPatch:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class PolicyOut(BaseModel):
    horizon_days: int
    late_cancel_hours: int
    strike_lookback_days: int
    strikes: int
    undo_minutes: int
    offer_hold_minutes: int
    reminder_first_hours: int
    reminder_second_hours: int
    defaults: dict[str, int]  # what each setting is when nobody has changed it
    bounds: dict[str, list[int]]  # [smallest, largest] allowed for each setting
    updated_at_utc: str | None
    updated_by: str | None


def _policy_values(policy: Policy) -> dict[str, int]:
    return {name: getattr(policy, name) for name in FIELD_NAMES}


def policy_out(view: PolicyView) -> PolicyOut:
    return PolicyOut(
        **_policy_values(view.policy),
        defaults=_policy_values(DEFAULT_POLICY),
        bounds={name: list(limits) for name, limits in BOUNDS.items()},
        updated_at_utc=utc_iso(view.updated_at) if view.updated_at else None,
        updated_by=view.updated_by,
    )


@router.get("", response_model=PolicyOut, summary="The clinic's current rules and their limits")
def get_policy(services: ServicesDep) -> PolicyOut:
    return policy_out(services.policy.get())


@router.patch(
    "",
    response_model=PolicyOut,
    summary="Change the clinic's rules (administrators only)",
    dependencies=[AdminOnly],
    responses={422: {"description": "VALIDATION_ERROR: a value outside its range"}},
)
def update_policy(body: PolicyPatch, services: ServicesDep, now: NowDep) -> PolicyOut:
    """Changes apply from the next request. Existing bookings are never rewritten: a changed
    late-cancel window, for example, decides cancellations made from now on."""
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    return policy_out(services.policy.update(changes, now))
