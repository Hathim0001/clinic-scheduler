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


# ------------------------------------------------------------------ roles and password hashing


def test_a_token_carries_the_role_and_the_account_id() -> None:
    from app.core.auth import verify_claims

    token, _ = issue_token(PASSWORD, "Meera", 1_000, 60, role="RECEPTIONIST", account_id=7)
    claims = verify_claims(PASSWORD, token, now=1_001)
    assert claims is not None
    assert (claims.name, claims.role, claims.account_id) == ("Meera", "RECEPTIONIST", 7)


def test_a_shared_password_token_is_an_administrator_without_an_account() -> None:
    from app.core.auth import verify_claims

    token, _ = issue_token(PASSWORD, "Meera", 1_000, 60)
    claims = verify_claims(PASSWORD, token, now=1_001)
    assert claims is not None
    assert (claims.role, claims.account_id) == ("ADMIN", None)


def test_a_token_naming_an_unknown_role_is_refused() -> None:
    import base64
    import hashlib
    import hmac
    import json

    from app.core.auth import _key, verify_claims

    body = (
        base64.urlsafe_b64encode(json.dumps({"n": "x", "e": 9_999, "r": "ROOT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    signature = (
        base64.urlsafe_b64encode(hmac.new(_key(PASSWORD), body.encode(), hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    assert verify_claims(PASSWORD, f"{body}.{signature}", now=1_000) is None


def test_a_password_hash_verifies_only_the_right_password() -> None:
    from app.core.passwords import hash_password, verify_password

    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("correct horse batter", stored)


def test_two_hashes_of_one_password_differ_because_each_has_its_own_salt() -> None:
    from app.core.passwords import hash_password

    assert hash_password("same password") != hash_password("same password")


@pytest.mark.parametrize(
    "stored", ["", "plain", "scrypt$1$2", "md5$1$2$3$ab$cd", "scrypt$x$8$1$zz$zz"]
)
def test_an_unreadable_hash_never_verifies_and_never_raises(stored: str) -> None:
    from app.core.passwords import verify_password

    assert verify_password("anything", stored) is False


def test_the_signing_secret_is_the_auth_secret_else_the_shared_password() -> None:
    both = Settings(
        database_url="postgresql+psycopg://x/y", auth_secret="s" * 20, staff_password="p" * 8
    )
    only_shared = Settings(database_url="postgresql+psycopg://x/y", staff_password="p" * 8)
    neither = Settings(database_url="postgresql+psycopg://x/y")
    assert both.signing_secret == "s" * 20
    assert only_shared.signing_secret == "p" * 8
    assert (neither.signing_secret, neither.auth_required) == (None, False)
    assert both.auth_required
    assert only_shared.auth_required


def test_a_short_auth_secret_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://x/y", auth_secret="too-short")
