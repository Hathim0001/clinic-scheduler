"""Reading and changing the clinic's own rules (see `app/domain/policy.py`)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

import structlog
from sqlalchemy.orm import Session, sessionmaker

from app.core.actor import current_actor
from app.domain.errors import ErrorCode, RuleViolation
from app.domain.policy import FIELD_NAMES, Policy, problems
from app.persistence import repositories as repo
from app.persistence.models import ClinicPolicy
from app.services.support import run

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class PolicyView:
    policy: Policy
    updated_at: datetime | None  # None while nobody has changed the defaults
    updated_by: str | None


def _view(session: Session) -> PolicyView:
    row = session.get(ClinicPolicy, 1)
    return PolicyView(
        repo.load_policy(session),
        row.updated_at if row is not None else None,
        row.updated_by if row is not None else None,
    )


class PolicyService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get(self) -> PolicyView:
        return run(self._factory, _view)

    def update(self, changes: dict[str, int], now: datetime) -> PolicyView:
        """Apply the fields that are sent. The whole result is checked, so two settings that only
        make sense together (the two reminders) cannot be saved in a broken state."""
        unknown = set(changes) - set(FIELD_NAMES)
        if unknown:
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR,
                "That is not a clinic setting.",
                field=sorted(unknown)[0],
            )

        def work(session: Session) -> PolicyView:
            current = repo.load_policy(session)
            proposed = replace(current, **changes)
            wrong = problems(proposed)
            if wrong:
                field, why = next(iter(wrong.items()))
                raise RuleViolation(
                    ErrorCode.VALIDATION_ERROR, f"{field} {why}.", field=field, problems=wrong
                )
            row = session.get(ClinicPolicy, 1)
            if row is None:
                row = ClinicPolicy(id=1)
                session.add(row)
            for name in FIELD_NAMES:
                setattr(row, name, getattr(proposed, name))
            row.updated_at, row.updated_by = now, current_actor.get()
            session.flush()
            log.info(
                "policy.updated",
                changed={k: v for k, v in changes.items() if getattr(current, k) != v},
            )
            return _view(session)

        return run(self._factory, work)
