"""A small per-client rate limit: a sliding window of one minute, kept in memory.

It is a guard against a runaway script or a hostile loop, not a billing system: the state lives in
one process, so with several instances each would count on its own. Health checks are exempt. It
sits inside the request-context middleware (the 429 carries a request id) and inside CORS (the
browser can read it).
"""

from __future__ import annotations

import time
from collections import deque

from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import error_response
from app.domain.errors import ErrorCode

WINDOW_SECONDS = 60.0
EXEMPT_PATHS = frozenset({"/healthz", "/readyz"})
MAX_TRACKED_CLIENTS = 10_000


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, per_minute: int = 600) -> None:
        self.app = app
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = {}

    def _retry_after(self, client: str, now: float) -> int | None:
        """Seconds to wait if `client` is over the limit, else None (and the hit is counted)."""
        window = self._hits.setdefault(client, deque())
        while window and now - window[0] >= WINDOW_SECONDS:
            window.popleft()
        if len(window) >= self.per_minute:
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
        client = (scope.get("client") or ("unknown", 0))[0]
        wait = self._retry_after(client, time.monotonic())
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
