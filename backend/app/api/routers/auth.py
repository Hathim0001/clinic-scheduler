"""Staff login: whether it is required, and how to get a token."""

from __future__ import annotations

import hmac
import time

import structlog
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.api.deps import NowDep, require_staff
from app.api.errors import ApiError
from app.api.ratelimit import LoginLockout
from app.api.schemas.requests import ChangePasswordRequest, LoginRequest, ResetPasswordRequest
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
    doctor_id: int | None = None  # set for a doctor's own login


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
        lockout: LoginLockout = request.app.state.login_lockout
        who = body.name.strip().lower()
        wait = lockout.retry_after(who, time.time())
        if wait is not None:
            log.warning("auth.login_locked")
            raise ApiError(
                ErrorCode.RATE_LIMITED,
                "Too many wrong passwords for this account. Try again later.",
                {"retry_after_seconds": wait},
                {"Retry-After": str(wait)},
            )
        account = request.app.state.services.staff.authenticate(body.name, body.password)
        if account is not None:
            lockout.succeeded(who)
            token, expires = issue_token(
                secret, account.display_name, time.time(), ttl, account.role.value, account.id
            )
            log.info("auth.login", staff=account.display_name, role=account.role.value)
            return TokenOut(
                token=token,
                name=account.display_name,
                role=account.role.value,
                expires_at_epoch=expires,
                doctor_id=account.doctor_id,
            )
        lockout.failed(who, time.time())
    shared = settings.staff_password
    if shared is not None and hmac.compare_digest(body.password.encode(), shared.encode()):
        if settings.auth_secret is not None:
            request.app.state.login_lockout.succeeded(body.name.strip().lower())
        token, expires = issue_token(secret, body.name, time.time(), ttl, Role.ADMIN.value)
        log.info("auth.login", staff=body.name, role=Role.ADMIN.value)
        return TokenOut(
            token=token, name=body.name, role=Role.ADMIN.value, expires_at_epoch=expires
        )
    log.warning("auth.login_failed")
    raise ApiError(ErrorCode.UNAUTHENTICATED, "The username or password is not correct.")


def _locked(request: Request, key: str) -> None:
    lockout: LoginLockout = request.app.state.login_lockout
    wait = lockout.retry_after(key, time.time())
    if wait is not None:
        raise ApiError(
            ErrorCode.RATE_LIMITED,
            "Too many wrong codes for this account. Try again later.",
            {"retry_after_seconds": wait},
            {"Retry-After": str(wait)},
        )


@router.post(
    "/reset-password",
    status_code=204,
    summary="Choose a new password with the single-use code an administrator gave you",
    responses={401: {"description": "UNAUTHENTICATED: the code is wrong, used or expired"}},
)
def reset_password(request: Request, body: ResetPasswordRequest, now: NowDep) -> Response:
    """Works for accounts only. The code comes from an administrator, is valid for an hour and works
    once; afterwards every older session of that account ends. The answer is the same whether the
    username exists or not, and five wrong codes lock the account's resets for a while."""
    if request.app.state.settings.auth_secret is None:
        raise RuleViolation(ErrorCode.VALIDATION_ERROR, "Staff accounts are not switched on.")
    key = f"reset:{body.username.strip().lower()}"
    _locked(request, key)
    done = request.app.state.services.staff.reset_password(
        body.username, body.code, body.new_password, now
    )
    if done is None:
        request.app.state.login_lockout.failed(key, time.time())
        log.warning("auth.reset_failed")
        raise ApiError(
            ErrorCode.UNAUTHENTICATED,
            "That code is not correct, has already been used or has expired. "
            "Ask an administrator for a new one.",
        )
    request.app.state.login_lockout.succeeded(key)
    log.info("auth.password_reset", staff_id=done.id)
    return Response(status_code=204)


@router.post(
    "/change-password",
    status_code=204,
    summary="Change your own password (other sessions of your account end)",
    dependencies=[Depends(require_staff)],
    responses={401: {"description": "UNAUTHENTICATED: the current password is wrong"}},
)
def change_password(request: Request, body: ChangePasswordRequest, now: NowDep) -> Response:
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        raise RuleViolation(
            ErrorCode.VALIDATION_ERROR,
            "Sign in with your own account to change a password; the shared password is changed "
            "by whoever runs the server.",
        )
    done = request.app.state.services.staff.change_password(
        account_id, body.current_password, body.new_password, now
    )
    if done is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "The current password is not correct.")
    log.info("auth.password_changed", staff_id=done.id)
    return Response(status_code=204)
