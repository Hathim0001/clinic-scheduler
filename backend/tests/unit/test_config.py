"""Settings parsing: defaults are safe and environment variables override them."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.unit


def make_settings(**values: Any) -> Settings:
    """Settings that ignore any .env file on disk, so a test sees only what it sets."""
    return Settings(**values, _env_file=None)  # type: ignore[call-arg]


def test_defaults_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL",
        "CORS_ORIGINS",
        "TEST_CLOCK_ENABLED",
        "LOG_LEVEL",
        "SEED_ANCHOR_DATE",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = make_settings()
    assert settings.test_clock_enabled is False  # the reviewer clock must be opted into
    assert settings.log_level == "INFO"
    assert settings.seed_anchor_date is None
    assert settings.cors_origin_list == ["http://localhost:5173", "http://localhost:8080"]


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.example/clinic?sslmode=require")
    monkeypatch.setenv("TEST_CLOCK_ENABLED", "true")
    monkeypatch.setenv("CORS_ORIGINS", " https://a.example , https://b.example ,, ")
    monkeypatch.setenv("SEED_ANCHOR_DATE", "2026-10-22")
    settings = make_settings()
    assert settings.database_url.endswith("sslmode=require")
    assert settings.test_clock_enabled is True
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]
    assert settings.seed_anchor_date == date(2026, 10, 22)


def test_log_level_is_normalised_and_validated() -> None:
    assert make_settings(log_level="debug").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        make_settings(log_level="chatty")
