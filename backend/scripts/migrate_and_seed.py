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
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.domain.timeutil import ist_date
from app.persistence.db import create_db_engine, create_session_factory
from app.persistence.models import AppMeta
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
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
