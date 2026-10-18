"""Hardening: who did it, an append-only audit table, and a way to expire idempotency keys.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE appointment_events
          ADD COLUMN actor text NOT NULL DEFAULT 'system' CHECK (length(actor) BETWEEN 1 AND 60);

        -- The audit trail is append-only in the database itself, not just in the application.
        CREATE FUNCTION appointment_events_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'appointment_events is append-only (% is not allowed)', TG_OP
            USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$;
        CREATE TRIGGER appointment_events_no_change
          BEFORE UPDATE OR DELETE ON appointment_events
          FOR EACH ROW EXECUTE FUNCTION appointment_events_append_only();

        -- Old idempotency keys are deleted by age, so the table does not grow without bound.
        CREATE INDEX ix_idempotency_created ON idempotency_keys (created_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_idempotency_created;
        DROP TRIGGER IF EXISTS appointment_events_no_change ON appointment_events;
        DROP FUNCTION IF EXISTS appointment_events_append_only();
        ALTER TABLE appointment_events DROP COLUMN IF EXISTS actor;
        """
    )
