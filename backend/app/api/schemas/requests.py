"""Request bodies. A client cannot send `end_at` or `status`: the server decides those."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StrictBool, model_validator

from app.api.schemas.types import (
    BirthDate,
    CorrectionNote,
    DailyCap,
    EntityId,
    Instant,
    IsoDate,
    Note,
    PersonName,
    PhoneText,
    Reason,
    SlotLength,
    StrictModel,
    TimeOfDay,
    Weekday,
)
from app.domain.model import MAX_APPOINTMENT_SLOTS


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
    accepting_bookings: StrictBool | None = None

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


class LoginRequest(StrictModel):
    name: PersonName
    password: Annotated[str, Field(strict=True, min_length=1, max_length=200)]


class StaffCreate(StrictModel):
    username: Annotated[str, Field(strict=True, pattern=r"^[a-z0-9._-]{3,40}$")]
    display_name: PersonName
    password: Annotated[str, Field(strict=True, min_length=8, max_length=200)]
    role: Literal["ADMIN", "RECEPTIONIST"]


class StaffPatch(StrictModel):
    """Only the fields that are sent change."""

    display_name: PersonName | None = None
    password: Annotated[str, Field(strict=True, min_length=8, max_length=200)] | None = None
    role: Literal["ADMIN", "RECEPTIONIST"] | None = None
    active: StrictBool | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> StaffPatch:
        if not self.model_fields_set:
            raise ValueError("send at least one of display_name, password, role, active")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class PatientCreate(StrictModel):
    name: PersonName
    phone: PhoneText
    date_of_birth: BirthDate
    allow_duplicate: StrictBool = False  # register even if the same name and birth date exist
    consent: StrictBool = False  # the privacy notice was accepted
    consent_by: Literal["PATIENT", "GUARDIAN"] = "PATIENT"  # a child needs a parent or guardian


class ConsentRequest(StrictModel):
    consent_by: Literal["PATIENT", "GUARDIAN"] = "PATIENT"


class PatientPatch(StrictModel):
    """Only the fields that are sent change. A field sent as null is refused, not ignored."""

    name: PersonName | None = None
    phone: PhoneText | None = None
    date_of_birth: BirthDate | None = None
    allow_duplicate: StrictBool = False

    @model_validator(mode="after")
    def _something_to_change(self) -> PatientPatch:
        sent = self.model_fields_set - {"allow_duplicate"}
        if not sent:
            raise ValueError("send at least one of name, phone, date_of_birth")
        for field in sent:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class CorrectRequest(StrictModel):
    status: Literal["COMPLETED", "NO_SHOW", "CANCELLED"]
    note: CorrectionNote  # why: kept in the appointment's history


class TriageRequest(StrictModel):
    text: Annotated[str, Field(strict=True, max_length=1000)]


class BookRequest(StrictModel):
    doctor_id: EntityId
    patient_id: EntityId
    start_at: Instant
    reason: Reason
    deposit_confirmed: StrictBool = False
    slots: Annotated[int, Field(strict=True, ge=1, le=MAX_APPOINTMENT_SLOTS)] = 1

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "doctor_id": 1,
                    "patient_id": 1,
                    "start_at": "2026-11-02T10:30:00+05:30",
                    "reason": "Fever for two days",
                }
            ]
        }
    )


class RecurringBookRequest(BookRequest):
    every_days: Annotated[int, Field(strict=True, ge=1, le=60)]
    count: Annotated[int, Field(strict=True, ge=2, le=12)]


class WaitlistJoinRequest(StrictModel):
    patient_id: EntityId
    date: IsoDate


class WaitlistAcceptRequest(StrictModel):
    reason: Reason
    deposit_confirmed: StrictBool = False


class CancelRequest(StrictModel):
    cancelled_by: Literal["PATIENT", "CLINIC"] = "PATIENT"


class RescheduleRequest(StrictModel):
    start_at: Instant
    doctor_id: EntityId | None = None
    deposit_confirmed: StrictBool | None = None
    # Who is moving it. A clinic move never counts against the patient, as with a clinic cancel.
    by: Literal["PATIENT", "CLINIC"] = "PATIENT"
    # A patient move that would be recorded as a late cancellation must be confirmed.
    acknowledge_late: StrictBool = False

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"start_at": "2026-11-03T11:00:00+05:30", "by": "CLINIC"}]}
    )
