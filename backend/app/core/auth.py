"""Signed, expiring staff tokens, with nothing but the standard library.

A token is `base64url(json).signature`, where the json holds the staff member's name, role and an
expiry (and the account id when they signed in with an individual account) and the signature is
HMAC-SHA256 under a key derived from the server's signing secret (`AUTH_SECRET`, or the shared
`STAFF_PASSWORD` when that is all that is set). Changing the secret invalidates every token at once.
The role in a token is only a hint for the UI: for an individual account the server reads the
current role and active flag from the database on every request, so demoting or deactivating
someone takes effect immediately.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Claims:
    name: str
    role: str  # "ADMIN" or "RECEPTIONIST"
    account_id: int | None  # None for the shared-password login


def _key(secret: str) -> bytes:
    return hashlib.sha256(f"clinic-scheduler-staff:{secret}".encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(
    secret: str,
    name: str,
    now: float,
    ttl_seconds: int,
    role: str = "ADMIN",
    account_id: int | None = None,
) -> tuple[str, int]:
    """A token for `name` and the epoch second at which it stops working."""
    expires = int(now) + ttl_seconds
    claims: dict[str, object] = {"n": name, "e": expires, "r": role}
    if account_id is not None:
        claims["i"] = account_id
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_key(secret), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}", expires


def verify_claims(secret: str, token: str, now: float) -> Claims | None:
    """The claims in a valid, unexpired token, else None. Never raises on bad input."""
    try:
        body, signature = token.split(".")
        expected = _b64(hmac.new(_key(secret), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        claims = json.loads(_unb64(body))
        name, expires = claims["n"], claims["e"]
        role = claims.get("r", "ADMIN")
        account_id = claims.get("i")
    except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        return None
    if not isinstance(name, str) or not isinstance(expires, int) or expires < now:
        return None
    if role not in ("ADMIN", "RECEPTIONIST"):
        return None
    if account_id is not None and not isinstance(account_id, int):
        return None
    return Claims(name, role, account_id)


def verify_token(secret: str, token: str, now: float) -> str | None:
    """The staff name in a valid, unexpired token, else None."""
    claims = verify_claims(secret, token, now)
    return claims.name if claims is not None else None
