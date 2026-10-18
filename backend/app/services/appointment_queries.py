"""Reading appointments: one by id, filtered lists, a patient's history and a day's queue.

`needs_attention` is derived (a BOOKED future appointment outside the doctor's current hours), so a
list filtered by it loads the rows that match the other filters and checks each one; it cannot be
a SQL condition. That is fine at clinic scale and is noted in the README.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.domain.model import CANCELLED_STATUSES, Status
from app.persistence import repositories as repo
from app.services.appointment_views import build_views, view_of
from app.services.support import run
from app.services.views import AppointmentView, Page


class AppointmentQueries:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get(self, appointment_id: int, now: datetime) -> AppointmentView:
        def work(session: Session) -> AppointmentView:
            repo.get_appointment(session, appointment_id)  # 404 before building the view
            return view_of(session, appointment_id, now)

        return run(self._factory, work)

    def search(
        self,
        *,
        doctor_id: int | None,
        day: date | None,
        status: Status | None,
        needs_attention: bool | None,
        limit: int,
        offset: int,
        now: datetime,
    ) -> Page[AppointmentView]:
        flt = repo.AppointmentFilter(
            doctor_id=doctor_id,
            day=day,
            statuses=frozenset({status}) if status is not None else None,
        )

        def work(session: Session) -> Page[AppointmentView]:
            if doctor_id is not None:
                repo.get_doctor(session, doctor_id)
            if needs_attention is True:
                # the stored flag and its partial index: no scan of every booking
                stored = repo.AppointmentFilter(
                    doctor_id=doctor_id,
                    day=day,
                    statuses=frozenset({Status.BOOKED})
                    if status in (None, Status.BOOKED)
                    else frozenset(),
                    start_from=now,
                    outside_hours=True,
                )
                rows = repo.find_appointments(session, stored, limit=limit, offset=offset)
                total = repo.count_appointments(session, stored)
                return Page(build_views(session, rows, now), total, limit, offset)
            if needs_attention is None:
                rows = repo.find_appointments(session, flt, limit=limit, offset=offset)
                total = repo.count_appointments(session, flt)
                return Page(build_views(session, rows, now), total, limit, offset)
            views = [
                v
                for v in build_views(session, repo.find_appointments(session, flt), now)
                if v.needs_attention is needs_attention
            ]
            return Page(views[offset : offset + limit], len(views), limit, offset)

        return run(self._factory, work)

    def for_patient(
        self, patient_id: int, status: Status | None, limit: int, offset: int, now: datetime
    ) -> Page[AppointmentView]:
        """A patient's appointments, newest first."""
        flt = repo.AppointmentFilter(
            patient_id=patient_id,
            statuses=frozenset({status}) if status is not None else None,
            newest_first=True,
        )

        def work(session: Session) -> Page[AppointmentView]:
            repo.get_patient(session, patient_id)
            rows = repo.find_appointments(session, flt, limit=limit, offset=offset)
            return Page(
                build_views(session, rows, now),
                repo.count_appointments(session, flt),
                limit,
                offset,
            )

        return run(self._factory, work)

    def queue(
        self, day: date, doctor_id: int | None, include_cancelled: bool, now: datetime
    ) -> list[AppointmentView]:
        """Everything booked for one India date, in time order. Cancelled ones only on request."""
        statuses = None if include_cancelled else frozenset(set(Status) - CANCELLED_STATUSES)
        flt = repo.AppointmentFilter(doctor_id=doctor_id, day=day, statuses=statuses)

        def work(session: Session) -> list[AppointmentView]:
            if doctor_id is not None:
                repo.get_doctor(session, doctor_id)
            return build_views(session, repo.find_appointments(session, flt), now)

        return run(self._factory, work)
