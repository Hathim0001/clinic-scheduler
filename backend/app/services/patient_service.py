"""Patients: registration, lookup by phone or name, and the deposit flag shown with each patient."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import ConflictError, ErrorCode, RuleViolation
from app.domain.model import DepositStatus
from app.domain.penalties import deposit_status
from app.domain.phone import normalise_phone
from app.domain.timeutil import ist_date
from app.persistence import repositories as repo
from app.persistence.models import Patient
from app.services.support import run
from app.services.views import Page, PatientView

EARLIEST_BIRTH_DATE = date(1900, 1, 1)


def _view(patient: Patient, deposit: DepositStatus | None = None) -> PatientView:
    return PatientView(
        patient.id,
        patient.name,
        patient.phone,
        patient.date_of_birth,
        patient.created_at,
        deposit,
    )


def _normalised(phone: str) -> str:
    try:
        return normalise_phone(phone)
    except ValueError as exc:
        raise RuleViolation(ErrorCode.VALIDATION_ERROR, str(exc), field="phone") from exc


class PatientService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(self, name: str, phone: str, date_of_birth: date, now: datetime) -> PatientView:
        cleaned = name.strip()
        if not 1 <= len(cleaned) <= 100:
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR, "The name must be 1 to 100 characters.", field="name"
            )
        normalised = _normalised(phone)
        if not EARLIEST_BIRTH_DATE <= date_of_birth <= ist_date(now):
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR,
                "The date of birth must be between 1 January 1900 and today.",
                field="date_of_birth",
            )

        def work(session: Session) -> PatientView:
            existing = repo.patient_by_phone(session, normalised)
            if existing is not None:  # a friendlier answer than the constraint's, same code
                raise ConflictError(
                    ErrorCode.PHONE_TAKEN,
                    "A patient with that phone number already exists.",
                    patient_id=existing.id,
                )
            patient = Patient(name=cleaned, phone=normalised, date_of_birth=date_of_birth)
            session.add(patient)
            session.flush()  # two requests racing past the check above meet the unique constraint
            return _view(patient, deposit_status([], now))

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
