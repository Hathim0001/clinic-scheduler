"""One reminder of each kind per appointment, however many servers run the scheduler.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX ux_notifications_one_reminder
          ON notifications (appointment_id, kind)
          WHERE kind IN ('REMINDER_FIRST', 'REMINDER_SECOND');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ux_notifications_one_reminder;")
