"""Turning appointment rows into the views the API serialises.

The two derived fields are worked out here, at request time, from the rules and the clock:
`allowed_actions` (which buttons make sense) and `needs_attention` (a booking that no longer fits
the doctor's hours). Neither is stored, so neither can go stale.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.availability import needs_attention
from app.domain.model import CancelledBy, Status
from app.domain.timeutil import ist_date
from app.domain.transitions import allowed_actions
from app.persistence import repositories as repo
from app.services.views import AppointmentView


def build_views(
    session: Session, rows: Sequence[repo.AppointmentRow], now: datetime
) -> list[AppointmentView]:
    lookup = repo.WindowsLookup(session)
    lookup.preload(
        (row.appointment.doctor_id, ist_date(row.appointment.start_at))
        for row in rows
        if row.appointment.status == Status.BOOKED.value
    )
    views = []
    for row in rows:
        appt = row.appointment
        status = Status(appt.status)
        windows = (
            lookup.windows(appt.doctor_id, ist_date(appt.start_at))
            if status is Status.BOOKED
            else ()
        )
        views.append(
            AppointmentView(
                id=appt.id,
                doctor_id=appt.doctor_id,
                doctor_name=row.doctor_name,
                patient_id=appt.patient_id,
                patient_name=row.patient_name,
                patient_phone=row.patient_phone,
                status=status,
                start_at=appt.start_at,
                end_at=appt.end_at,
                reason=appt.reason,
                deposit_required_at_booking=appt.deposit_required_at_booking,
                deposit_confirmed=appt.deposit_confirmed,
                cancelled_at=appt.cancelled_at,
                cancelled_by=CancelledBy(appt.cancelled_by) if appt.cancelled_by else None,
                status_changed_at=appt.status_changed_at,
                rescheduled_to_id=appt.rescheduled_to_id,
                needs_attention=needs_attention(repo.appointment_facts(appt), now, windows),
                allowed_actions=tuple(allowed_actions(status, appt.start_at, now)),
            )
        )
    return views


def view_of(session: Session, appointment_id: int, now: datetime) -> AppointmentView:
    return build_views(session, repo.appointment_rows_by_id(session, [appointment_id]), now)[0]
