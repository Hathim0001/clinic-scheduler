"""Facts the seed script recorded about the demo data, for the clock presets in the UI."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import AppMeta
from app.services.support import run


@dataclass(frozen=True, slots=True)
class SeedFacts:
    anchor_date: str | None  # the date the seed scenarios are built around
    queue_day: str | None  # the day that has a full queue (the "Seed day" clock preset)


class MetaService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def seed_facts(self) -> SeedFacts:
        def work(session: Session) -> SeedFacts:
            rows = dict(session.execute(select(AppMeta.key, AppMeta.value)).all())
            return SeedFacts(rows.get("seed_anchor_date"), rows.get("seed_queue_day"))

        return run(self._factory, work)
