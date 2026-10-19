"""The one error shape, and the handlers that turn every failure into it.

Every error body has exactly four keys: code, message, details and request_id. That holds for rule
violations, bad input, unknown routes, wrong methods, oversized bodies, an unreachable database and
the catch-all 500, so a client needs one parser (plan 22.2). Error bodies never repeat what the
client sent: validation errors list the field and the problem, not the value.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from app.core import metrics
from app.domain.errors import DomainError, ErrorCode
from app.persistence.db_errors import is_unavailable

log = structlog.get_logger()

STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.MALFORMED_JSON: 400,
    ErrorCode.INVALID_TEST_CLOCK: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.DOCTOR_NOT_FOUND: 404,
    ErrorCode.PATIENT_NOT_FOUND: 404,
    ErrorCode.APPOINTMENT_NOT_FOUND: 404,
    ErrorCode.REFERENCE_NOT_FOUND: 404,
    ErrorCode.WAITLIST_ENTRY_NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.BOOKING_IN_PAST: 422,
    ErrorCode.BOOKING_TOO_FAR: 422,
    ErrorCode.OFF_GRID: 422,
    ErrorCode.OUTSIDE_AVAILABILITY: 422,
    ErrorCode.DEPOSIT_REQUIRED: 422,
    ErrorCode.RESCHEDULE_NO_CHANGE: 422,
    ErrorCode.WINDOW_OVERLAP: 422,
    ErrorCode.WINDOW_OFF_GRID: 422,
    ErrorCode.DAILY_CAP_REACHED: 409,
    ErrorCode.SLOT_TAKEN: 409,
    ErrorCode.PATIENT_OVERLAP: 409,
    ErrorCode.INVALID_TRANSITION: 409,
    ErrorCode.APPOINTMENT_ALREADY_STARTED: 409,
    ErrorCode.TOO_EARLY_TO_MARK: 409,
    ErrorCode.AVAILABILITY_CONFLICTS: 409,
    ErrorCode.PHONE_TAKEN: 409,
    ErrorCode.PATIENT_HAS_UPCOMING: 409,
    ErrorCode.PATIENT_ERASED: 409,
    ErrorCode.STAFF_USERNAME_TAKEN: 409,
    ErrorCode.LAST_ADMIN: 409,
    ErrorCode.STAFF_NOT_FOUND: 404,
    ErrorCode.NOTIFICATION_NOT_FOUND: 404,
    ErrorCode.SLOT_LENGTH_LOCKED: 409,
    ErrorCode.DOCTOR_HAS_APPOINTMENTS: 409,
    ErrorCode.ALREADY_WAITING: 409,
    ErrorCode.OFFER_EXPIRED: 409,
    ErrorCode.DOCTOR_NOT_ACCEPTING: 409,
    ErrorCode.POSSIBLE_DUPLICATE: 409,
    ErrorCode.ALREADY_CHECKED_IN: 409,
    ErrorCode.IDEMPOTENCY_KEY_REUSED: 409,
    ErrorCode.INVALID_CORRECTION: 409,
    ErrorCode.LATE_RESCHEDULE_NEEDS_CONFIRMATION: 409,
    ErrorCode.UNDO_NOT_POSSIBLE: 409,
    ErrorCode.CONFLICT: 409,
    ErrorCode.PRECONDITION_FAILED: 412,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}

_MAX_REPORTED_FIELDS = 20
_MAX_LOC_TEXT = 64  # a hostile client can send a huge key name; do not echo all of it


class ApiError(Exception):
    """An error raised by the HTTP layer itself (the domain has its own, see DomainError)."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


class InvalidTestClock(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_TEST_CLOCK, message)


class ServiceUnavailable(ApiError):
    def __init__(
        self, message: str = "The service is busy or unavailable. Try again shortly."
    ) -> None:
        super().__init__(ErrorCode.SERVICE_UNAVAILABLE, message, headers={"Retry-After": "1"})


def request_id_of(request: Request) -> str:
    return str(getattr(request.state, "request_id", "-"))


def error_response(
    request_id: str,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """The standard error body. The status comes from the catalogue, so it cannot disagree."""
    return JSONResponse(
        {
            "error": {
                "code": code.value,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
        status_code=STATUS_BY_CODE[code],
        headers=headers,
    )


def _log_fields(request: Request) -> dict[str, Any]:
    return dict(getattr(request.state, "log_fields", {}))


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # noqa: S101 - narrows the type for the checker
    status = STATUS_BY_CODE[exc.code]
    metrics.count_rejection(exc.code.value)
    log.warning(
        "request.rejected",
        code=exc.code.value,
        status=status,
        from_database=isinstance(exc.__cause__, DBAPIError),
        **_log_fields(request),
    )
    return error_response(request_id_of(request), exc.code, exc.message, exc.details)


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101
    log.info("request.refused", code=exc.code.value, **_log_fields(request))
    return error_response(request_id_of(request), exc.code, exc.message, exc.details, exc.headers)


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    problems = exc.errors()
    if any(problem["type"] == "json_invalid" for problem in problems):
        log.info("request.refused", code=ErrorCode.MALFORMED_JSON.value, **_log_fields(request))
        return error_response(
            request_id_of(request),
            ErrorCode.MALFORMED_JSON,
            "The request body is not valid JSON.",
        )
    fields = [
        {
            "loc": [str(part)[:_MAX_LOC_TEXT] for part in problem["loc"]],
            "msg": str(problem["msg"])[:200],
            "type": str(problem["type"]),
        }
        for problem in problems[:_MAX_REPORTED_FIELDS]
    ]
    log.info("request.refused", code=ErrorCode.VALIDATION_ERROR.value, **_log_fields(request))
    return error_response(
        request_id_of(request),
        ErrorCode.VALIDATION_ERROR,
        "One or more fields are missing or invalid.",
        {"fields": fields, "total_problems": len(problems)},
    )


_HTTP_STATUS_TO_CODE = {
    400: (ErrorCode.MALFORMED_JSON, "The request body could not be read as JSON."),
    404: (ErrorCode.NOT_FOUND, "There is no such endpoint."),
    405: (ErrorCode.METHOD_NOT_ALLOWED, "That method is not allowed for this endpoint."),
    413: (ErrorCode.PAYLOAD_TOO_LARGE, "The request body is too large."),
}


def _allowed_methods(request: Request) -> list[str]:
    """The methods some route of this app accepts for the path, found by asking the router."""
    allowed = []
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        probe = {**request.scope, "method": method}
        if any(route.matches(probe)[0] == Match.FULL for route in request.app.routes):
            allowed.append(method)
    return allowed


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code, message = _HTTP_STATUS_TO_CODE.get(
        exc.status_code, (ErrorCode.VALIDATION_ERROR, "The request could not be processed.")
    )
    headers = {k: v for k, v in (exc.headers or {}).items() if k.lower() == "allow"}
    if exc.status_code == 405:  # Starlette names one method; list every method of the path
        headers["Allow"] = ", ".join(_allowed_methods(request))
    return error_response(request_id_of(request), code, message, headers=headers or None)


async def database_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """What is left after the services translated the errors a client can cause."""
    assert isinstance(exc, SQLAlchemyError)  # noqa: S101
    if is_unavailable(exc):
        log.error("database.unavailable", error_type=type(exc).__name__, **_log_fields(request))
        error = ServiceUnavailable()
        return error_response(
            request_id_of(request), error.code, error.message, error.details, error.headers
        )
    log.error("database.error", error_type=type(exc).__name__, exc_info=exc, **_log_fields(request))
    return internal_error_response(request_id_of(request))


def internal_error_response(request_id: str) -> JSONResponse:
    """The catch-all 500: a generic message and the request id, nothing else leaks."""
    return error_response(
        request_id,
        ErrorCode.INTERNAL_ERROR,
        "Something went wrong on our side. Quote the request id when reporting it.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
