"""The live rule proof: every scenario passes and the database ends up exactly as it began."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import Patient
from app.services import proof_service
from app.services.proof_service import CASES, run_proof
from tests.integration.conftest import Clinic

pytestmark = pytest.mark.integration


def test_every_scenario_gives_the_documented_answer(engine: Engine, clinic: Clinic) -> None:
    report = run_proof(engine)
    wrong = [(c.id, c.expected, c.observed) for c in report.cases if not c.passed]
    assert wrong == [], wrong
    assert len(report.cases) == len(CASES)
    assert report.passed


def test_nothing_is_left_behind_even_next_to_real_data(
    engine: Engine, clinic: Clinic, session_factory: sessionmaker[Session]
) -> None:
    before = clinic.appointments()
    report = run_proof(engine)
    assert report.rows_before == report.rows_after
    assert clinic.appointments() == before
    with session_factory() as session:
        assert not session.query(Patient).filter(Patient.name.like("Proof Patient%")).count()
        assert session.query(Patient).count() == 3  # the three real ones from the fixture


def test_running_it_twice_gives_the_same_answers(engine: Engine, clinic: Clinic) -> None:
    first = [(c.id, c.observed) for c in run_proof(engine).cases]
    second = [(c.id, c.observed) for c in run_proof(engine).cases]
    assert first == second


def test_a_scenario_that_crashes_is_a_failed_case_not_a_failed_run(
    engine: Engine, clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(lab: object) -> tuple[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(proof_service, "CASES", (("broken", "r", "s", broken),))
    report = proof_service.run_proof(engine)
    assert not report.passed
    assert report.cases[0].observed == "RuntimeError: boom"
    assert report.rows_before == report.rows_after
