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
    # Requests per minute allowed from one client address; 0 switches the limit off.
    rate_limit_per_minute: int = Field(default=600, ge=0, le=100_000)
    # Seconds to wait for the database to accept a connection (Neon may need a few to wake up).
    db_connect_timeout_s: int = Field(default=10, ge=1, le=60)
    seed_anchor_date: date | None = None
    # Database connections kept per process (and how many more a burst may borrow).
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    # How many reverse proxies sit in front of the API and append to X-Forwarded-For. The client
    # address is read that many entries from the RIGHT, because everything to the left can be
    # forged by the caller. 0 means no proxy: the socket address is used.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    # Staff login. Unset (the default) leaves the API open, as the assignment allows; set it and
    # every route except the health checks, the clock and the login itself needs a signed token.
    staff_password: str | None = Field(default=None, min_length=8)
    auth_token_ttl_hours: int = Field(default=12, ge=1, le=168)
    # Individual staff accounts with roles. Unset (the default) leaves them off. Set it to a long
    # random string and people sign in with their own username and password; the shared
    # STAFF_PASSWORD, if also set, still works as an administrator, to create the first account.
    auth_secret: str | None = Field(default=None, min_length=16)
    # How often (seconds) the server passes lapsed waitlist offers to the next patient. 0 is off.
    offer_sweep_interval_s: int = Field(default=30, ge=0, le=3600)

    @field_validator("staff_password", "auth_secret", mode="before")
    @classmethod
    def _blank_means_off(cls, value: object) -> object:
        """An empty STAFF_PASSWORD (a variable that exists but holds nothing) leaves login off."""
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def auth_required(self) -> bool:
        """Is any kind of staff sign-in switched on?"""
        return self.staff_password is not None or self.auth_secret is not None

    @property
    def signing_secret(self) -> str | None:
        """What tokens are signed with: AUTH_SECRET, else the shared password."""
        return self.auth_secret or self.staff_password

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
