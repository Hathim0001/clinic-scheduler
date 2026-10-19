"""Bring a database up to date and, if asked, fill it with the reviewer seed.

    python -m scripts.migrate_and_seed                    migrate only
    python -m scripts.migrate_and_seed --if-empty         migrate, seed only if there are no doctors
    python -m scripts.migrate_and_seed --reset            migrate, wipe every table, seed again
    python -m scripts.migrate_and_seed --print-scenarios  also print the scenario table

The database comes from DATABASE_URL. --if-empty is what the container runs at every start, so a
restart of the hosted API never duplicates data; --reset is run by hand from a laptop.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.domain.model import Role
from app.domain.timeutil import ist_date
from app.persistence.db import create_db_engine, create_session_factory
from app.persistence.models import AppMeta, Doctor, StaffAccount
from app.services.staff_service import StaffService
from scripts.seed import (
    database_is_empty,
    describe_scenarios,
    reset_database,
    scenario_dates,
    seed_database,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def run_migrations(database_url: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


DEMO_ACCOUNTS = (
    # username, display name, role, the doctor's name it belongs to (for a doctor's own login)
    ("reception", "Reception Desk", Role.RECEPTIONIST, None),
    ("dr.rao", "Dr. Ananya Rao", Role.DOCTOR, "Dr. Ananya Rao"),
    ("dr.menon", "Dr. Vikram Menon", Role.DOCTOR, "Dr. Vikram Menon"),
)


def seed_demo_accounts(factory: sessionmaker[Session], password: str) -> list[str]:
    """Make a receptionist and a login for each demo doctor, so every role can be tried.

    Only runs when SEED_DEMO_ACCOUNTS is set, with a password from DEMO_ACCOUNTS_PASSWORD. Accounts
    that already exist are left alone, so it is safe at every start. The demo data and its logins
    are for a laptop or a review, never for a real clinic."""
    made: list[str] = []
    staff = StaffService(factory)
    with factory() as session:
        taken = set(session.scalars(select(StaffAccount.username)))
        doctors = {d.name: d.id for d in session.scalars(select(Doctor))}
    for username, name, role, doctor in DEMO_ACCOUNTS:
        if username in taken or (doctor is not None and doctor not in doctors):
            continue
        staff.create(username, name, password, role, doctors.get(doctor) if doctor else None)
        made.append(username)
    return made


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--if-empty", action="store_true", help="seed only when there are no doctors"
    )
    parser.add_argument("--reset", action="store_true", help="wipe every table, then seed")
    parser.add_argument("--print-scenarios", action="store_true", help="print the scenario table")
    args = parser.parse_args(argv)

    settings = get_settings()
    run_migrations(settings.database_url)
    print("migrations: up to date")

    now = datetime.now(UTC)
    anchor = settings.seed_anchor_date or ist_date(now)
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with factory() as session, session.begin():
            if args.reset:
                reset_database(session)
                seed_database(session, anchor, now)
                print(f"seed: reset and seeded, anchor date {anchor}")
            elif args.if_empty:
                if database_is_empty(session):
                    seed_database(session, anchor, now)
                    print(f"seed: database was empty, seeded, anchor date {anchor}")
                else:
                    print("seed: database already has data, left untouched")
            if args.print_scenarios:
                stored = session.get(AppMeta, "seed_anchor_date")
                shown = date.fromisoformat(stored.value) if stored else anchor
                print("\n".join(describe_scenarios(scenario_dates(shown))))
        demo_password = os.environ.get("DEMO_ACCOUNTS_PASSWORD", "")
        if (
            os.environ.get("SEED_DEMO_ACCOUNTS", "").lower() in ("1", "true", "yes")
            and demo_password
        ):
            made = seed_demo_accounts(factory, demo_password)
            if made:
                print(f"demo accounts: created {', '.join(made)}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
