"""The request-context middleware: one place that every request passes through.

For each request it
- takes the caller's X-Request-ID if it looks safe, otherwise makes a new one, and returns it in the
  response header and every error body (a hostile id is never reflected into logs or responses);
- refuses a body over 64 KiB before the application reads it;
- writes one JSON access log line (method, path, status, duration; never bodies or query strings);
- turns any exception nobody handled into the standard 500 body.

It is a plain ASGI middleware, not Starlette's BaseHTTPMiddleware, so it does not interfere with
streaming bodies or context variables. It sits inside the CORS middleware: a response produced
here still gets its Access-Control-Allow-Origin header, which an exception handler registered for
`Exception` would not (plan 22.6).
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

import structlog
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response, internal_error_response
from app.domain.errors import ErrorCode

log = structlog.get_logger()

MAX_BODY_BYTES = 64 * 1024
_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_QUIET_PATHS = frozenset({"/healthz"})
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")

# Sent on every response. The API only returns JSON (plus an .ics file), so the page policy is the
# strictest possible; the interactive docs load scripts and are exempt from it. Patient data must
# never be kept by a browser or a shared cache, hence no-store.
_SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"strict-transport-security", b"max-age=63072000; includeSubDomains"),
)
_API_POLICY = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return str(value.decode("latin-1"))
    return None


def _request_id(scope: Scope) -> str:
    supplied = _header(scope, b"x-request-id")
    if supplied is not None and _REQUEST_ID.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex


def _security_headers(path: str, existing: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """The protective headers a response does not already carry."""
    present = {key for key, _ in existing}
    wanted = list(_SECURITY_HEADERS)
    if not path.startswith(_DOC_PATHS):
        wanted.append(_API_POLICY)
    return [(key, value) for key, value in wanted if key not in present]


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_id = _request_id(scope)
        state: dict[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["log_fields"] = {}
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        outcome = {"status": 500, "started": False}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                outcome["status"] = message["status"]
                outcome["started"] = True
                headers = [(k, v) for k, v in message.get("headers", []) if k != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                headers.extend(_security_headers(scope["path"], headers))
                message = {**message, "headers": headers}
            await send(message)

        received = 0

        async def guarded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    # FastAPI re-raises an HTTPException from body parsing unchanged, so this
                    # reaches the handler that answers 413 in the standard error shape.
                    raise StarletteHTTPException(status_code=413)
            return message

        declared = _header(scope, b"content-length")
        too_big = (
            declared is not None and declared.isdigit() and int(declared) > self.max_body_bytes
        )
        try:
            if too_big:  # refuse without reading a byte of it
                response = error_response(
                    request_id,
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    f"The request body is larger than {self.max_body_bytes // 1024} KiB.",
                )
                await response(scope, receive, send_with_id)
            else:
                await self.app(scope, guarded_receive, send_with_id)
        except Exception as exc:
            log.error(
                "request.failed", error_type=type(exc).__name__, exc_info=exc, **state["log_fields"]
            )
            if not outcome["started"]:
                await internal_error_response(request_id)(scope, receive, send_with_id)
        finally:
            fields = {k: v for k, v in state["log_fields"].items() if v is not None}
            if "effective_now" in state:
                fields["effective_now"] = state["effective_now"]
            emit = log.debug if scope["path"] in _QUIET_PATHS else log.info
            emit(
                "request",
                method=scope["method"],
                path=scope["path"],
                status=outcome["status"],
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                **fields,
            )
