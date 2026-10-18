"""The live rule proof: scenarios run against the real rules and database, then rolled back."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Request

from app.api.schemas.responses import ProofCaseOut, ProofOut
from app.services.proof_service import run_proof

router = APIRouter(tags=["proof"])
_one_at_a_time = threading.Lock()  # each run holds a connection and a transaction for a moment


@router.post(
    "/diagnostics/proof",
    response_model=ProofOut,
    summary="Run the rule scenarios and roll them back",
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
