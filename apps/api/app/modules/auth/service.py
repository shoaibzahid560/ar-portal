"""Sign-in rules: who may sign in, how long a session lasts, and what gets audited."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.modules.auth import repository
from app.modules.auth.google import GoogleIdentity
from app.modules.auth.models import UserSession
from app.modules.notifications import service as notify
from app.modules.users.models import User

IDLE_TIMEOUT = timedelta(minutes=30)
ABSOLUTE_LIFETIME = timedelta(hours=12)
LAST_SEEN_WRITE_INTERVAL = timedelta(minutes=1)


class DenialReason(StrEnum):
    """Shown to the person on the login page as ?error=<value>."""

    DOMAIN = "domain"
    NOT_REGISTERED = "not_registered"


@dataclass(frozen=True)
class ActiveSession:
    session: UserSession
    user: User


def now() -> datetime:
    return datetime.now(UTC)


async def sign_in(
    db: AsyncSession, identity: GoogleIdentity, *, ip: str | None, user_agent: str | None
) -> tuple[str | None, DenialReason | None]:
    """
    Returns (session token, None) when the person may sign in, or (None, reason) when not.
    Both outcomes are audited. Inactive and unknown accounts get the same answer on purpose.
    """
    settings = get_settings()
    reason: DenialReason | None = None
    if not identity.email_verified:
        reason = DenialReason.DOMAIN
    elif settings.allowed_google_domain and identity.hosted_domain != settings.allowed_google_domain:
        reason = DenialReason.DOMAIN

    user = None if reason else await repository.get_user_by_email(db, identity.email)
    if reason is None and (user is None or user.status != "active"):
        reason = DenialReason.NOT_REGISTERED

    if reason is not None or user is None:
        audit.record(
            db,
            action="auth.login_denied",
            entity_type="auth",
            entity_id=identity.email,
            actor_user_id=user.id if user else None,
            after={"reason": str(reason)},
        )
        notify.send(
            db,
            await notify.oversight(db),
            kind="auth.login_denied",
            title=f"Sign-in refused for {identity.email}",
            body="Not a registered, active account."
            if reason == DenialReason.NOT_REGISTERED
            else "Not a company account.",
            link="/audit?view=access",
        )
        await db.commit()
        return None, reason

    token = new_token()
    started = now()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            last_seen_at=started,
            expires_at=started + ABSOLUTE_LIFETIME,
            ip=ip,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    user.last_login_at = started
    audit.record(db, action="auth.login", entity_type="user", entity_id=user.id, actor_user_id=user.id)
    await db.commit()
    return token, None


async def resume(db: AsyncSession, token: str) -> ActiveSession | None:
    """Checks a session cookie on every request. Returns None if the person must sign in again."""
    found = await repository.get_session_with_user(db, hash_token(token))
    if found is None:
        return None
    session, user = found
    current = now()
    if (
        session.revoked_at is not None
        or session.expires_at <= current
        or session.last_seen_at <= current - IDLE_TIMEOUT
        or user.status != "active"
    ):
        return None
    if current - session.last_seen_at >= LAST_SEEN_WRITE_INTERVAL:
        session.last_seen_at = current
        await db.commit()
    return ActiveSession(session=session, user=user)


async def sign_out(db: AsyncSession, active: ActiveSession) -> None:
    active.session.revoked_at = now()
    audit.record(
        db, action="auth.logout", entity_type="user", entity_id=active.user.id, actor_user_id=active.user.id
    )
    await db.commit()
