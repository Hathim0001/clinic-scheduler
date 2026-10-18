"""Patients: registration, lookup by phone or name, and the deposit flag shown with each patient."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ConflictError, ErrorCode, RuleViolation
from app.domain.model import DepositStatus
from app.domain.penalties import deposit_status
from app.domain.phone import normalise_phone
from app.domain.timeutil import ist_date
from app.persistence import repositories as repo
from app.persistence.models import Appointment, Patient, WaitlistEntry
from app.services.notification_service import scrub_patient
from app.services.support import run
from app.services.views import Page, PatientView

EARLIEST_BIRTH_DATE = date(1900, 1, 1)
CONSENT_VERSION = "privacy-notice-2026-10"  # bump when the notice shown to patients changes
ERASED_NAME = "Erased patient"
ERASED_REASON = "[erased]"
_UPCOMING = ("BOOKED",)
_LIVE_WAITLIST = ("WAITING", "OFFERED")


def erased_phone(patient_id: int) -> str:
    """A valid but reserved-looking number that keeps `phone` unique and identifies no one."""
    return f"+91{6_000_000_000 + patient_id}"


def refuse_erased(patient: Patient) -> None:
    """Raise PATIENT_ERASED: an erased patient cannot be booked, edited or put on a waitlist."""
    if patient.erased_at is not None:
        raise ConflictError(
            ErrorCode.PATIENT_ERASED,
            "This patient's data has been erased, so they cannot be booked or edited. "
            "Register them again if they return.",
            patient_id=patient.id,
        )


def _view(patient: Patient, deposit: DepositStatus | None = None) -> PatientView:
    return PatientView(
        patient.id,
        patient.name,
        patient.phone,
        patient.date_of_birth,
        patient.created_at,
        deposit,
        patient.consent_at,
        patient.erased_at,
    )


def _normalised(phone: str) -> str:
    try:
        return normalise_phone(phone)
    except ValueError as exc:
        raise RuleViolation(ErrorCode.VALIDATION_ERROR, str(exc), field="phone") from exc


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= 100:
        raise RuleViolation(
            ErrorCode.VALIDATION_ERROR, "The name must be 1 to 100 characters.", field="name"
        )
    return cleaned


def _check_birth_date(born: date, now: datetime) -> None:
    if not EARLIEST_BIRTH_DATE <= born <= ist_date(now):
        raise RuleViolation(
            ErrorCode.VALIDATION_ERROR,
            "The date of birth must be between 1 January 1900 and today.",
            field="date_of_birth",
        )


def _refuse_taken_phone(owner: Patient | None) -> None:
    """Raise PHONE_TAKEN if someone is registered on the number.

    Only the id is returned, not the name or birth date: telling a receptionist who has a number is
    useful, telling it to anyone who can send a request is a privacy leak.
    """
    if owner is not None:
        raise ConflictError(
            ErrorCode.PHONE_TAKEN,
            "A patient with that phone number already exists. Search by phone to find them.",
            patient_id=owner.id,
        )


def _refuse_duplicates(matches: list[Patient]) -> None:
    """Raise POSSIBLE_DUPLICATE if another patient has the same name and date of birth.

    Two profiles for one person split a history in two and hide a deposit flag; two people who
    really share a name and birth date (twins) can still be registered by confirming.
    """
    if matches:
        raise ConflictError(
            ErrorCode.POSSIBLE_DUPLICATE,
            "A patient with the same name and date of birth is already registered. If this is "
            "the same person, use that record; if not, confirm and register anyway.",
            candidates=[{"patient_id": p.id, "name": p.name, "phone": p.phone} for p in matches],
        )


class PatientService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(
        self,
        name: str,
        phone: str,
        date_of_birth: date,
        now: datetime,
        allow_duplicate: bool = False,
        consent: bool = False,
    ) -> PatientView:
        """Register a patient. A phone number identifies one patient (the problem statement: phone,
        unique), so a number already in use is refused with PHONE_TAKEN. `consent` records that the
        patient accepted the privacy notice at `now`; registration works without it."""
        cleaned = _clean_name(name)
        normalised = _normalised(phone)
        _check_birth_date(date_of_birth, now)

        def work(session: Session) -> PatientView:
            _refuse_taken_phone(repo.patient_by_phone(session, normalised))
            if not allow_duplicate:
                _refuse_duplicates(repo.patients_like(session, cleaned, date_of_birth))
            patient = Patient(name=cleaned, phone=normalised, date_of_birth=date_of_birth)
            if consent:
                patient.consent_at, patient.consent_version = now, CONSENT_VERSION
            session.add(patient)
            session.flush()
            return _view(patient, deposit_status([], now))

        return run(self._factory, work)

    def update(
        self,
        patient_id: int,
        now: datetime,
        *,
        name: str | None = None,
        phone: str | None = None,
        date_of_birth: date | None = None,
        allow_duplicate: bool = False,
    ) -> PatientView:
        """Correct a patient's details (a new phone number, a misspelt name, a wrong birth date).

        Appointments follow the patient, so nothing is rebooked. A new phone that already belongs to
        someone else is refused, and a new name and birth date that match another patient are
        refused unless the caller confirms they are different people.
        """
        cleaned = _clean_name(name) if name is not None else None
        normalised = _normalised(phone) if phone is not None else None
        if date_of_birth is not None:
            _check_birth_date(date_of_birth, now)

        def work(session: Session) -> PatientView:
            patient = repo.get_patient(session, patient_id, lock=True)
            refuse_erased(patient)
            if normalised is not None and normalised != patient.phone:
                _refuse_taken_phone(repo.patient_by_phone(session, normalised))
            new_name = cleaned if cleaned is not None else patient.name
            new_birth = date_of_birth if date_of_birth is not None else patient.date_of_birth
            changed = (new_name, new_birth) != (patient.name, patient.date_of_birth)
            if changed and not allow_duplicate:
                _refuse_duplicates(repo.patients_like(session, new_name, new_birth, patient.id))
            patient.name = new_name
            patient.date_of_birth = new_birth
            if normalised is not None:
                patient.phone = normalised
            session.flush()
            return _view(
                patient, deposit_status(repo.penalty_events(session, patient.id, now), now)
            )

        return run(self._factory, work)

    def record_consent(self, patient_id: int, now: datetime) -> PatientView:
        """Record that the patient accepted the current privacy notice."""

        def work(session: Session) -> PatientView:
            patient = repo.get_patient(session, patient_id, lock=True)
            refuse_erased(patient)
            patient.consent_at, patient.consent_version = now, CONSENT_VERSION
            session.flush()
            return _view(
                patient, deposit_status(repo.penalty_events(session, patient.id, now), now)
            )

        return run(self._factory, work)

    def erase(self, patient_id: int, now: datetime) -> PatientView:
        """Erase a patient's personal data on request (DPDP Act right to erasure).

        The name, phone and date of birth are replaced and the free-text reasons of their
        appointments are blanked, so nothing identifies them. The appointments themselves stay,
        with the doctor, time and outcome, because the clinic's counts and a doctor's schedule
        depend on them. Refused while the patient has an upcoming booking or a live waitlist
        entry, since erasing then would silently cancel care; leave those first. Repeating it
        changes nothing.
        """

        def work(session: Session) -> PatientView:
            patient = repo.get_patient(session, patient_id, lock=True)
            if patient.erased_at is not None:
                return _view(patient)
            upcoming = session.scalar(
                select(Appointment.id)
                .where(
                    Appointment.patient_id == patient.id,
                    Appointment.status.in_(_UPCOMING),
                    Appointment.start_at > now,
                )
                .limit(1)
            )
            waiting = session.scalar(
                select(WaitlistEntry.id)
                .where(
                    WaitlistEntry.patient_id == patient.id,
                    WaitlistEntry.status.in_(_LIVE_WAITLIST),
                )
                .limit(1)
            )
            if upcoming is not None or waiting is not None:
                raise ConflictError(
                    ErrorCode.PATIENT_HAS_UPCOMING,
                    "This patient still has an upcoming appointment or a waitlist place. Cancel "
                    "or complete those first, then erase.",
                    patient_id=patient.id,
                    has_upcoming_appointment=upcoming is not None,
                    on_waitlist=waiting is not None,
                )
            scrub_patient(session, patient, erased_phone(patient.id))
            patient.name = ERASED_NAME
            patient.phone = erased_phone(patient.id)
            patient.date_of_birth = EARLIEST_BIRTH_DATE
            patient.consent_at = patient.consent_version = None
            patient.erased_at = now
            for appointment in session.scalars(
                select(Appointment).where(Appointment.patient_id == patient.id)
            ):
                appointment.reason = ERASED_REASON
            session.flush()
            return _view(patient)

        return run(self._factory, work)

    def inactive_ids(self, now: datetime, days: int) -> list[int]:
        """Patients not yet erased who have had no appointment or waitlist entry for `days` days
        and have nothing upcoming: the candidates a retention rule would erase."""
        cutoff = now - timedelta(days=days)

        def work(session: Session) -> list[int]:
            recent_appointment = select(Appointment.patient_id).where(
                (Appointment.start_at >= cutoff) | (Appointment.status == "BOOKED")
            )
            recent_waitlist = select(WaitlistEntry.patient_id).where(
                (WaitlistEntry.created_at >= cutoff) | WaitlistEntry.status.in_(_LIVE_WAITLIST)
            )
            return list(
                session.scalars(
                    select(Patient.id)
                    .where(
                        Patient.erased_at.is_(None),
                        Patient.created_at < cutoff,
                        Patient.id.not_in(recent_appointment),
                        Patient.id.not_in(recent_waitlist),
                    )
                    .order_by(Patient.id)
                )
            )

        return run(self._factory, work)

    def get(self, patient_id: int, now: datetime) -> PatientView:
        def work(session: Session) -> PatientView:
            patient = repo.get_patient(session, patient_id)
            return _view(
                patient, deposit_status(repo.penalty_events(session, patient.id, now), now)
            )

        return run(self._factory, work)

    def search(
        self, *, phone: str | None, name_prefix: str | None, limit: int, offset: int
    ) -> Page[PatientView]:
        """Exact match on the normalised phone, and/or a case-insensitive prefix of the name."""
        normalised = _normalised(phone) if phone is not None else None
        prefix = name_prefix.strip() if name_prefix is not None else None

        def work(session: Session) -> Page[PatientView]:
            rows, total = repo.find_patients(
                session, phone=normalised, name_prefix=prefix or None, limit=limit, offset=offset
            )
            return Page([_view(p) for p in rows], total, limit, offset)

        return run(self._factory, work)
