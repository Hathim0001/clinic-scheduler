"""A transactional outbox of messages to patients.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE notifications (
          id             serial PRIMARY KEY,
          patient_id     integer NOT NULL REFERENCES patients (id),
          appointment_id integer REFERENCES appointments (id),
          kind           text NOT NULL,
          to_phone       text NOT NULL,
          body           text NOT NULL,
          status         text NOT NULL DEFAULT 'PENDING'
                         CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'SKIPPED')),
          attempts       smallint NOT NULL DEFAULT 0,
          last_error     text,
          created_at     timestamptz NOT NULL DEFAULT now(),
          sent_at        timestamptz,
          sent_via       text CHECK (sent_via IN ('GATEWAY', 'MANUAL')),
          CONSTRAINT notifications_sent_pair CHECK ((status = 'SENT') = (sent_at IS NOT NULL))
        );
        CREATE INDEX ix_notifications_open ON notifications (id)
          WHERE status IN ('PENDING', 'SKIPPED');
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE notifications;")
