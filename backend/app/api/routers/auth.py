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
from app.domain.model import Role

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()


class AuthStatus(BaseModel):
    required: bool
    accounts: bool  # sign in with a username and password of your own (AUTH_SECRET is set)


class TokenOut(BaseModel):
    token: str
    name: str
    role: str
    expires_at_epoch: int


@router.get("/status", response_model=AuthStatus, summary="Does this server ask for a staff login?")
def status(request: Request) -> AuthStatus:
    settings = request.app.state.settings
    return AuthStatus(required=settings.auth_required, accounts=settings.auth_secret is not None)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Sign in and get a token (send it as a Bearer token)",
    responses={401: {"description": "UNAUTHENTICATED: wrong username or password"}},
)
def login(request: Request, body: LoginRequest) -> TokenOut:
    """With individual accounts on, `name` is the username. Otherwise `name` is just a label for the
    audit trail and the password is the shared staff password. The shared password, when also set,
    still signs in as an administrator under whatever name is given, so the first account can be
    created. Checks are constant-time and this route is limited to 10 attempts a minute per client.
    """
    settings = request.app.state.settings
    secret = settings.signing_secret
    if secret is None:
        raise RuleViolation(ErrorCode.VALIDATION_ERROR, "Staff login is not switched on.")
    ttl = settings.auth_token_ttl_hours * 3600

    if settings.auth_secret is not None:
        account = request.app.state.services.staff.authenticate(body.name, body.password)
        if account is not None:
            token, expires = issue_token(
                secret, account.display_name, time.time(), ttl, account.role.value, account.id
            )
            log.info("auth.login", staff=account.display_name, role=account.role.value)
            return TokenOut(
                token=token,
                name=account.display_name,
                role=account.role.value,
                expires_at_epoch=expires,
            )
    shared = settings.staff_password
    if shared is not None and hmac.compare_digest(body.password.encode(), shared.encode()):
        token, expires = issue_token(secret, body.name, time.time(), ttl, Role.ADMIN.value)
        log.info("auth.login", staff=body.name, role=Role.ADMIN.value)
        return TokenOut(
            token=token, name=body.name, role=Role.ADMIN.value, expires_at_epoch=expires
        )
    log.warning("auth.login_failed")
    raise ApiError(ErrorCode.UNAUTHENTICATED, "The username or password is not correct.")
