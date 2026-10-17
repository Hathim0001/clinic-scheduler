"""Fixtures for tests of the services against PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import Appointment
from app.services.appointment_queries import AppointmentQueries
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.services.doctor_service import DoctorService
from app.services.patient_service import PatientService
from app.services.record_service import RecordService
from app.services.waitlist_service import WaitlistService
from tests.factories import add_doctor, add_patient, add_weekly
from tests.helpers import ist

MONDAY = date(2026, 11, 2)
NOW = ist(2026, 11, 2, 8, 0)  # Monday 08:00 IST, before any working hours


def at(hour: int, minute: int = 0, *, day: int = 2) -> datetime:
    """A time in November 2026 (Monday 2 November by default), in India."""
    return ist(2026, 11, day, hour, minute)


@dataclass(frozen=True)
class Clinic:
    factory: sessionmaker[Session]
    booking: BookingService
    availability: AvailabilityService
    doctors: DoctorService
    patients: PatientService
    queries: AppointmentQueries
    waitlist: WaitlistService
    records: RecordService
    rao: int  # 30-minute slots, cap 6, Monday to Friday 09:00-13:00
    menon: int  # 15-minute slots, cap 20, Monday to Friday 09:00-13:00
    asha: int
    ravi: int
    meena: int

    def appointment(self, appointment_id: int) -> Appointment:
        with self.factory() as session:
            return session.scalars(
                select(Appointment).where(Appointment.id == appointment_id)
            ).one()

    def appointments(self) -> list[Appointment]:
        with self.factory() as session:
            return list(session.scalars(select(Appointment).order_by(Appointment.id)))


@pytest.fixture
def clinic(session_factory: sessionmaker[Session]) -> Clinic:
    with session_factory() as session, session.begin():
        rao = add_doctor(session, name="Dr. Rao", slot=30, cap=6)
        menon = add_doctor(session, name="Dr. Menon", slot=15, cap=20)
        for doctor in (rao, menon):
            for weekday in range(5):
                add_weekly(session, doctor.id, weekday, 540, 780)
        asha = add_patient(session, 1, name="Asha Iyer")
        ravi = add_patient(session, 2, name="Ravi Kumar")
        meena = add_patient(session, 3, name="Meena Das")
        ids = (rao.id, menon.id, asha.id, ravi.id, meena.id)
    return Clinic(
        session_factory,
        BookingService(session_factory),
        AvailabilityService(session_factory),
        DoctorService(session_factory),
        PatientService(session_factory),
        AppointmentQueries(session_factory),
        WaitlistService(session_factory),
        RecordService(session_factory),
        *ids,
    )
