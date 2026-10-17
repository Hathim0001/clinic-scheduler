"""Small builders shared by unit, integration and API tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config

from app.domain.timeutil import IST

BACKEND_DIR = Path(__file__).resolve().parent.parent


def ist(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0, micro: int = 0
) -> datetime:
    """An India wall-clock time as an aware UTC instant: ist(2026, 11, 2, 9, 0) is 09:00 IST."""
    return datetime(year, month, day, hour, minute, second, micro, tzinfo=IST).astimezone(UTC)


def hm(text: str) -> int:
    """'09:30' -> 570 minutes since midnight ('24:00' -> 1440)."""
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def alembic_config(database_url: str) -> Config:
    """Alembic config pointing at an explicit database (the tests never read DATABASE_URL)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config
