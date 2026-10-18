"""A small per-client rate limit: a sliding window of one minute, kept in memory.

It is a guard against a runaway script or a hostile loop, not a billing system: the state lives in
one process, so with several instances each would count on its own. Health checks are exempt, and
the login route has a much tighter limit of its own so a password cannot be guessed at full speed.
It sits inside the request-context middleware (the 429 carries a request id) and inside CORS (the
browser can read it).

Which address counts as "the client": with no proxy in front, the socket address. Behind
`trusted_proxy_hops` proxies, the X-Forwarded-For entry that many places from the right. A caller
can write anything on the left of that header, so reading the left-most entry (the usual default)
would let a hostile client dodge the limit by changing it on every request.
"""

from __future__ import annotations

import time
from collections import deque

from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import error_response
from app.domain.errors import ErrorCode

WINDOW_SECONDS = 60.0
EXEMPT_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})
MAX_TRACKED_CLIENTS = 10_000
LOGIN_PATH = "/api/v1/auth/login"
LOGIN_PER_MINUTE = 10


def client_address(scope: Scope, trusted_proxy_hops: int) -> str:
    """The address to count a request against (see the module note on proxies)."""
    socket_address = (scope.get("client") or ("unknown", 0))[0]
    if trusted_proxy_hops <= 0:
        return str(socket_address)
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            entries = [part.strip() for part in value.decode("latin-1").split(",") if part.strip()]
            if len(entries) >= trusted_proxy_hops:
                return str(entries[-trusted_proxy_hops])
            break
    return str(socket_address)


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, per_minute: int = 600, trusted_proxy_hops: int = 0) -> None:
        self.app = app
        self.per_minute = per_minute
        self.trusted_proxy_hops = trusted_proxy_hops
        self._hits: dict[str, deque[float]] = {}

    def _retry_after(self, client: str, now: float, limit: int) -> int | None:
        """Seconds to wait if `client` is over `limit`, else None (and the hit is counted)."""
        window = self._hits.setdefault(client, deque())
        while window and now - window[0] >= WINDOW_SECONDS:
            window.popleft()
        if len(window) >= limit:
            return max(1, int(WINDOW_SECONDS - (now - window[0])) + 1)
        window.append(now)
        if len(self._hits) > MAX_TRACKED_CLIENTS:  # forget clients that have gone quiet
            for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= WINDOW_SECONDS]:
                del self._hits[key]
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.per_minute == 0 or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        if scope["method"] == "OPTIONS":  # preflights are not API calls
            await self.app(scope, receive, send)
            return
        client = client_address(scope, self.trusted_proxy_hops)
        if scope["path"] == LOGIN_PATH:  # its own bucket, with its own much lower limit
            wait = self._retry_after(f"login:{client}", time.monotonic(), LOGIN_PER_MINUTE)
        else:
            wait = self._retry_after(client, time.monotonic(), self.per_minute)
        if wait is None:
            await self.app(scope, receive, send)
            return
        response = error_response(
            str(scope.get("state", {}).get("request_id", "-")),
            ErrorCode.RATE_LIMITED,
            f"Too many requests. Try again in {wait} seconds.",
            {"retry_after_seconds": wait},
            {"Retry-After": str(wait)},
        )
        await response(scope, receive, send)
