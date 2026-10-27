"""Who is making this request, and what are they allowed to do. Used by every protected route."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

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
    role: Role
    permissions: frozenset[str]
    session: UserSession

    def can(self, permission: str) -> bool:
        return permission in self.permissions


async def get_ctx(request: Request, db: DbSession) -> Ctx:
    """Rejects the request with 401 unless it carries a valid, active session."""
    token = request.cookies.get(SESSION_COOKIE)
    active = await service.resume(db, token) if token else None
    if active is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in required.")
    role = await repository.get_role(db, active.user.role_id)
    permissions = await repository.get_permission_keys(db, role.id)
    return Ctx(db=db, user=active.user, role=role, permissions=frozenset(permissions), session=active.session)


CurrentCtx = Annotated[Ctx, Depends(get_ctx)]


def require(permission: str) -> Callable[..., Coroutine[Any, Any, Ctx]]:
    """Route dependency: 401 if not signed in, 403 if signed in without this permission."""

    async def dependency(ctx: CurrentCtx) -> Ctx:
        if not ctx.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permission required: {permission}")
        return ctx

    return dependency
