"""Erase patients who have been inactive for a retention period (DPDP Act: keep data no longer
than needed).

    python -m scripts.purge_inactive --days 1095            list who would be erased (dry run)
    python -m scripts.purge_inactive --days 1095 --apply    erase them

A patient is inactive when they were registered before the cut-off, have had no appointment and no
waitlist entry since, and have nothing upcoming. Erasing uses the same service as the API
(`POST /patients/{id}/erase`), so the appointments stay as anonymous history. The database comes
from DATABASE_URL. Run it from a scheduler (cron, a Render cron job) at whatever period the
clinic's retention policy sets; the default of three years is a placeholder, not legal advice.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.config import get_settings
from app.persistence.db import create_db_engine, create_session_factory
from app.services.patient_service import PatientService

DEFAULT_DAYS = 3 * 365
MIN_DAYS = 30


def purge(service: PatientService, now: datetime, days: int, apply: bool) -> list[int]:
    """The ids that were (or, in a dry run, would be) erased."""
    ids = service.inactive_ids(now, days)
    if apply:
        for patient_id in ids:
            service.erase(patient_id, now)
    return ids


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Erase patients inactive for a retention period.")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="inactivity period in days")
    parser.add_argument("--apply", action="store_true", help="erase; without it only list")
    args = parser.parse_args(argv)
    if args.days < MIN_DAYS:
        parser.error(
            f"--days must be at least {MIN_DAYS} so a mistake cannot erase recent patients"
        )

    engine = create_db_engine(get_settings().database_url)
    try:
        ids = purge(
            PatientService(create_session_factory(engine)), datetime.now(UTC), args.days, args.apply
        )
    finally:
        engine.dispose()
    verb = "erased" if args.apply else "would be erased (dry run; add --apply)"
    print(f"{len(ids)} patient(s) {verb}: {ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
