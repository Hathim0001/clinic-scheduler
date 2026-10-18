"""Password hashing for staff accounts, with the standard library's scrypt.

A stored hash is `scrypt$n$r$p$salt$digest` (salt and digest in hex), so the cost can rise later
and old hashes still verify. Comparison is constant-time. Nothing here ever logs or returns a
password.
"""

from __future__ import annotations

import hashlib
import hmac
import os

_N, _R, _P, _LENGTH = 2**14, 8, 1, 32
MIN_LENGTH = 8


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_LENGTH)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True when `password` matches `stored`; False for a wrong password or an unreadable hash."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(digest) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


# Verified when a username does not exist, so a missing user costs the same as a wrong password and
# the response time does not reveal which usernames are real.
DUMMY_HASH = hash_password("not-a-real-account-password")
