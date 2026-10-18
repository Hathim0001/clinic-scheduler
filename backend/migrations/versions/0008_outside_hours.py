"""Store whether a booking lies outside the doctor's hours, and index the ones that do.

`needs_attention` used to be worked out for every matching row on every read. It is now stored as
`appointments.outside_hours`, refreshed in the same transaction as any change to a doctor's hours
(the only thing that can change it; a new booking is checked against the hours first). The list of
bookings needing attention then reads a small partial index instead of scanning every booking.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE appointments ADD COLUMN outside_hours boolean NOT NULL DEFAULT false;
        CREATE INDEX ix_appointments_outside_hours ON appointments (start_at)
          WHERE outside_hours AND status = 'BOOKED';
        """
    )
    # Fill it in for the bookings that already exist, with the same code that keeps it current.
    from app.persistence.repositories import refresh_outside_hours

    with Session(bind=op.get_bind()) as session:
        refresh_outside_hours(session)


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX ix_appointments_outside_hours;
        ALTER TABLE appointments DROP COLUMN outside_hours;
        """
    )
