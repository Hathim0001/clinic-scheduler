"""Liveness and readiness. They live at the root, outside /api/v1, where platforms expect them."""

from __future__ import annotations

import hmac

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.errors import ApiError, ServiceUnavailable
from app.api.schemas.responses import HealthOut
from app.core import metrics
from app.domain.errors import ErrorCode

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


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Request and rejection counters, Prometheus text format",
)
def prometheus_metrics(request: Request) -> PlainTextResponse:
    """Aggregates only (see `app.core.metrics`): no paths, ids, names or phone numbers. With
    `METRICS_TOKEN` set, a Bearer token is required."""
    token = request.app.state.settings.metrics_token
    if token is not None:
        supplied = request.headers.get("authorization", "")[7:].strip()
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            raise ApiError(ErrorCode.UNAUTHENTICATED, "A metrics token is required.")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")
