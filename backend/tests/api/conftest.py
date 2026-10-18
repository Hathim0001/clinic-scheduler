"""Fixtures for tests that go through the HTTP layer with a real application and database."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.timeutil import IST
from app.main import create_app
from tests.integration.conftest import MONDAY, NOW, Clinic, at, clinic  # noqa: F401 - fixtures

ORIGIN = "http://localhost:5173"
BASE = "/api/v1"


def clock(instant: datetime) -> dict[str, str]:
    """The X-Test-Clock header for an instant, written the way a reviewer would type it."""
    return {"X-Test-Clock": instant.astimezone(IST).isoformat(timespec="seconds")}


@dataclass
class Api:
    http: TestClient
    clinic: Clinic

    def get(self, path: str, now: datetime = NOW, **kwargs: Any) -> Any:
        return self.http.get(
            f"{BASE}{path}", headers=clock(now) | kwargs.pop("headers", {}), **kwargs
        )

    def post(self, path: str, body: Any = None, now: datetime = NOW, **kwargs: Any) -> Any:
        headers = clock(now) | kwargs.pop("headers", {})
        return self.http.post(f"{BASE}{path}", json=body, headers=headers, **kwargs)

    def put(self, path: str, body: Any, now: datetime = NOW, **kwargs: Any) -> Any:
        headers = clock(now) | kwargs.pop("headers", {})
        return self.http.put(f"{BASE}{path}", json=body, headers=headers, **kwargs)

    def patch(self, path: str, body: Any, now: datetime = NOW, **kwargs: Any) -> Any:
        headers = clock(now) | kwargs.pop("headers", {})
        return self.http.patch(f"{BASE}{path}", json=body, headers=headers, **kwargs)

    def delete(self, path: str, now: datetime = NOW, **kwargs: Any) -> Any:
        return self.http.delete(
            f"{BASE}{path}", headers=clock(now) | kwargs.pop("headers", {}), **kwargs
        )


def make_settings(database_url: str, **values: Any) -> Settings:
    defaults: dict[str, Any] = {
        "database_url": database_url,
        "cors_origins": ORIGIN,
        "test_clock_enabled": True,
        "log_level": "WARNING",
        "offer_sweep_interval_s": 0,
    }
    return Settings(**(defaults | values), _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def api(clinic: Clinic, database_url: str) -> Iterator[Api]:  # noqa: F811 - the imported fixture
    app = create_app(make_settings(database_url))
    with TestClient(app, raise_server_exceptions=False) as http:
        yield Api(http, clinic)
