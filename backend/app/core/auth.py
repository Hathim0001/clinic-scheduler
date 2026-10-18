"""Signed, expiring staff tokens, with nothing but the standard library.

A token is `base64url(json).signature`, where the json holds the staff member's name and an expiry
and the signature is HMAC-SHA256 under a key derived from the staff password. Changing the password
therefore invalidates every token at once. This is a shared-password login, enough to put a name on
each audit row and to keep the public internet out; it is not a user database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json


def _key(password: str) -> bytes:
    return hashlib.sha256(f"clinic-scheduler-staff:{password}".encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(password: str, name: str, now: float, ttl_seconds: int) -> tuple[str, int]:
    """A token for `name` and the epoch second at which it stops working."""
    expires = int(now) + ttl_seconds
    body = _b64(json.dumps({"n": name, "e": expires}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_key(password), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}", expires


def verify_token(password: str, token: str, now: float) -> str | None:
    """The staff name in a valid, unexpired token, else None. Never raises on bad input."""
    try:
        body, signature = token.split(".")
        expected = _b64(hmac.new(_key(password), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        claims = json.loads(_unb64(body))
        name, expires = claims["n"], claims["e"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(name, str) or not isinstance(expires, int) or expires < now:
        return None
    return name
