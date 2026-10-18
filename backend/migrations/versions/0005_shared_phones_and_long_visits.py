"""Shared phone numbers and visits longer than one slot.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- A family can share one mobile. The service asks for confirmation before it registers a
        -- second patient on a number, so a plain index replaces the unique constraint.
        ALTER TABLE patients DROP CONSTRAINT patients_phone_key;
        CREATE INDEX ix_patients_phone ON patients (phone);

        -- A visit lasts one to four of the doctor's slots.
        ALTER TABLE appointments
          ADD COLUMN slots smallint NOT NULL DEFAULT 1 CHECK (slots BETWEEN 1 AND 4);
        ALTER TABLE appointments DROP CONSTRAINT appt_one_slot_long;
        ALTER TABLE appointments ADD CONSTRAINT appt_whole_slots
          CHECK (end_at - start_at IN (slots * interval '15 minutes', slots * interval '30 minutes'));

        -- An offered slot remembers how long the freed visit was.
        ALTER TABLE waitlist_entries
          ADD COLUMN offered_slots smallint NOT NULL DEFAULT 1 CHECK (offered_slots BETWEEN 1 AND 4);
        """
    )


def downgrade() -> None:
    # Fails, on purpose, while two patients share a number or a visit is longer than one slot:
    # going back would otherwise lose that information.
    op.execute(
        """
        ALTER TABLE waitlist_entries DROP COLUMN IF EXISTS offered_slots;
        ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appt_whole_slots;
        ALTER TABLE appointments
          ADD CONSTRAINT appt_one_slot_long
          CHECK (end_at - start_at IN (interval '15 minutes', interval '30 minutes'));
        ALTER TABLE appointments DROP COLUMN IF EXISTS slots;
        DROP INDEX IF EXISTS ix_patients_phone;
        ALTER TABLE patients ADD CONSTRAINT patients_phone_key UNIQUE (phone);
        """
    )
