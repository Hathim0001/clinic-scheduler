"""Staff accounts: who can sign in, and as what (ADMIN, RECEPTIONIST or DOCTOR).

Used only when sign-in is on with individual accounts (`AUTH_SECRET`). An administrator manages
accounts and the clinic's set-up (doctors, hours, rules, erasing a patient); a receptionist does the
day-to-day work; a doctor sees the schedule and marks their own visits. The last active
administrator cannot be removed, so the clinic cannot lock itself out.

A forgotten password is handled without email: an administrator issues a single-use code (valid for
an hour, stored only as a hash) and the person chooses a new password with it. Changing or resetting
a password stamps the account, and any token issued before the stamp stops working.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.passwords import DUMMY_HASH, MIN_LENGTH, hash_password, verify_password
from app.domain.errors import ConflictError, ErrorCode, NotFoundError, RuleViolation
from app.domain.model import Role
from app.persistence import repositories as repo
from app.persistence.models import StaffAccount
from app.services.support import run

RESET_CODE_LIFETIME = timedelta(hours=1)
# No 0/O/1/I/L: a code read aloud over the phone or copied by hand is not misread.
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


@dataclass(frozen=True, slots=True)
class StaffView:
    id: int
    username: str
    display_name: str
    role: Role
    active: bool
    doctor_id: int | None = None
    password_changed_ms: int = 0  # tokens issued before this moment are no longer valid


@dataclass(frozen=True, slots=True)
class ResetCode:
    code: str  # shown once, to the administrator who asked for it
    expires_at: datetime


def _view(account: StaffAccount) -> StaffView:
    return StaffView(
        account.id,
        account.username,
        account.display_name,
        Role(account.role),
        account.active,
        account.doctor_id,
        int(account.password_changed_at.timestamp() * 1000),
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


def _doctor_for(session: Session, role: Role, doctor_id: int | None) -> int | None:
    """A doctor account must name an existing doctor; any other role must not."""
    if role is Role.DOCTOR:
        if doctor_id is None:
            raise RuleViolation(
                ErrorCode.VALIDATION_ERROR,
                "A doctor account must say which doctor it belongs to.",
                field="doctor_id",
            )
        repo.get_doctor(session, doctor_id)  # DOCTOR_NOT_FOUND when there is none
        return doctor_id
    if doctor_id is not None:
        raise RuleViolation(
            ErrorCode.VALIDATION_ERROR,
            "Only a doctor account belongs to a doctor.",
            field="doctor_id",
        )
    return None


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()


def new_reset_code() -> str:
    """Eight characters in two groups of four, for example `K7QX-92MD`."""
    chars = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    return f"{chars[:4]}-{chars[4:]}"


class StaffService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list(self) -> list[StaffView]:
        def work(session: Session) -> list[StaffView]:
            rows = session.scalars(select(StaffAccount).order_by(StaffAccount.username))
            return [_view(a) for a in rows]

        return run(self._factory, work)

    def create(
        self,
        username: str,
        display_name: str,
        password: str,
        role: Role,
        doctor_id: int | None = None,
    ) -> StaffView:
        _check_password(password)
        hashed = hash_password(password)

        def work(session: Session) -> StaffView:
            belongs_to = _doctor_for(session, role, doctor_id)
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
                doctor_id=belongs_to,
                password_changed_at=datetime.now(UTC),
            )
            session.add(account)
            session.flush()
            return _view(account)

        return run(self._factory, work)

    def bootstrap_admin(self, username: str, password: str) -> bool:
        """Create the first administrator from the environment when no account exists yet.

        Returns True when it created one. It does nothing once any account exists, so a changed
        or removed environment variable never alters a clinic that is already set up."""
        _check_password(password)
        hashed = hash_password(password)

        def work(session: Session) -> bool:
            if session.scalar(select(func.count()).select_from(StaffAccount)):
                return False
            session.add(
                StaffAccount(
                    username=username.strip().lower(),
                    display_name=username.strip().title() or "Administrator",
                    password_hash=hashed,
                    role=Role.ADMIN.value,
                    password_changed_at=datetime.now(UTC),
                )
            )
            return True

        return run(self._factory, work)

    def update(
        self,
        account_id: int,
        now: datetime,
        *,
        role: Role | None = None,
        active: bool | None = None,
        password: str | None = None,
        display_name: str | None = None,
        doctor_id: int | None = None,
        doctor_id_given: bool = False,
    ) -> StaffView:
        if password is not None:
            _check_password(password)
        hashed = hash_password(password) if password is not None else None

        def work(session: Session) -> StaffView:
            account = _get(session, account_id, lock=True)
            was_admin = account.role == Role.ADMIN.value and account.active
            new_role = role if role is not None else Role(account.role)
            wanted = doctor_id if doctor_id_given else account.doctor_id
            account.doctor_id = _doctor_for(session, new_role, wanted)
            account.role = new_role.value
            if active is not None:
                account.active = active
            if display_name is not None:
                account.display_name = display_name
            if hashed is not None:
                account.password_hash = hashed
                account.password_changed_at = datetime.now(UTC)
                account.reset_code_hash = account.reset_expires_at = None
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

    # ----------------------------------------------------------------------- password changes

    def issue_reset_code(self, account_id: int, now: datetime) -> ResetCode:
        """A single-use code for this account, valid for an hour; a new one replaces any old one."""
        code = new_reset_code()

        def work(session: Session) -> ResetCode:
            account = _get(session, account_id, lock=True)
            expires = now + RESET_CODE_LIFETIME
            account.reset_code_hash = _code_hash(code)
            account.reset_expires_at = expires
            return ResetCode(code, expires)

        return run(self._factory, work)

    def reset_password(
        self, username: str, code: str, new_password: str, now: datetime
    ) -> StaffView | None:
        """Set a new password with a valid, unexpired, unused code; None when the code does not fit.

        The code is cleared on success, so it works once, and the account's other sessions end."""
        _check_password(new_password)
        hashed = hash_password(new_password)

        def work(session: Session) -> StaffView | None:
            account = session.scalars(
                select(StaffAccount)
                .where(StaffAccount.username == username.strip().lower())
                .with_for_update()
            ).one_or_none()
            if (
                account is None
                or not account.active
                or account.reset_code_hash is None
                or account.reset_expires_at is None
                or account.reset_expires_at < now
                or not hmac.compare_digest(account.reset_code_hash, _code_hash(code))
            ):
                return None
            account.password_hash = hashed
            account.password_changed_at = datetime.now(UTC)
            account.reset_code_hash = account.reset_expires_at = None
            session.flush()
            return _view(account)

        return run(self._factory, work)

    def change_password(
        self, account_id: int, current: str, new_password: str, now: datetime
    ) -> StaffView | None:
        """Change your own password; None when `current` is wrong."""
        _check_password(new_password)
        hashed = hash_password(new_password)

        def work(session: Session) -> StaffView | None:
            account = _get(session, account_id, lock=True)
            if not verify_password(current, account.password_hash):
                return None
            account.password_hash = hashed
            account.password_changed_at = datetime.now(UTC)
            account.reset_code_hash = account.reset_expires_at = None
            session.flush()
            return _view(account)

        return run(self._factory, work)


def deactivate_for_doctor(session: Session, doctor_id: int) -> None:
    """A deleted doctor's login stops working (it keeps its name, so it can be reviewed)."""
    session.execute(
        update(StaffAccount).where(StaffAccount.doctor_id == doctor_id).values(active=False)
    )
