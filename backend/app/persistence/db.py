"""Engine, session factory and the unit-of-work helper.

Services never open transactions themselves: they hand a function to `run_in_transaction`, which
runs it in one transaction on a fresh session, commits on success, rolls back on any exception and
re-runs it once if PostgreSQL rolled it back because of a deadlock.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.db_errors import is_retryable


def _connect_options(
    statement_timeout_ms: int, lock_timeout_ms: int, idle_tx_timeout_ms: int
) -> str:
    # Sent to the server with every new connection:
    #   timezone=UTC                         timestamptz values come back in UTC
    #   statement_timeout                    no single query runs longer than this
    #   lock_timeout                         waiting for a row lock (the doctor lock) times out
    #   idle_in_transaction_session_timeout  a request that dies holding the lock is cut off
    return (
        f"-c timezone=UTC -c statement_timeout={statement_timeout_ms} "
        f"-c lock_timeout={lock_timeout_ms} "
        f"-c idle_in_transaction_session_timeout={idle_tx_timeout_ms}"
    )


def create_db_engine(
    database_url: str,
    *,
    statement_timeout_ms: int = 8_000,
    lock_timeout_ms: int = 5_000,
    idle_tx_timeout_ms: int = 15_000,
    connect_timeout_s: int = 10,
) -> Engine:
    """One engine per process. pool_pre_ping replaces connections that Neon suspended when idle."""
    return create_engine(
        database_url,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={
            "options": _connect_options(statement_timeout_ms, lock_timeout_ms, idle_tx_timeout_ms),
            "connect_timeout": connect_timeout_s,
        },
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: rows stay readable after the transaction that loaded them ends.
    return sessionmaker(engine, expire_on_commit=False)


def run_in_transaction[T](
    factory: sessionmaker[Session],
    work: Callable[[Session], T],
    *,
    retries: int = 1,
) -> T:
    """Run `work` in one transaction and return its result.

    `work` must be safe to run twice: it may only depend on its arguments (including a `now` fixed
    by the caller), because a deadlock or serialization failure re-runs the whole function.
    """
    attempt = 0
    while True:
        try:
            with factory() as session, session.begin():
                return work(session)
        except DBAPIError as exc:
            if is_retryable(exc) and attempt < retries:
                attempt += 1
                continue
            raise
