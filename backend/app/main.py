"""The application factory: settings, database, services, middleware and routers wired together.

Run it with  uvicorn app.main:create_app --factory --no-access-log
(the request-context middleware writes one JSON log line per request, so uvicorn's own access log
would only duplicate it).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Services
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.ratelimit import RateLimitMiddleware
from app.api.routers import (
    appointments,
    availability,
    clock,
    doctors,
    health,
    patients,
    queue,
    waitlist,
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.persistence.db import create_db_engine, create_session_factory

API_PREFIX = "/api/v1"
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
        settings.database_url, connect_timeout_s=settings.db_connect_timeout_s
    )
    factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
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
    for router in (
        clock.router,
        doctors.router,
        availability.router,
        patients.router,
        appointments.router,
        queue.router,
        waitlist.router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    # The last middleware added is the outermost. CORS wraps the request-context middleware, so
    # every response, including its 413 and 500 answers, carries the CORS headers (plan 17.8).
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Test-Clock", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Effective-Now", "Retry-After"],
        allow_credentials=False,
        max_age=600,
    )
    return app
