"""Alembic environment.

The migrations are hand-written SQL (Alembic's autogenerate cannot express the partial exclusion
constraints that enforce the booking rules), so there is no model metadata to compare against.
The URL comes from the `sqlalchemy.url` option when a caller sets one (the tests and scripts do),
otherwise from the DATABASE_URL setting.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings

config = context.config


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
