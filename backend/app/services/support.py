"""Helpers shared by the services."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.db import run_in_transaction
from app.persistence.db_errors import translate_db_error


def run[T](factory: sessionmaker[Session], work: Callable[[Session], T]) -> T:
    """Run `work` in one transaction (retrying once after a deadlock).

    A constraint or data error that a client caused comes out as the domain error the pre-check
    would have given. A busy or unreachable database is left as it is for the API to report as 503.
    """
    try:
        return run_in_transaction(factory, work)
    except DBAPIError as exc:
        translated = translate_db_error(exc)
        if translated is None:
            raise
        raise translated from exc
