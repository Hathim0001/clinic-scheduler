"""Consent record and erasure marker on patients (India's DPDP Act: consent, erasure).

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE patients
          ADD COLUMN consent_at      timestamptz,
          ADD COLUMN consent_version text,
          ADD COLUMN erased_at       timestamptz,
          ADD CONSTRAINT patients_consent_pair
            CHECK ((consent_at IS NULL) = (consent_version IS NULL));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE patients
          DROP CONSTRAINT patients_consent_pair,
          DROP COLUMN erased_at,
          DROP COLUMN consent_version,
          DROP COLUMN consent_at;
        """
    )
