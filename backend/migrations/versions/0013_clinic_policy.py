"""The clinic's editable rules: one row of numbers a manager may change.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE clinic_policy (
          id                     smallint PRIMARY KEY CHECK (id = 1),
          horizon_days           integer NOT NULL DEFAULT 60
                                 CHECK (horizon_days BETWEEN 1 AND 365),
          late_cancel_hours      integer NOT NULL DEFAULT 2
                                 CHECK (late_cancel_hours BETWEEN 0 AND 72),
          strike_lookback_days   integer NOT NULL DEFAULT 30
                                 CHECK (strike_lookback_days BETWEEN 1 AND 180),
          strikes                integer NOT NULL DEFAULT 2 CHECK (strikes BETWEEN 1 AND 10),
          undo_minutes           integer NOT NULL DEFAULT 10
                                 CHECK (undo_minutes BETWEEN 0 AND 60),
          offer_hold_minutes     integer NOT NULL DEFAULT 30
                                 CHECK (offer_hold_minutes BETWEEN 5 AND 240),
          reminder_first_hours   integer NOT NULL DEFAULT 24
                                 CHECK (reminder_first_hours BETWEEN 0 AND 168),
          reminder_second_hours  integer NOT NULL DEFAULT 2
                                 CHECK (reminder_second_hours BETWEEN 0 AND 48),
          updated_at             timestamptz NOT NULL DEFAULT now(),
          updated_by             text
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE clinic_policy;")
