"""Operations: not accepting bookings, check-in, waitlist declines, audit events, idempotency keys.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE doctors ADD COLUMN accepting_bookings boolean NOT NULL DEFAULT true;
        ALTER TABLE appointments ADD COLUMN checked_in_at timestamptz;
        ALTER TABLE waitlist_entries ADD COLUMN declined_start_at timestamptz;

        CREATE TABLE appointment_events (
          id              serial PRIMARY KEY,
          appointment_id  integer NOT NULL REFERENCES appointments(id),
          patient_id      integer NOT NULL REFERENCES patients(id),
          kind            text    NOT NULL CHECK (length(kind) BETWEEN 1 AND 30),
          at              timestamptz NOT NULL,
          detail          jsonb   NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX ix_events_appointment ON appointment_events (appointment_id, id);
        CREATE INDEX ix_events_patient ON appointment_events (patient_id, id);

        CREATE TABLE idempotency_keys (
          key             text PRIMARY KEY CHECK (length(key) BETWEEN 1 AND 100),
          request_hash    text NOT NULL,
          appointment_id  integer NOT NULL REFERENCES appointments(id),
          created_at      timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS idempotency_keys;
        DROP TABLE IF EXISTS appointment_events;
        ALTER TABLE waitlist_entries DROP COLUMN IF EXISTS declined_start_at;
        ALTER TABLE appointments DROP COLUMN IF EXISTS checked_in_at;
        ALTER TABLE doctors DROP COLUMN IF EXISTS accepting_bookings;
        """
    )
