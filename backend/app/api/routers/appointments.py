"""Appointments: book, read, list, cancel, reschedule and mark. Each route calls one service method;
the rules live in `domain/` and are enforced by `services/`."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Header, Query, Request, Response

from app.api.deps import NowDep, ServicesDep
from app.api.ics import calendar_text
from app.api.params import (
    AppointmentId,
    BoolQuery,
    Limit,
    Offset,
    OptionalDayQuery,
    OptionalId,
)
from app.api.presenters import appointment_out, deposit_out, event_out
from app.api.schemas.requests import (
    BookRequest,
    CancelRequest,
    CorrectRequest,
    RecurringBookRequest,
    RescheduleRequest,
)
from app.api.schemas.responses import (
    AppointmentOut,
    CancelOut,
    EventOut,
    PageOut,
    RescheduleOut,
    SeriesOut,
)
from app.domain.model import CancelledBy, Status
from app.services.views import BookCommand

router = APIRouter(prefix="/appointments", tags=["appointments"])
log = structlog.get_logger()


@router.get("", response_model=PageOut[AppointmentOut], summary="List appointments")
def list_appointments(
    services: ServicesDep,
    now: NowDep,
    doctor_id: OptionalId = None,
    day: OptionalDayQuery = None,
    status: Status | None = None,
    needs_attention: Annotated[BoolQuery | None, Query()] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PageOut[AppointmentOut]:
    """`needs_attention=true` lists booked future appointments that no longer fit the doctor's
    hours, so the list survives a page reload."""
    page = services.queries.search(
        doctor_id=doctor_id,
        day=day,
        status=status,
        needs_attention=needs_attention,
        limit=limit,
        offset=offset,
        now=now,
    )
    return PageOut[AppointmentOut](
        items=[appointment_out(a) for a in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "",
    response_model=AppointmentOut,
    status_code=201,
    summary="Book an appointment",
    responses={
        404: {"description": "DOCTOR_NOT_FOUND or PATIENT_NOT_FOUND"},
        409: {"description": "SLOT_TAKEN, PATIENT_OVERLAP or DAILY_CAP_REACHED"},
        422: {"description": "The slot or the request breaks a rule (see the error code)"},
    },
)
def book(
    request: Request,
    response: Response,
    body: BookRequest,
    services: ServicesDep,
    now: NowDep,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=1,
            max_length=100,
            description=(
                "Optional. Send the same key when retrying a booking whose answer was lost: the "
                "retry returns the original appointment (200, Idempotent-Replay: true) instead of "
                "booking twice. Reusing a key for a different request is a 409."
            ),
        ),
    ] = None,
) -> AppointmentOut:
    """The server computes the end time from the doctor's slot length; `end_at` is not accepted."""
    request.state.log_fields.update(doctor_id=body.doctor_id, patient_id=body.patient_id)
    command = BookCommand(
        doctor_id=body.doctor_id,
        patient_id=body.patient_id,
        start_at=body.start_at,
        reason=body.reason,
        deposit_confirmed=body.deposit_confirmed,
        slots=body.slots,
    )
    if idempotency_key is not None:
        view, replayed = services.booking.book_idempotent(command, idempotency_key, now)
        if replayed:
            response.status_code = 200
            response.headers["Idempotent-Replay"] = "true"
            log.info("appointment.replayed", appointment_id=view.id)
            return appointment_out(view)
    else:
        view = services.booking.book(command, now)
    log.info(
        "appointment.booked",
        appointment_id=view.id,
        doctor_id=view.doctor_id,
        patient_id=view.patient_id,
        deposit_required=view.deposit_required_at_booking,
    )
    return appointment_out(view)


@router.post(
    "/recurring",
    response_model=SeriesOut,
    status_code=201,
    summary="Book a series (every N days, 2 to 12 appointments), all or none",
    responses={
        409: {"description": "A slot in the series is taken; details.occurrence says which"}
    },
)
def book_series(
    request: Request, body: RecurringBookRequest, services: ServicesDep, now: NowDep
) -> SeriesOut:
    request.state.log_fields.update(doctor_id=body.doctor_id, patient_id=body.patient_id)
    views = services.booking.book_series(
        BookCommand(
            body.doctor_id,
            body.patient_id,
            body.start_at,
            body.reason,
            body.deposit_confirmed,
            body.slots,
        ),
        body.every_days,
        body.count,
        now,
    )
    log.info(
        "appointment.series_booked",
        doctor_id=body.doctor_id,
        patient_id=body.patient_id,
        count=len(views),
        first_appointment_id=views[0].id,
    )
    return SeriesOut(appointments=[appointment_out(v) for v in views])


@router.get("/{appointment_id}", response_model=AppointmentOut, summary="Get an appointment")
def get_appointment(
    appointment_id: AppointmentId, services: ServicesDep, now: NowDep
) -> AppointmentOut:
    return appointment_out(services.queries.get(appointment_id, now))


@router.get(
    "/{appointment_id}/calendar.ics",
    summary="Download one appointment as a calendar event (iCalendar)",
    response_class=Response,
)
def appointment_calendar(
    appointment_id: AppointmentId, services: ServicesDep, now: NowDep
) -> Response:
    view = services.queries.get(appointment_id, now)
    return Response(
        calendar_text([view], now),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="appointment-{view.id}.ics"'},
    )


@router.post(
    "/{appointment_id}/cancel",
    response_model=CancelOut,
    summary="Cancel (a patient cancelling under 2 hours ahead is a late cancellation)",
)
def cancel(
    request: Request,
    appointment_id: AppointmentId,
    services: ServicesDep,
    now: NowDep,
    body: CancelRequest | None = None,
) -> CancelOut:
    request.state.log_fields.update(appointment_id=appointment_id)
    cancelled_by = CancelledBy(body.cancelled_by if body is not None else "PATIENT")
    result = services.booking.cancel(appointment_id, cancelled_by, now)
    log.info(
        "appointment.cancelled",
        appointment_id=appointment_id,
        cancelled_by=cancelled_by.value,
        late=result.late,
    )
    return CancelOut(
        appointment=appointment_out(result.appointment),
        late=result.late,
        deposit=deposit_out(result.deposit),
    )


@router.post(
    "/{appointment_id}/reschedule",
    response_model=RescheduleOut,
    summary="Move an appointment: the old one is cancelled and a new one booked, atomically",
)
def reschedule(
    request: Request,
    appointment_id: AppointmentId,
    body: RescheduleRequest,
    services: ServicesDep,
    now: NowDep,
) -> RescheduleOut:
    request.state.log_fields.update(appointment_id=appointment_id, doctor_id=body.doctor_id)
    result = services.booking.reschedule(
        appointment_id,
        body.start_at,
        body.doctor_id,
        body.deposit_confirmed,
        now,
        CancelledBy(body.by),
        body.acknowledge_late,
    )
    log.info(
        "appointment.rescheduled",
        appointment_id=appointment_id,
        new_appointment_id=result.new.id,
        old_status=result.old.status.value,
    )
    return RescheduleOut(old=appointment_out(result.old), new=appointment_out(result.new))


@router.post("/{appointment_id}/complete", response_model=AppointmentOut, summary="Mark completed")
def complete(
    request: Request, appointment_id: AppointmentId, services: ServicesDep, now: NowDep
) -> AppointmentOut:
    request.state.log_fields.update(appointment_id=appointment_id)
    view = services.booking.complete(appointment_id, now)
    log.info("appointment.completed", appointment_id=appointment_id)
    return appointment_out(view)


@router.post("/{appointment_id}/no-show", response_model=AppointmentOut, summary="Mark no-show")
def no_show(
    request: Request, appointment_id: AppointmentId, services: ServicesDep, now: NowDep
) -> AppointmentOut:
    request.state.log_fields.update(appointment_id=appointment_id)
    view = services.booking.no_show(appointment_id, now)
    log.info("appointment.no_show", appointment_id=appointment_id)
    return appointment_out(view)


@router.post(
    "/{appointment_id}/confirmed-by-phone",
    response_model=AppointmentOut,
    summary="Record that reception rang the patient and they confirmed (repeating it is harmless)",
    responses={409: {"description": "INVALID_TRANSITION: only a booked appointment"}},
)
def confirmed_by_phone(
    request: Request, appointment_id: AppointmentId, services: ServicesDep, now: NowDep
) -> AppointmentOut:
    request.state.log_fields.update(appointment_id=appointment_id)
    view = services.booking.confirm_by_phone(appointment_id, now)
    log.info("appointment.confirmed_by_phone", appointment_id=appointment_id)
    return appointment_out(view)


@router.post(
    "/{appointment_id}/check-in",
    response_model=AppointmentOut,
    summary="Record the patient arriving (on the day of the visit; repeating it is harmless)",
)
def check_in(
    request: Request, appointment_id: AppointmentId, services: ServicesDep, now: NowDep
) -> AppointmentOut:
    request.state.log_fields.update(appointment_id=appointment_id)
    view = services.booking.check_in(appointment_id, now)
    log.info("appointment.checked_in", appointment_id=appointment_id)
    return appointment_out(view)


@router.post(
    "/{appointment_id}/correct",
    response_model=AppointmentOut,
    summary="Correct a wrongly recorded outcome (completed and no-show swap; late cancel waived)",
    responses={409: {"description": "INVALID_CORRECTION"}},
)
def correct(
    request: Request,
    appointment_id: AppointmentId,
    body: CorrectRequest,
    services: ServicesDep,
    now: NowDep,
) -> AppointmentOut:
    """The original outcome and the note stay in `GET /appointments/{id}/history`."""
    request.state.log_fields.update(appointment_id=appointment_id)
    view = services.booking.correct(appointment_id, Status(body.status), body.note, now)
    log.info("appointment.corrected", appointment_id=appointment_id, status=body.status)
    return appointment_out(view)


@router.get(
    "/{appointment_id}/history",
    response_model=list[EventOut],
    summary="Everything that happened to an appointment, oldest first",
)
def history(appointment_id: AppointmentId, services: ServicesDep) -> list[EventOut]:
    return [event_out(e) for e in services.records.history(appointment_id)]
