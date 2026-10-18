"""Four small changes found in the review of the privacy and messaging work.

- patients.consent_by: who accepted the privacy notice, the patient or (for a child) a guardian.
- patients_phone_check also accepts the reserved erased pattern +910XXXXXXXXX (a real Indian mobile
  never starts with 0 after +91), so an erased patient can never collide with a real number.
- notifications.locked_until: a short lease, so a message is sent outside the database transaction.
- appointments.confirmed_by_phone_at: reception rang the patient to confirm (the call list).

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE patients
          ADD COLUMN consent_by text CHECK (consent_by IN ('PATIENT', 'GUARDIAN'));
        UPDATE patients SET consent_by = 'PATIENT' WHERE consent_at IS NOT NULL;
        ALTER TABLE patients
          ADD CONSTRAINT patients_consent_by_pair CHECK ((consent_at IS NULL) = (consent_by IS NULL));

        ALTER TABLE patients DROP CONSTRAINT patients_phone_check;
        ALTER TABLE patients ADD CONSTRAINT patients_phone_check
          CHECK (phone ~ '^\\+91[6-9][0-9]{9}$' OR phone ~ '^\\+910[0-9]{9}$');

        ALTER TABLE notifications ADD COLUMN locked_until timestamptz;
        ALTER TABLE appointments ADD COLUMN confirmed_by_phone_at timestamptz;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE appointments DROP COLUMN confirmed_by_phone_at;
        ALTER TABLE notifications DROP COLUMN locked_until;
        UPDATE patients SET phone = '+916' || substr(phone, 5)
          WHERE phone ~ '^\\+910';
        ALTER TABLE patients DROP CONSTRAINT patients_phone_check;
        ALTER TABLE patients ADD CONSTRAINT patients_phone_check
          CHECK (phone ~ '^\\+91[6-9][0-9]{9}$');
        ALTER TABLE patients DROP CONSTRAINT patients_consent_by_pair;
        ALTER TABLE patients DROP COLUMN consent_by;
        """
    )
