"""Request bodies. A client cannot send `end_at` or `status`: the server decides those."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, model_validator

from app.api.schemas.types import (
    BirthDate,
    DailyCap,
    EntityId,
    Instant,
    Note,
    PersonName,
    PhoneText,
    Reason,
    SlotLength,
    StrictModel,
    TimeOfDay,
    Weekday,
)


class DoctorCreate(StrictModel):
    name: PersonName
    speciality: PersonName
    slot_length_min: SlotLength
    daily_cap: DailyCap


class DoctorPatch(StrictModel):
    """Only the fields that are sent change. A field sent as null is refused, not ignored."""

    name: PersonName | None = None
    speciality: PersonName | None = None
    slot_length_min: SlotLength | None = None
    daily_cap: DailyCap | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> DoctorPatch:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class WindowIn(StrictModel):
    start: TimeOfDay
    end: TimeOfDay


class WeeklyWindowIn(WindowIn):
    weekday: Weekday


class WeeklyWindowsPut(StrictModel):
    windows: list[WeeklyWindowIn] = Field(max_length=70)
    acknowledge_conflicts: StrictBool = False


class OverridePut(StrictModel):
    windows: list[WindowIn] = Field(max_length=20)
    note: Note | None = None
    acknowledge_conflicts: StrictBool = False


class PatientCreate(StrictModel):
    name: PersonName
    phone: PhoneText
    date_of_birth: BirthDate


class BookRequest(StrictModel):
    doctor_id: EntityId
    patient_id: EntityId
    start_at: Instant
    reason: Reason
    deposit_confirmed: StrictBool = False


class CancelRequest(StrictModel):
    cancelled_by: Literal["PATIENT", "CLINIC"] = "PATIENT"


class RescheduleRequest(StrictModel):
    start_at: Instant
    doctor_id: EntityId | None = None
    deposit_confirmed: StrictBool | None = None
