"""Liveness and readiness. They live at the root, outside /api/v1, where platforms expect them."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.errors import ServiceUnavailable
from app.api.schemas.responses import HealthOut

router = APIRouter(tags=["health"])
log = structlog.get_logger()


@router.get("/healthz", response_model=HealthOut, summary="Liveness: the process is up")
def healthz() -> HealthOut:
    """Never touches the database, so a database outage cannot make the platform restart us."""
    return HealthOut(status="ok")


@router.get("/readyz", response_model=HealthOut, summary="Readiness: the database answers")
def readyz(request: Request) -> HealthOut:
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log.error("database.not_ready", error_type=type(exc).__name__)
        raise ServiceUnavailable("The database is not reachable.") from None
    return HealthOut(status="ready")
