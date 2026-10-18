"""The live rule proof: scenarios run against the real rules and database, then rolled back."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import AdminOnly
from app.api.schemas.responses import ProofCaseOut, ProofOut
from app.services.proof_service import run_proof

router = APIRouter(tags=["proof"])
_one_at_a_time = threading.Lock()  # each run holds a connection and a transaction for a moment


@router.post(
    "/diagnostics/proof",
    response_model=ProofOut,
    summary="Run the rule scenarios and roll them back",
    dependencies=[AdminOnly],
)
def run_rule_proof(request: Request) -> ProofOut:
    """Runs fixed scenarios (the 2-hour boundary, the 60-day limit, the deposit flag, an atomic
    move, and more) through the real services and PostgreSQL constraints inside a transaction that
    is always rolled back. `rows_before` and `rows_after` show that nothing was kept. It uses its
    own fixed clock and its own doctors and patients, so it never reads clinic data."""
    with _one_at_a_time:
        report = run_proof(request.app.state.engine)
    return ProofOut(
        passed=report.passed,
        rows_before=report.rows_before,
        rows_after=report.rows_after,
        cases=[
            ProofCaseOut(
                id=c.id,
                rule=c.rule,
                scenario=c.scenario,
                expected=c.expected,
                observed=c.observed,
                passed=c.passed,
            )
            for c in report.cases
        ],
    )


class AuditOut(BaseModel):
    events_checked: int
    broken_event_ids: list[int]
    intact: bool


@router.get(
    "/diagnostics/audit",
    response_model=AuditOut,
    summary="Check that no past audit event has been altered",
    dependencies=[AdminOnly],
)
def verify_audit(request: Request) -> AuditOut:
    """Each audit event carries a hash that includes the one before it (set by a database trigger).
    This recomputes them all in the database and lists any event that no longer matches."""
    checked, broken = request.app.state.services.records.verify_audit()
    return AuditOut(events_checked=checked, broken_event_ids=broken, intact=not broken)
