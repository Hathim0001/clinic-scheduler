"""SQLAlchemy models. They mirror the tables created by migrations/versions/0001_initial.sql and are
used for queries. The migration, not these classes, defines the schema, including every constraint
that backs a booking rule (see plan section 23).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AppMeta(Base):
    """Facts written by the seed script, such as the anchor date used for the clock presets."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    speciality: Mapped[str] = mapped_column(Text)
    slot_length_min: Mapped[int] = mapped_column(SmallInteger)
    daily_cap: Mapped[int] = mapped_column(SmallInteger)
    accepting_bookings: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class WeeklyWindowRow(Base):
    """One recurring window; weekday 0 is Monday, times are minutes since IST midnight."""

    __tablename__ = "weekly_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_min: Mapped[int] = mapped_column(SmallInteger)
    end_min: Mapped[int] = mapped_column(SmallInteger)


class OverrideRow(Base):
    """A date-specific replacement of the weekly pattern. No windows at all means leave."""

    __tablename__ = "availability_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    on_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    windows: Mapped[list[OverrideWindowRow]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OverrideWindowRow.start_min",
    )


class OverrideWindowRow(Base):
    __tablename__ = "override_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    override_id: Mapped[int] = mapped_column(
        ForeignKey("availability_overrides.id", ondelete="CASCADE")
    )
    start_min: Mapped[int] = mapped_column(SmallInteger)
    end_min: Mapped[int] = mapped_column(SmallInteger)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = _created_at()
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    consent_version: Mapped[str | None] = mapped_column(Text, default=None)
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class StaffAccount(Base):
    """An individual login, used only when the server runs with AUTH_SECRET."""

    __tablename__ = "staff_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created_at()


class Notification(Base):
    """A message to a patient, written in the same transaction as the change it announces."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    kind: Mapped[str] = mapped_column(Text)
    to_phone: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="PENDING")
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_via: Mapped[str | None] = mapped_column(Text)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    deposit_required_at_booking: Mapped[bool] = mapped_column(Boolean, default=False)
    deposit_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rescheduled_to_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    slots: Mapped[int] = mapped_column(SmallInteger, default=1)
    outside_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class WaitlistEntry(Base):
    """A patient waiting for any slot with a doctor on one India date.

    WAITING until a cancellation frees a slot they could take, then OFFERED that slot until
    `offer_expires_at`; BOOKED when they accept, EXPIRED when the offer lapses and they are not
    waiting any more, CANCELLED when removed.
    """

    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    on_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, default="WAITING")
    offered_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    declined_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offered_slots: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class AppointmentEvent(Base):
    """An append-only record of what happened to an appointment, written in the same transaction as
    the change itself, so the history cannot disagree with the data (and an event cannot exist for a
    change that was rolled back)."""

    __tablename__ = "appointment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    kind: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actor: Mapped[str] = mapped_column(Text, default="system")


class IdempotencyKey(Base):
    """A booking request already carried out, so a retry returns the same appointment."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"))
    created_at: Mapped[datetime] = _created_at()
