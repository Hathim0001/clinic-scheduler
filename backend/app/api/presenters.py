"""Turning service views into response bodies: every instant gets a UTC and an India rendering."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta

from app.api.schemas.responses import (
    AlternativeOut,
    AppointmentOut,
    DepositOut,
    DoctorOut,
    DoctorReportOut,
    EventOut,
    OverrideOut,
    PatientExportOut,
    PatientOut,
    ReportOut,
    ScheduleOut,
    ScheduleSlotOut,
    SlotOut,
    SlotsOut,
    StrikeOut,
    WaitlistOut,
    WeeklyOut,
    WeeklyWindowOut,
    WindowOut,
)
from app.domain.model import DepositStatus, WeeklyWindow, Window
from app.domain.timeutil import format_minutes, ist_iso, utc_iso
from app.services.alternatives_service import Alternative
from app.services.record_service import PatientExport, ReportView
from app.services.views import (
    AppointmentView,
    DoctorView,
    EventView,
    OverrideChange,
    OverrideView,
    PatientView,
    ScheduleView,
    SlotsView,
    WaitlistView,
    WeeklyView,
)


def _utc(instant: datetime | None) -> str | None:
    return utc_iso(instant) if instant is not None else None


def _ist(instant: datetime | None) -> str | None:
    return ist_iso(instant) if instant is not None else None


def window_out(window: Window) -> WindowOut:
    return WindowOut(start=format_minutes(window.start_min), end=format_minutes(window.end_min))


def weekly_window_out(window: WeeklyWindow) -> WeeklyWindowOut:
    return WeeklyWindowOut(
        weekday=window.weekday,
        start=format_minutes(window.start_min),
        end=format_minutes(window.end_min),
    )


def doctor_out(view: DoctorView) -> DoctorOut:
    return DoctorOut(
        id=view.id,
        name=view.name,
        speciality=view.speciality,
        slot_length_min=view.slot_length_min,
        daily_cap=view.daily_cap,
        accepting_bookings=view.accepting_bookings,
    )


def deposit_out(deposit: DepositStatus) -> DepositOut:
    return DepositOut(
        required=deposit.required,
        required_until_utc=_utc(deposit.required_until),
        required_until_ist=_ist(deposit.required_until),
        reasons=[
            StrikeOut(
                appointment_id=event.appointment_id,
                type=event.kind.value,  # type: ignore[arg-type]
                at_utc=utc_iso(event.at),
                at_ist=ist_iso(event.at),
            )
            for event in deposit.reasons
        ],
    )


def patient_out(view: PatientView) -> PatientOut:
    return PatientOut(
        id=view.id,
        name=view.name,
        phone=view.phone,
        date_of_birth=view.date_of_birth.isoformat(),
        created_at_utc=utc_iso(view.created_at),
        deposit_required=view.deposit.required if view.deposit is not None else None,
        deposit=deposit_out(view.deposit) if view.deposit is not None else None,
        consent_at_utc=utc_iso(view.consent_at) if view.consent_at is not None else None,
        erased=view.erased_at is not None,
    )


def appointment_out(view: AppointmentView) -> AppointmentOut:
    return AppointmentOut(
        id=view.id,
        doctor_id=view.doctor_id,
        doctor_name=view.doctor_name,
        patient_id=view.patient_id,
        patient_name=view.patient_name,
        patient_phone=view.patient_phone,
        status=view.status.value,
        start_at_utc=utc_iso(view.start_at),
        start_at_ist=ist_iso(view.start_at),
        end_at_utc=utc_iso(view.end_at),
        end_at_ist=ist_iso(view.end_at),
        reason=view.reason,
        deposit_required_at_booking=view.deposit_required_at_booking,
        deposit_confirmed=view.deposit_confirmed,
        cancelled_at_utc=_utc(view.cancelled_at),
        cancelled_at_ist=_ist(view.cancelled_at),
        cancelled_by=view.cancelled_by.value if view.cancelled_by is not None else None,
        status_changed_at_utc=_utc(view.status_changed_at),
        status_changed_at_ist=_ist(view.status_changed_at),
        rescheduled_to_id=view.rescheduled_to_id,
        needs_attention=view.needs_attention,
        allowed_actions=list(view.allowed_actions),
        checked_in_at_utc=_utc(view.checked_in_at),
        checked_in_at_ist=_ist(view.checked_in_at),
        urgent_symptoms=view.urgent_symptoms,
        slots=view.slots,
        duration_min=int((view.end_at - view.start_at).total_seconds() // 60),
    )


def _slot_times(start: datetime, minutes: int) -> dict[str, str]:
    end = start + timedelta(minutes=minutes)
    return {
        "start_at_utc": utc_iso(start),
        "start_at_ist": ist_iso(start),
        "end_at_utc": utc_iso(end),
        "end_at_ist": ist_iso(end),
    }


def alternative_out(option: Alternative) -> AlternativeOut:
    return AlternativeOut(
        **_slot_times(option.start_at, option.duration_min),
        doctor_id=option.doctor_id,
        doctor_name=option.doctor_name,
        speciality=option.speciality,
        same_doctor=option.same_doctor,
    )


def slots_out(view: SlotsView) -> SlotsOut:
    return SlotsOut(
        doctor_id=view.doctor_id,
        date=view.day.isoformat(),
        slot_length_min=view.slot_length_min,
        source=view.source,  # type: ignore[arg-type]
        windows=[window_out(w) for w in view.windows],
        slots=[SlotOut(**_slot_times(s, view.duration_min)) for s in view.slots],
        unavailable_reason=view.unavailable_reason.value if view.unavailable_reason else None,
        duration_min=view.duration_min,
    )


def schedule_out(view: ScheduleView) -> ScheduleOut:
    return ScheduleOut(
        doctor_id=view.doctor_id,
        date=view.day.isoformat(),
        slot_length_min=view.slot_length_min,
        source=view.source,  # type: ignore[arg-type]
        windows=[window_out(w) for w in view.windows],
        slots=[
            ScheduleSlotOut(
                **_slot_times(slot.start_at, view.slot_length_min),
                state=slot.state.value,
                appointment=appointment_out(slot.appointment) if slot.appointment else None,
            )
            for slot in view.slots
        ],
        outside_availability=[appointment_out(a) for a in view.outside_availability],
        unavailable_reason=view.unavailable_reason.value if view.unavailable_reason else None,
    )


def waitlist_out(view: WaitlistView) -> WaitlistOut:
    return WaitlistOut(
        id=view.id,
        doctor_id=view.doctor_id,
        doctor_name=view.doctor_name,
        patient_id=view.patient_id,
        patient_name=view.patient_name,
        patient_phone=view.patient_phone,
        date=view.day.isoformat(),
        status=view.status,  # type: ignore[arg-type]
        position=view.position,
        offered_start_at_utc=_utc(view.offered_start_at),
        offered_start_at_ist=_ist(view.offered_start_at),
        offer_expires_at_utc=_utc(view.offer_expires_at),
        offer_expires_at_ist=_ist(view.offer_expires_at),
        appointment_id=view.appointment_id,
    )


def weekly_out(view: WeeklyView) -> WeeklyOut:
    return WeeklyOut(
        windows=[weekly_window_out(w) for w in view.windows],
        needs_attention=[appointment_out(a) for a in view.needs_attention],
    )


def override_out(view: OverrideView | OverrideChange) -> OverrideOut:
    needs_attention = view.needs_attention if isinstance(view, OverrideChange) else ()
    return OverrideOut(
        date=view.on_date.isoformat(),
        note=view.note,
        windows=[window_out(w) for w in view.windows],
        needs_attention=[appointment_out(a) for a in needs_attention],
    )


def event_out(view: EventView) -> EventOut:
    return EventOut(
        id=view.id,
        appointment_id=view.appointment_id,
        patient_id=view.patient_id,
        kind=view.kind,
        at_utc=utc_iso(view.at),
        at_ist=ist_iso(view.at),
        detail=view.detail,
        actor=view.actor,
    )


def export_out(export: PatientExport) -> PatientExportOut:
    return PatientExportOut(
        patient=patient_out(export.patient),
        appointments=[appointment_out(a) for a in export.appointments],
        events=[event_out(e) for e in export.events],
    )


def report_out(report: ReportView) -> ReportOut:
    return ReportOut(
        start=report.start.isoformat(),
        end=report.end.isoformat(),
        doctors=[DoctorReportOut(**asdict(d)) for d in report.doctors],
        total=DoctorReportOut(**asdict(report.total)),
    )
