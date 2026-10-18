"""Phone numbers are unique again, as the problem statement defines the patient.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Refuses, with a message that says why, if two patients already share a number: the database
    # must not pick which one to keep.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT phone FROM patients GROUP BY phone HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'cannot make patients.phone unique: some numbers are used twice';
          END IF;
        END $$;
        DROP INDEX IF EXISTS ix_patients_phone;
        ALTER TABLE patients ADD CONSTRAINT patients_phone_key UNIQUE (phone);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_phone_key;
        CREATE INDEX ix_patients_phone ON patients (phone);
        """
    )
