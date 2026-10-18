"""Staff tokens, which address the rate limit counts, and the settings that control them."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.api.ratelimit import client_address
from app.core.auth import issue_token, verify_token
from app.core.config import Settings

pytestmark = pytest.mark.unit

PASSWORD = "correct horse battery"


# ------------------------------------------------------------------------------------- tokens


def test_a_token_round_trips_to_the_staff_name() -> None:
    token, expires = issue_token(PASSWORD, "Meera", now=1_000, ttl_seconds=60)
    assert expires == 1_060
    assert verify_token(PASSWORD, token, now=1_059) == "Meera"


def test_a_token_stops_working_after_its_expiry() -> None:
    token, _ = issue_token(PASSWORD, "Meera", now=1_000, ttl_seconds=60)
    assert verify_token(PASSWORD, token, now=1_060) == "Meera"  # the last second still counts
    assert verify_token(PASSWORD, token, now=1_061) is None


def test_a_token_is_bound_to_the_password() -> None:
    token, _ = issue_token(PASSWORD, "Meera", now=1_000, ttl_seconds=60)
    assert verify_token(PASSWORD + "x", token, now=1_001) is None


def test_a_changed_name_or_expiry_breaks_the_signature() -> None:
    token, _ = issue_token(PASSWORD, "Meera", now=1_000, ttl_seconds=60)
    body, signature = token.split(".")
    other, _ = issue_token(PASSWORD, "Admin", now=1_000, ttl_seconds=60)
    assert verify_token(PASSWORD, other.split(".")[0] + "." + signature, now=1_001) is None
    assert verify_token(PASSWORD, body + "." + signature[:-2] + "AA", now=1_001) is None


@pytest.mark.parametrize(
    "garbage",
    ["", ".", "a.b", "a.b.c", "not a token", "{}.{}", "é.é", "A" * 5000, "e30.e30"],
)
def test_garbage_is_refused_without_an_exception(garbage: str) -> None:
    assert verify_token(PASSWORD, garbage, now=1_000) is None


def test_a_correctly_signed_body_of_the_wrong_shape_is_refused() -> None:
    import base64
    import hashlib
    import hmac
    import json

    def sign(claims: Any) -> str:
        key = hashlib.sha256(f"clinic-scheduler-staff:{PASSWORD}".encode()).digest()
        body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        signature = hmac.new(key, body.encode(), hashlib.sha256).digest()
        return body + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

    assert verify_token(PASSWORD, sign({"n": "x", "e": 9_999}), now=1) == "x"
    wrong_shapes: list[Any] = [{"n": 5, "e": 9_999}, {"n": "x", "e": "9999"}, {"n": "x"}, [], "x"]
    for claims in wrong_shapes:
        assert verify_token(PASSWORD, sign(claims), now=1) is None


# ------------------------------------------------------------------------- the client address


def scope(client: str | None, forwarded: str | None = None) -> dict[str, Any]:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return {"type": "http", "client": (client, 5000) if client else None, "headers": headers}


def test_without_a_proxy_the_socket_address_counts_whatever_the_header_says() -> None:
    assert client_address(scope("10.0.0.5", "1.2.3.4"), 0) == "10.0.0.5"
    assert client_address(scope(None), 0) == "unknown"


def test_behind_one_proxy_the_right_most_entry_counts() -> None:
    assert client_address(scope("10.0.0.5", "203.0.113.9"), 1) == "203.0.113.9"
    assert client_address(scope("10.0.0.5", "203.0.113.9, 10.1.1.1"), 1) == "10.1.1.1"


def test_a_forged_left_hand_entry_cannot_change_the_counted_address() -> None:
    honest = client_address(scope("10.0.0.5", "203.0.113.9"), 1)
    forged = client_address(scope("10.0.0.5", "9.9.9.9, 203.0.113.9"), 1)
    assert honest == forged == "203.0.113.9"


def test_two_hops_reads_the_second_from_the_right() -> None:
    assert client_address(scope("10.0.0.5", "7.7.7.7, 203.0.113.9, 10.1.1.1"), 2) == "203.0.113.9"


def test_a_header_with_too_few_entries_falls_back_to_the_socket() -> None:
    assert client_address(scope("10.0.0.5", "203.0.113.9"), 2) == "10.0.0.5"
    assert client_address(scope("10.0.0.5", " , ,"), 1) == "10.0.0.5"
    assert client_address(scope("10.0.0.5"), 1) == "10.0.0.5"  # no header at all


# ----------------------------------------------------------------------------------- settings


def settings(**values: Any) -> Settings:
    return Settings(**values, _env_file=None)  # type: ignore[call-arg]


def test_login_is_off_by_default_and_blank_means_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STAFF_PASSWORD", raising=False)
    assert settings().staff_password is None
    assert settings(staff_password="   ").staff_password is None
    monkeypatch.setenv("STAFF_PASSWORD", "")
    assert settings().staff_password is None


def test_a_short_staff_password_is_refused() -> None:
    with pytest.raises(ValidationError):
        settings(staff_password="short")
    assert settings(staff_password="long enough").staff_password == "long enough"


def test_proxy_pool_and_sweep_settings_are_bounded() -> None:
    assert settings().trusted_proxy_hops == 0
    assert settings().db_pool_size == 5
    for bad in (
        {"trusted_proxy_hops": -1},
        {"trusted_proxy_hops": 6},
        {"db_pool_size": 0},
        {"offer_sweep_interval_s": -1},
    ):
        with pytest.raises(ValidationError):
            settings(**bad)
