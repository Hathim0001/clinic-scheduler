"""Turning a broken rule into the error the client sees: a sentence a receptionist can act on, and
structured details the UI can use.

The rule functions only say *which* rule broke (an ErrorCode). The wording lives here, in one place,
so booking, rescheduling and the schedule screens explain a refusal the same way.
"""

from __future__ import annotations

from datetime import datetime

from app.domain.booking_window import HORIZON_DAYS
from app.domain.errors import ConflictError, DomainError, ErrorCode, RuleViolation, domain_error
from app.domain.model import DepositStatus, SlotContext
from app.domain.penalties import LOOKBACK
from app.domain.slots import conflicting_appointment, overlapping_patient_appointment
from app.domain.timeutil import IST, format_minutes, ist_date, ist_iso

_DAYS = LOOKBACK.days


def ist_text(instant: datetime) -> str:
    """An instant as India wall-clock text for a sentence: 02 Nov 2026, 11:00."""
    return instant.astimezone(IST).strftime("%d %b %Y, %H:%M")


def violation_error(
    code: ErrorCode,
    start_at: datetime,
    ctx: SlotContext,
    patient_id: int | None = None,
    slots: int = 1,
) -> DomainError:
    """The error for the first violation of the slot starting at `start_at`.

    `patient_id` is the patient being booked; with it a SLOT_TAKEN error can say whether the slot is
    held by that same patient (a double click) or by someone else.
    """
    doctor = ctx.doctor
    when = ist_text(start_at)
    match code:
        case ErrorCode.DOCTOR_NOT_ACCEPTING:
            return domain_error(
                code,
                f"{doctor.name} is not taking new bookings at the moment. Existing appointments "
                "are unaffected.",
            )
        case ErrorCode.BOOKING_IN_PAST:
            return domain_error(code, f"{when} has already passed.")
        case ErrorCode.BOOKING_TOO_FAR:
            return domain_error(
                code,
                f"Appointments can be booked at most {HORIZON_DAYS} days ahead; {when} is later.",
                horizon_days=HORIZON_DAYS,
            )
        case ErrorCode.OFF_GRID:
            return domain_error(
                code,
                f"{doctor.name} sees patients in {doctor.slot_length_min}-minute slots, so "
                f"{when} is not a slot start.",
                slot_length_min=doctor.slot_length_min,
            )
        case ErrorCode.OUTSIDE_AVAILABILITY:
            hours = ", ".join(
                f"{format_minutes(w.start_min)}-{format_minutes(w.end_min)}" for w in ctx.windows
            )
            where = f"works {hours} that day" if hours else "is not working that day"
            visit = f" for a {slots * doctor.slot_length_min}-minute visit" if slots > 1 else ""
            return domain_error(
                code,
                f"{doctor.name} is not available at {when}{visit}; {doctor.name} {where}.",
                windows=[
                    {"start": format_minutes(w.start_min), "end": format_minutes(w.end_min)}
                    for w in ctx.windows
                ],
            )
        case ErrorCode.DAILY_CAP_REACHED:
            return domain_error(
                code,
                f"{doctor.name} already has the maximum of {doctor.daily_cap} appointments on "
                f"{ist_date(start_at):%d %b %Y}.",
                daily_cap=doctor.daily_cap,
            )
        case ErrorCode.SLOT_TAKEN:
            taken = conflicting_appointment(start_at, ctx, slots)
            details: dict[str, object] = {}
            if taken is not None:
                details = {
                    "appointment_id": taken.id,
                    "same_patient": patient_id is not None and taken.patient_id == patient_id,
                }
            same = details.get("same_patient") is True
            message = (
                "This patient already has an appointment in that slot."
                if same
                else "That slot has just been taken by another booking."
            )
            return ConflictError(code, message, **details)
        case ErrorCode.PATIENT_OVERLAP:
            other = overlapping_patient_appointment(start_at, ctx, slots)
            return ConflictError(
                code,
                f"The patient already has an appointment that overlaps {when}.",
                **({"appointment_id": other.id} if other is not None else {}),
            )
        case _:
            raise ValueError(f"{code} is not a slot violation")


def deposit_required_error(deposit: DepositStatus) -> RuleViolation:
    """DEPOSIT_REQUIRED, listing the strikes behind the flag and the date it ends."""
    until = deposit.required_until
    return RuleViolation(
        ErrorCode.DEPOSIT_REQUIRED,
        f"Patient has {len(deposit.reasons)} late cancellations or no-shows in the last "
        f"{_DAYS} days; confirm the deposit to book.",
        required_until=ist_iso(until) if until is not None else None,
        reasons=[
            {"appointment_id": e.appointment_id, "type": e.kind.value, "at": ist_iso(e.at)}
            for e in deposit.reasons
        ],
    )
