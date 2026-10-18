"""Individual staff accounts with roles (optional: used only when AUTH_SECRET is set).

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE staff_accounts (
          id            serial PRIMARY KEY,
          username      text NOT NULL,
          display_name  text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 100),
          password_hash text NOT NULL,
          role          text NOT NULL CHECK (role IN ('ADMIN', 'RECEPTIONIST')),
          active        boolean NOT NULL DEFAULT true,
          created_at    timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT staff_username_key UNIQUE (username),
          CONSTRAINT staff_username_shape
            CHECK (username = lower(username) AND username ~ '^[a-z0-9._-]{3,40}$')
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE staff_accounts;")
