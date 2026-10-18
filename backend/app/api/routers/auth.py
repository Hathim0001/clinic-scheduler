"""Staff login: whether it is required, and how to get a token."""

from __future__ import annotations

import hmac
import time

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.errors import ApiError
from app.api.schemas.requests import LoginRequest
from app.core.auth import issue_token
from app.domain.errors import ErrorCode, RuleViolation

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()


class AuthStatus(BaseModel):
    required: bool


class TokenOut(BaseModel):
    token: str
    name: str
    expires_at_epoch: int


@router.get("/status", response_model=AuthStatus, summary="Does this server ask for a staff login?")
def status(request: Request) -> AuthStatus:
    return AuthStatus(required=request.app.state.settings.staff_password is not None)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Exchange the staff password and a name for a token (send it as a Bearer token)",
    responses={401: {"description": "UNAUTHENTICATED: wrong password"}},
)
def login(request: Request, body: LoginRequest) -> TokenOut:
    """The name goes on every audit row the token writes. The password check is constant-time and
    this route is limited to 10 attempts a minute per client."""
    settings = request.app.state.settings
    password = settings.staff_password
    if password is None:
        raise RuleViolation(ErrorCode.VALIDATION_ERROR, "Staff login is not switched on.")
    if not hmac.compare_digest(body.password.encode(), password.encode()):
        log.warning("auth.login_failed")
        raise ApiError(ErrorCode.UNAUTHENTICATED, "The password is not correct.")
    token, expires = issue_token(
        password, body.name, time.time(), settings.auth_token_ttl_hours * 3600
    )
    log.info("auth.login", staff=body.name)
    return TokenOut(token=token, name=body.name, expires_at_epoch=expires)
