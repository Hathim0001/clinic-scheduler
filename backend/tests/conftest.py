"""Shared fixtures.

Database tests need PostgreSQL, which the plan relies on for its exclusion constraints, so there is
no SQLite fallback. Start the compose database first:  docker compose up -d db
The tests use their own database (clinic_test) on the same server and create it on demand.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from psycopg import sql
from sqlalchemy import Engine, make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.db import create_db_engine, create_session_factory
from tests.helpers import alembic_config

DEFAULT_TEST_URL = "postgresql+psycopg://clinic:clinic@localhost:5433/clinic_test"
# Every data table; alembic_version is left alone.
DATA_TABLES = (
    "appointments, override_windows, availability_overrides, weekly_windows, "
    "patients, doctors, app_meta"
)


def _ensure_database(url: URL) -> None:
    """Create the test database if it does not exist yet (connects to the maintenance database)."""
    try:
        with psycopg.connect(
            host=url.host,
            port=url.port,
            user=url.username,
            password=url.password,
            dbname="postgres",
            autocommit=True,
            connect_timeout=5,
        ) as conn:
            found = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)
            ).fetchone()
            if not found:
                conn.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(str(url.database)))
                )
    except psycopg.OperationalError as exc:
        pytest.fail(
            f"PostgreSQL is not reachable: {exc}\nStart it with:  docker compose up -d db",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of a migrated, empty-schema test database."""
    url = make_url(os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_URL))
    _ensure_database(url)
    rendered = url.render_as_string(hide_password=False)
    command.upgrade(alembic_config(rendered), "head")
    return rendered


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    eng = create_db_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory over empty tables.

    Services commit their own transactions and the concurrency tests need real commits across
    connections, so tests cannot be isolated by rolling back. Each test starts by truncating.
    """
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {DATA_TABLES} RESTART IDENTITY CASCADE"))
    return create_session_factory(engine)
