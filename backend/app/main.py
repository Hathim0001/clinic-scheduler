"""The application factory: settings, database, services, middleware and routers wired together.

Run it with  uvicorn app.main:create_app --factory --no-access-log
(the request-context middleware writes one JSON log line per request, so uvicorn's own access log
would only duplicate it).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import anyio.to_thread
import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Services, require_staff
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.ratelimit import RateLimitMiddleware
from app.api.routers import (
    alternatives,
    appointments,
    auth,
    availability,
    clock,
    doctors,
    health,
    patients,
    queue,
    reports,
    waitlist,
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.persistence.db import create_db_engine, create_session_factory

API_PREFIX = "/api/v1"
log = structlog.get_logger()


async def _sweep_offers(app: FastAPI, interval_s: int) -> None:
    """Every `interval_s` seconds, pass lapsed waitlist offers to the next patient in line.

    It runs on the real clock (a test clock only applies to a request) and never stops on an error:
    a database hiccup is logged and the next round tries again.
    """
    while True:
        await asyncio.sleep(interval_s)
        try:
            moved = await anyio.to_thread.run_sync(
                app.state.services.waitlist.sweep, datetime.now(UTC)
            )
            if moved:
                log.info("waitlist.swept", doctors=moved)
        except Exception:
            log.exception("waitlist.sweep_failed")


DESCRIPTION = (
    "Appointment scheduling for a small clinic. The business rules live in `app/domain`, are "
    "enforced by `app/services` and are guaranteed by database constraints. Every instant in a "
    "response is given in UTC and in India Standard Time. With the test clock enabled, send "
    "`X-Test-Clock: 2026-11-02T08:00:00+05:30` to make the server treat that as now."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(
        settings.database_url,
        connect_timeout_s=settings.db_connect_timeout_s,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        sweeper = (
            asyncio.create_task(_sweep_offers(app, settings.offer_sweep_interval_s))
            if settings.offer_sweep_interval_s
            else None
        )
        yield
        if sweeper is not None:
            sweeper.cancel()
        engine.dispose()

    app = FastAPI(
        title="Clinic Appointment Scheduler API",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.services = Services.build(factory)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(clock.router, prefix=API_PREFIX)  # open: shows the time, no personal data
    app.include_router(auth.router, prefix=API_PREFIX)  # open: it is how you sign in
    for router in (
        doctors.router,
        availability.router,
        alternatives.router,
        patients.router,
        appointments.router,
        queue.router,
        waitlist.router,
        reports.router,
    ):
        app.include_router(router, prefix=API_PREFIX, dependencies=[Depends(require_staff)])

    # The last middleware added is the outermost. CORS wraps the request-context middleware, so
    # every response, including its 413 and 500 answers, carries the CORS headers (plan 17.8).
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=settings.rate_limit_per_minute,
        trusted_proxy_hops=settings.trusted_proxy_hops,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Test-Clock",
            "X-Request-ID",
            "Idempotency-Key",
        ],
        expose_headers=["X-Request-ID", "X-Effective-Now", "Retry-After", "Idempotent-Replay"],
        allow_credentials=False,
        max_age=600,
    )
    return app
