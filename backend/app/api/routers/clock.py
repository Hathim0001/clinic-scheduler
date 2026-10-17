"""The clock the server is using for this request, for the UI's clock bar."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request

from app.api.deps import NowDep, ServicesDep, clock_header_value
from app.api.schemas.responses import ClockOut
from app.domain.timeutil import ist_iso, utc_iso

router = APIRouter(tags=["clock"])


@router.get("/clock", response_model=ClockOut, summary="The effective time and test-clock status")
def get_clock(request: Request, services: ServicesDep, now: NowDep) -> ClockOut:
    source: Literal["REAL", "HEADER"] = (
        "HEADER" if clock_header_value(request) is not None else "REAL"
    )
    facts = services.meta.seed_facts()
    return ClockOut(
        now_utc=utc_iso(now),
        now_ist=ist_iso(now),
        source=source,
        test_clock_enabled=request.app.state.settings.test_clock_enabled,
        seed_anchor_date=facts.anchor_date,
        seed_queue_day=facts.queue_day,
    )
