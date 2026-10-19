"""Doctor logins, one-time password-reset codes, and a stamp that ends old sessions.

- staff_accounts.role also allows DOCTOR, and a DOCTOR account names the doctor it belongs to
  (`doctor_id`). There is deliberately no foreign key: a reset of the demo data empties the doctors
  table, and that must not take the staff accounts with it.
- reset_code_hash / reset_expires_at: an administrator issues a single-use code that lets the person
  choose a new password. Only a hash is stored.
- password_changed_at: a token issued before this moment no longer works, so changing or resetting
  a password signs the account out everywhere.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE staff_accounts DROP CONSTRAINT staff_accounts_role_check;
        ALTER TABLE staff_accounts ADD CONSTRAINT staff_accounts_role_check
          CHECK (role IN ('ADMIN', 'RECEPTIONIST', 'DOCTOR'));
        ALTER TABLE staff_accounts ADD COLUMN doctor_id integer;
        ALTER TABLE staff_accounts ADD CONSTRAINT staff_doctor_role_pair
          CHECK ((role = 'DOCTOR') = (doctor_id IS NOT NULL));
        ALTER TABLE staff_accounts ADD COLUMN reset_code_hash text;
        ALTER TABLE staff_accounts ADD COLUMN reset_expires_at timestamptz;
        ALTER TABLE staff_accounts ADD CONSTRAINT staff_reset_pair
          CHECK ((reset_code_hash IS NULL) = (reset_expires_at IS NULL));
        ALTER TABLE staff_accounts
          ADD COLUMN password_changed_at timestamptz NOT NULL DEFAULT now();
        UPDATE staff_accounts SET password_changed_at = created_at;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM staff_accounts WHERE role = 'DOCTOR';
        ALTER TABLE staff_accounts DROP COLUMN password_changed_at;
        ALTER TABLE staff_accounts DROP CONSTRAINT staff_reset_pair;
        ALTER TABLE staff_accounts DROP COLUMN reset_expires_at;
        ALTER TABLE staff_accounts DROP COLUMN reset_code_hash;
        ALTER TABLE staff_accounts DROP CONSTRAINT staff_doctor_role_pair;
        ALTER TABLE staff_accounts DROP COLUMN doctor_id;
        ALTER TABLE staff_accounts DROP CONSTRAINT staff_accounts_role_check;
        ALTER TABLE staff_accounts ADD CONSTRAINT staff_accounts_role_check
          CHECK (role IN ('ADMIN', 'RECEPTIONIST'));
        """
    )
