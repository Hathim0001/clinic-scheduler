"""T-S01: the migration runs up, down and up again, and the models match the migrated schema."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import Engine, inspect, text

from app.persistence.models import Base
from tests.helpers import alembic_config

pytestmark = pytest.mark.integration

DATA_TABLES = {
    "doctors",
    "weekly_windows",
    "availability_overrides",
    "override_windows",
    "patients",
    "appointments",
    "app_meta",
    "waitlist_entries",
}


def test_upgrade_downgrade_upgrade_is_clean(database_url: str, engine: Engine) -> None:
    """T-S01"""
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) >= DATA_TABLES


def test_models_match_the_migrated_schema(engine: Engine) -> None:
    """T-S01: a column added to the migration but not the models (or the reverse) fails here."""
    assert set(Base.metadata.tables) == DATA_TABLES
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        in_database = {column["name"] for column in inspector.get_columns(table.name)}
        assert {column.name for column in table.columns} == in_database, table.name


def test_the_four_exclusion_constraints_exist(engine: Engine) -> None:
    with engine.connect() as connection:
        names = {
            row[0]
            for row in connection.execute(
                text("SELECT conname FROM pg_constraint WHERE contype = 'x'")
            )
        }
    assert names == {
        "weekly_windows_no_overlap",
        "override_windows_no_overlap",
        "no_doctor_overlap",
        "no_patient_overlap",
    }
