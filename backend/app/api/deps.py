"""Dependencies shared by the routers: the services and the effective clock."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import ApiError, InvalidTestClock
from app.api.parsing import parse_instant
from app.core.actor import current_actor
from app.core.auth import verify_claims
from app.domain.errors import ErrorCode
from app.domain.model import Role
from app.domain.timeutil import utc_iso
from app.services.alternatives_service import AlternativesService
from app.services.appointment_queries import AppointmentQueries
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.services.doctor_service import DoctorService
from app.services.meta_service import MetaService
from app.services.notification_service import NotificationService
from app.services.patient_service import PatientService
from app.services.policy_service import PolicyService
from app.services.record_service import RecordService
from app.services.staff_service import StaffService
from app.services.waitlist_service import WaitlistService

TEST_CLOCK_HEADER = "x-test-clock"


@dataclass(frozen=True, slots=True)
class Services:
    booking: BookingService
    availability: AvailabilityService
    doctors: DoctorService
    patients: PatientService
    queries: AppointmentQueries
    meta: MetaService
    waitlist: WaitlistService
    records: RecordService
    alternatives: AlternativesService
    staff: StaffService
    notifications: NotificationService
    policy: PolicyService

    @classmethod
    def build(cls, factory: sessionmaker[Session]) -> Services:
        availability = AvailabilityService(factory)
        doctors = DoctorService(factory)
        return cls(
            booking=BookingService(factory),
            availability=availability,
            doctors=doctors,
            patients=PatientService(factory),
            queries=AppointmentQueries(factory),
            meta=MetaService(factory),
            waitlist=WaitlistService(factory),
            records=RecordService(factory),
            alternatives=AlternativesService(availability, doctors),
            staff=StaffService(factory),
            notifications=NotificationService(factory),
            policy=PolicyService(factory),
        )


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def clock_header_value(request: Request) -> str | None:
    """The X-Test-Clock header if the request has one (even an empty one), else None."""
    values = request.headers.getlist(TEST_CLOCK_HEADER)
    if not values:
        return None
    if len(values) > 1:
        raise InvalidTestClock("Send the X-Test-Clock header only once.")
    return str(values[0])


def effective_now(request: Request, response: Response) -> datetime:
    """ "Now" for this request, read once and passed down.

    The real clock, unless the request carries X-Test-Clock and the server allows it. A header that
    cannot be honoured is an error rather than being ignored, so a reviewer is never left believing
    a simulated time was applied when it was not (plan F-07).
    """
    value = clock_header_value(request)
    if value is None:
        return datetime.now(UTC)
    if not request.app.state.settings.test_clock_enabled:
        raise InvalidTestClock("The test clock is disabled on this server.")
    try:
        instant = parse_instant(value)
    except ValueError as exc:
        raise InvalidTestClock(f"X-Test-Clock {exc}") from None
    request.state.effective_now = utc_iso(instant)
    response.headers["X-Effective-Now"] = utc_iso(instant)
    return instant


async def require_staff(request: Request) -> None:
    """Sets the actor for the audit trail and, when staff login is on, insists on a valid token.

    `async` on purpose: it must run in the request's own context for the actor to be visible to the
    route handler that runs after it in a worker thread. For an individual account the role and
    the active flag are read from the database, not trusted from the token, so a demotion or a
    deactivation applies to the very next request.
    """
    settings = request.app.state.settings
    secret = settings.signing_secret
    if secret is None:
        current_actor.set("anonymous")
        request.state.role = Role.ADMIN  # no sign-in at all: nothing to restrict
        return
    header = request.headers.get("authorization", "")
    claims = (
        verify_claims(secret, header[7:].strip(), time.time())
        if header.lower().startswith("bearer ")
        else None
    )
    role = Role(claims.role) if claims is not None else None
    name = claims.name if claims is not None else None
    if claims is not None and claims.account_id is not None:
        account = await run_in_threadpool(
            request.app.state.services.staff.current, claims.account_id
        )
        role = account.role if account is not None else None
        name = account.display_name if account is not None else None
    if role is None or name is None:
        raise ApiError(
            ErrorCode.UNAUTHENTICATED,
            "Sign in to use this service.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    current_actor.set(name)
    request.state.role = role
    log_fields = getattr(request.state, "log_fields", None)
    if log_fields is not None:
        log_fields["staff"] = name


async def require_admin(request: Request) -> None:
    """For set-up and sensitive routes: only an administrator (or an open server) may pass."""
    if getattr(request.state, "role", Role.ADMIN) is not Role.ADMIN:
        raise ApiError(
            ErrorCode.FORBIDDEN, "Only an administrator can do this.", details={"required": "ADMIN"}
        )


ServicesDep = Annotated[Services, Depends(get_services)]
AdminOnly = Depends(require_admin)
NowDep = Annotated[datetime, Depends(effective_now)]
