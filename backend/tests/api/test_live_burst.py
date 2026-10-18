"""The reviewer's burst script against a real server on a real socket (T-B12 over HTTP).

Unlike the TestClient tests, this goes through uvicorn, its thread pool and the connection pool:
twenty requests arrive at the same instant, more than the ten database connections, and the rules
must still hold (exactly one booking, nothing but SLOT_TAKEN for the rest, no 5xx).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from app.main import create_app
from scripts import burst, load
from tests.api.conftest import make_settings
from tests.integration.conftest import Clinic, clinic  # noqa: F401 - fixture

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


@pytest.fixture
def live_url(clinic: Clinic, database_url: str) -> Iterator[str]:  # noqa: F811 - the fixture
    app = create_app(make_settings(database_url, test_clock_enabled=False, rate_limit_per_minute=0))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the test server did not start")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=15)


def test_twenty_simultaneous_bookings_of_one_slot_give_one_booking(
    live_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = burst.main(["--base-url", live_url, "--requests", "20", "--doctor-id", "1"])
    output = capsys.readouterr().out
    assert exit_code == 0, output
    assert "HTTP 201 OK: 1" in output
    assert "HTTP 409 SLOT_TAKEN: 19" in output
    assert "PASS" in output


def test_sixty_simultaneous_users_mixing_reads_bookings_and_cancels_break_nothing(
    live_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Far more users than database connections: no 5xx and no doctor is double-booked."""
    exit_code = load.main(["--base-url", live_url, "--users", "60", "--rounds", "3"])
    output = capsys.readouterr().out
    assert exit_code == 0, output
    assert "server errors: 0" in output
    assert "overlaps: 0" in output
