"""Waitlist: patients waiting for a slot with a doctor on a date, and the offers made to them.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE waitlist_entries (
          id                serial PRIMARY KEY,
          doctor_id         integer NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
          patient_id        integer NOT NULL REFERENCES patients(id),
          on_date           date    NOT NULL
                            CHECK (on_date BETWEEN DATE '2000-01-01' AND DATE '2100-12-31'),
          status            text    NOT NULL DEFAULT 'WAITING',
          offered_start_at  timestamptz,
          offer_expires_at  timestamptz,
          appointment_id    integer REFERENCES appointments(id),
          created_at        timestamptz NOT NULL DEFAULT now(),
          updated_at        timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT waitlist_status_valid
            CHECK (status IN ('WAITING','OFFERED','BOOKED','CANCELLED','EXPIRED')),
          CONSTRAINT waitlist_offer_complete
            CHECK (status <> 'OFFERED' OR (offered_start_at IS NOT NULL AND offer_expires_at IS NOT NULL)),
          CONSTRAINT waitlist_booked_has_appointment
            CHECK (status <> 'BOOKED' OR appointment_id IS NOT NULL)
        );
        -- A patient waits once per doctor and date, however many times they ask.
        CREATE UNIQUE INDEX uq_waitlist_active
          ON waitlist_entries (doctor_id, patient_id, on_date)
          WHERE status IN ('WAITING', 'OFFERED');
        CREATE INDEX ix_waitlist_queue ON waitlist_entries (doctor_id, on_date, created_at, id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS waitlist_entries")
