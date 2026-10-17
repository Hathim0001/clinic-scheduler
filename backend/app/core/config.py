"""Settings read from environment variables (and an optional backend/.env file).

Every value has a safe default so the app and the tests start without any setup. Nothing secret is
ever hard-coded: the default database URL is the throwaway one from docker-compose.yml.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class Settings(BaseSettings):
    """Each field maps to the upper-case environment variable of the same name."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://clinic:clinic@localhost:5433/clinic"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    # Secure by default: the X-Test-Clock header only works when this is switched on explicitly.
    test_clock_enabled: bool = False
    log_level: str = "INFO"
    # Seconds to wait for the database to accept a connection (Neon may need a few to wake up).
    db_connect_timeout_s: int = Field(default=10, ge=1, le=60)
    seed_anchor_date: date | None = None

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(_LOG_LEVELS)}")
        return level

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS split on commas, trimmed, without empty entries."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings; tests build their own Settings instead of calling this."""
    return Settings()
