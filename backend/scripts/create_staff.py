"""Create the first administrator (or any account) straight in the database.

    AUTH_SECRET=... python -m scripts.create_staff --username dev --name "Dev Admin" --role ADMIN

The password is read from the STAFF_NEW_PASSWORD environment variable or prompted for, never taken
from the command line where it would end up in shell history. Once one administrator exists, more
accounts are made in the UI (Staff page) or with `POST /api/v1/staff`. The database comes from
DATABASE_URL.
"""

from __future__ import annotations

import argparse
import getpass
import os
from collections.abc import Sequence

from app.core.config import get_settings
from app.domain.model import Role
from app.persistence.db import create_db_engine, create_session_factory
from app.services.staff_service import StaffService


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a staff account.")
    parser.add_argument("--username", required=True, help="lower-case letters, digits . _ -")
    parser.add_argument("--name", required=True, help="the name shown in the audit trail")
    parser.add_argument("--role", choices=[r.value for r in Role], default=Role.ADMIN.value)
    parser.add_argument("--doctor-id", type=int, help="the doctor a DOCTOR account belongs to")
    args = parser.parse_args(argv)
    password = os.environ.get("STAFF_NEW_PASSWORD") or getpass.getpass("Password: ")

    engine = create_db_engine(get_settings().database_url)
    try:
        view = StaffService(create_session_factory(engine)).create(
            args.username, args.name, password, Role(args.role), args.doctor_id
        )
    finally:
        engine.dispose()
    print(f"Created {view.role.value} account {view.username!r} (id {view.id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
