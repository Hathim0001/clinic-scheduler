"""Make the audit trail tamper-evident: each event carries a hash of the one before it.

Every `appointment_events` row stores `prev_hash` (the previous event of the same appointment) and
`row_hash` (a SHA-256 over the previous hash and the row's own content), both computed by a trigger,
so the application cannot get them wrong or skip them. `verify_audit_chain()` recomputes everything
and lists the events whose hash no longer matches. Together with the append-only trigger this means
a change to a past event is either refused or shows up as a break. It is evidence, not proof: someone
with full database rights could recompute the chain, which is why the README says tamper-evident.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE appointment_events ADD COLUMN prev_hash bytea, ADD COLUMN row_hash bytea;

        CREATE FUNCTION appointment_event_hash(prev bytea, e appointment_events) RETURNS bytea
        LANGUAGE sql STABLE AS $$
          SELECT sha256(convert_to(
            coalesce(encode(prev, 'hex'), '') || '|' || e.id || '|' || e.appointment_id || '|'
            || e.patient_id || '|' || e.kind || '|'
            || to_char(e.at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '|' || e.actor
            || '|' || e.detail::text, 'UTF8'))
        $$;

        CREATE FUNCTION appointment_events_chain() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE previous bytea;
        BEGIN
          SELECT row_hash INTO previous FROM appointment_events
            WHERE appointment_id = NEW.appointment_id ORDER BY id DESC LIMIT 1;
          NEW.prev_hash := previous;
          NEW.row_hash := appointment_event_hash(previous, NEW);
          RETURN NEW;
        END;
        $$;

        -- chain the events that already exist, once, with the append-only guard stood down
        ALTER TABLE appointment_events DISABLE TRIGGER appointment_events_no_change;
        DO $$
        DECLARE
          r appointment_events%ROWTYPE;
          previous bytea;
          current_appointment integer;
          computed bytea;
        BEGIN
          FOR r IN SELECT * FROM appointment_events ORDER BY appointment_id, id LOOP
            IF current_appointment IS DISTINCT FROM r.appointment_id THEN
              previous := NULL;
              current_appointment := r.appointment_id;
            END IF;
            computed := appointment_event_hash(previous, r);
            UPDATE appointment_events SET prev_hash = previous, row_hash = computed WHERE id = r.id;
            previous := computed;
          END LOOP;
        END;
        $$;
        ALTER TABLE appointment_events ENABLE TRIGGER appointment_events_no_change;

        ALTER TABLE appointment_events ALTER COLUMN row_hash SET NOT NULL;
        CREATE TRIGGER appointment_events_chain_hash
          BEFORE INSERT ON appointment_events
          FOR EACH ROW EXECUTE FUNCTION appointment_events_chain();

        CREATE FUNCTION verify_audit_chain() RETURNS TABLE (event_id integer)
        LANGUAGE sql STABLE AS $$
          SELECT x.id FROM appointment_events x
          LEFT JOIN LATERAL (
            SELECT p.row_hash FROM appointment_events p
            WHERE p.appointment_id = x.appointment_id AND p.id < x.id
            ORDER BY p.id DESC LIMIT 1
          ) earlier ON true
          WHERE x.prev_hash IS DISTINCT FROM earlier.row_hash
             OR x.row_hash IS DISTINCT FROM appointment_event_hash(x.prev_hash, x)
          ORDER BY x.id
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION verify_audit_chain();
        DROP TRIGGER appointment_events_chain_hash ON appointment_events;
        DROP FUNCTION appointment_events_chain();
        DROP FUNCTION appointment_event_hash(bytea, appointment_events);
        ALTER TABLE appointment_events DROP COLUMN row_hash, DROP COLUMN prev_hash;
        """
    )
