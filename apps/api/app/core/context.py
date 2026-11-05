"""Who is making this request, and what are they allowed to do. Used by every protected route."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import Access, load_access
from app.core.db import DbSession
from app.modules.auth import repository, service
from app.modules.auth.models import UserSession
from app.modules.roles.models import Role
from app.modules.users.models import User

SESSION_COOKIE = "ar_session"


@dataclass(frozen=True)
class Ctx:
    db: AsyncSession
    user: User
    role: Role  # the primary role, for display
    access: Access
    session: UserSession

    @property
    def permissions(self) -> frozenset[str]:
        """Every permission held anywhere, from any role."""
        return self.access.held()

    def can(self, permission: str) -> bool:
        """Holds this permission somewhere. Data checks then ask access.has(permission, practice)."""
        return permission in self.permissions


async def get_ctx(request: Request, db: DbSession) -> Ctx:
    """Rejects the request with 401 unless it carries a valid, active session."""
    token = request.cookies.get(SESSION_COOKIE)
    active = await service.resume(db, token) if token else None
    if active is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in required.")
    request.state.user_id = active.user.id  # lets refused requests be recorded with who tried
    role = await repository.get_role(db, active.user.role_id)
    access = await load_access(db, active.user.id, role.id)
    return Ctx(db=db, user=active.user, role=role, access=access, session=active.session)


CurrentCtx = Annotated[Ctx, Depends(get_ctx)]


def require(*permissions: str) -> Callable[..., Coroutine[Any, Any, Ctx]]:
    """
    Route dependency: 401 if not signed in, 403 unless the person holds at least one of these permissions
    somewhere. Which records they may touch is then checked per practice, in the module's service.
    """

    async def dependency(ctx: CurrentCtx) -> Ctx:
        if not any(ctx.can(p) for p in permissions):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permission required: {' or '.join(permissions)}")
        return ctx

    return dependency


RECENT_SIGN_IN_MINUTES = 15


def require_recent_sign_in(ctx: Ctx) -> None:
    """Owner-level actions need a fresh sign-in (specification, section 3: strong authentication)."""
    age = datetime.now(UTC) - ctx.session.created_at
    if age > timedelta(minutes=RECENT_SIGN_IN_MINUTES):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "For this change, sign out and sign in again: owner-level changes need a sign-in "
            f"within the last {RECENT_SIGN_IN_MINUTES} minutes.",
        )
