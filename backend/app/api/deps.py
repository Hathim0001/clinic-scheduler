"""Dependencies shared by the routers: the services and the effective clock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import InvalidTestClock
from app.api.parsing import parse_instant
from app.domain.timeutil import utc_iso
from app.services.appointment_queries import AppointmentQueries
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.services.doctor_service import DoctorService
from app.services.meta_service import MetaService
from app.services.patient_service import PatientService
from app.services.record_service import RecordService
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

    @classmethod
    def build(cls, factory: sessionmaker[Session]) -> Services:
        return cls(
            booking=BookingService(factory),
            availability=AvailabilityService(factory),
            doctors=DoctorService(factory),
            patients=PatientService(factory),
            queries=AppointmentQueries(factory),
            meta=MetaService(factory),
            waitlist=WaitlistService(factory),
            records=RecordService(factory),
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


ServicesDep = Annotated[Services, Depends(get_services)]
NowDep = Annotated[datetime, Depends(effective_now)]
