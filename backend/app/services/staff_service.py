"""Staff accounts: who can sign in, and as what (ADMIN or RECEPTIONIST).

Used only when the server is started with `AUTH_SECRET`; without it the API is open (or protected by
the one shared `STAFF_PASSWORD`), which is what the assignment allows. An administrator manages
accounts and the clinic's set-up (doctors, hours, erasing a patient); a receptionist does the
day-to-day work. The last active administrator cannot be removed, so the clinic cannot lock itself
out.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.passwords import DUMMY_HASH, MIN_LENGTH, hash_password, verify_password
from app.domain.errors import ConflictError, ErrorCode, NotFoundError, RuleViolation
from app.domain.model import Role
from app.persistence.models import StaffAccount
from app.services.support import run


@dataclass(frozen=True, slots=True)
class StaffView:
    id: int
    username: str
    display_name: str
    role: Role
    active: bool


def _view(account: StaffAccount) -> StaffView:
    return StaffView(
        account.id, account.username, account.display_name, Role(account.role), account.active
    )


def _check_password(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise RuleViolation(
            ErrorCode.VALIDATION_ERROR,
            f"The password must be at least {MIN_LENGTH} characters.",
            field="password",
        )


def _get(session: Session, account_id: int, *, lock: bool = False) -> StaffAccount:
    statement = select(StaffAccount).where(StaffAccount.id == account_id)
    account = session.scalars(statement.with_for_update() if lock else statement).one_or_none()
    if account is None:
        raise NotFoundError(
            ErrorCode.STAFF_NOT_FOUND,
            f"There is no staff account {account_id}.",
            staff_id=account_id,
        )
    return account


def _active_admins(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(StaffAccount)
            .where(StaffAccount.role == Role.ADMIN.value, StaffAccount.active.is_(True))
        )
        or 0
    )


class StaffService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list(self) -> list[StaffView]:
        def work(session: Session) -> list[StaffView]:
            rows = session.scalars(select(StaffAccount).order_by(StaffAccount.username))
            return [_view(a) for a in rows]

        return run(self._factory, work)

    def create(self, username: str, display_name: str, password: str, role: Role) -> StaffView:
        _check_password(password)
        hashed = hash_password(password)

        def work(session: Session) -> StaffView:
            taken = session.scalar(
                select(StaffAccount.id).where(StaffAccount.username == username).limit(1)
            )
            if taken is not None:
                raise ConflictError(
                    ErrorCode.STAFF_USERNAME_TAKEN, "That username is already in use."
                )
            account = StaffAccount(
                username=username,
                display_name=display_name,
                password_hash=hashed,
                role=role.value,
            )
            session.add(account)
            session.flush()
            return _view(account)

        return run(self._factory, work)

    def update(
        self,
        account_id: int,
        *,
        role: Role | None = None,
        active: bool | None = None,
        password: str | None = None,
        display_name: str | None = None,
    ) -> StaffView:
        if password is not None:
            _check_password(password)
        hashed = hash_password(password) if password is not None else None

        def work(session: Session) -> StaffView:
            account = _get(session, account_id, lock=True)
            was_admin = account.role == Role.ADMIN.value and account.active
            if role is not None:
                account.role = role.value
            if active is not None:
                account.active = active
            if display_name is not None:
                account.display_name = display_name
            if hashed is not None:
                account.password_hash = hashed
            session.flush()
            lost_admin = was_admin and not (account.role == Role.ADMIN.value and account.active)
            if lost_admin and _active_admins(session) == 0:
                raise ConflictError(
                    ErrorCode.LAST_ADMIN,
                    "This is the last active administrator. Make someone else an administrator "
                    "first, so the clinic cannot lock itself out.",
                    staff_id=account.id,
                )
            return _view(account)

        return run(self._factory, work)

    def authenticate(self, username: str, password: str) -> StaffView | None:
        """The active account whose password matches, else None. A missing user costs as much as a
        wrong password, so response time does not reveal which usernames exist."""

        def work(session: Session) -> StaffView | None:
            account = session.scalars(
                select(StaffAccount).where(StaffAccount.username == username.strip().lower())
            ).one_or_none()
            stored = account.password_hash if account is not None else DUMMY_HASH
            matches = verify_password(password, stored)
            if account is None or not matches or not account.active:
                return None
            return _view(account)

        return run(self._factory, work)

    def current(self, account_id: int) -> StaffView | None:
        """The account as it is now (role and active flag), for checking a token on each request."""

        def work(session: Session) -> StaffView | None:
            account = session.get(StaffAccount, account_id)
            return _view(account) if account is not None and account.active else None

        return run(self._factory, work)
