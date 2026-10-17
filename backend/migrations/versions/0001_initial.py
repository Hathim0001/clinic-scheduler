"""Initial schema: doctors, availability, patients, appointments.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# The DDL is plain SQL in a file next to this module so it can be read, diffed and run by hand.
_SCHEMA_SQL = Path(__file__).with_name("0001_initial.sql")


def upgrade() -> None:
    # exec_driver_sql sends the text to the driver untouched. Going through text() would treat
    # colons in the SQL as bind parameters.
    op.get_bind().exec_driver_sql(_SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    # The btree_gist extension is left in place: other schemas in the database may use it.
    op.execute(
        "DROP TABLE IF EXISTS app_meta, override_windows, availability_overrides, "
        "weekly_windows, appointments, patients, doctors CASCADE"
    )
