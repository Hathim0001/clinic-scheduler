"""The waitlist: join for a doctor and date, see the queue, leave, and accept an offered slot."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from app.api.deps import NowDep, ServicesDep
from app.api.params import DayQuery, DoctorId, EntityPath, PatientId
from app.api.presenters import appointment_out, waitlist_out
from app.api.schemas.requests import WaitlistAcceptRequest, WaitlistJoinRequest
from app.api.schemas.responses import WaitlistAcceptOut, WaitlistOut

router = APIRouter(tags=["waitlist"])
log = structlog.get_logger()


@router.post(
    "/doctors/{doctor_id}/waitlist",
    response_model=WaitlistOut,
    status_code=201,
    summary="Put a patient on the waitlist for a doctor and an India date",
    responses={409: {"description": "ALREADY_WAITING"}},
)
def join_waitlist(
    doctor_id: DoctorId, body: WaitlistJoinRequest, services: ServicesDep, now: NowDep
) -> WaitlistOut:
    """When a cancellation frees a slot that day, the first patient who could take it is offered
    it for 30 minutes (see `GET /patients/{id}/waitlist`) and accepts with
    `POST /waitlist/{id}/accept`.
    """
    return waitlist_out(services.waitlist.join(doctor_id, body.patient_id, body.date, now))


@router.get(
    "/doctors/{doctor_id}/waitlist",
    response_model=list[WaitlistOut],
    summary="Who is waiting, or holding an offer, for a doctor on a date",
)
def doctor_waitlist(
    doctor_id: DoctorId, day: DayQuery, services: ServicesDep, now: NowDep
) -> list[WaitlistOut]:
    return [waitlist_out(v) for v in services.waitlist.for_doctor_day(doctor_id, day, now)]


@router.get(
    "/patients/{patient_id}/waitlist",
    response_model=list[WaitlistOut],
    summary="A patient's waitlist entries that are still alive, with any open offer",
)
def patient_waitlist(
    patient_id: PatientId, services: ServicesDep, now: NowDep
) -> list[WaitlistOut]:
    return [waitlist_out(v) for v in services.waitlist.for_patient(patient_id, now)]


@router.delete(
    "/waitlist/{entry_id}",
    response_model=WaitlistOut,
    summary="Leave the waitlist",
)
def leave_waitlist(entry_id: EntityPath, services: ServicesDep, now: NowDep) -> WaitlistOut:
    return waitlist_out(services.waitlist.leave(entry_id, now))


@router.post(
    "/waitlist/{entry_id}/accept",
    response_model=WaitlistAcceptOut,
    summary="Accept the offered slot: it is booked like any other appointment",
    responses={409: {"description": "OFFER_EXPIRED, SLOT_TAKEN or INVALID_TRANSITION"}},
)
def accept_offer(
    entry_id: EntityPath, body: WaitlistAcceptRequest, services: ServicesDep, now: NowDep
) -> WaitlistAcceptOut:
    result = services.waitlist.accept(entry_id, body.reason, body.deposit_confirmed, now)
    return WaitlistAcceptOut(
        entry=waitlist_out(result.entry), appointment=appointment_out(result.appointment)
    )


@router.post(
    "/waitlist/{entry_id}/decline",
    response_model=WaitlistOut,
    summary="Say no to an offer but keep the place in the queue; the slot goes to the next patient",
)
def decline_offer(entry_id: EntityPath, services: ServicesDep, now: NowDep) -> WaitlistOut:
    return waitlist_out(services.waitlist.decline(entry_id, now))
