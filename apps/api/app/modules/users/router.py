import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.context import Ctx, require
from app.core.scope import get_scope
from app.modules.users import repository, service
from app.modules.users.schemas import IdList, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

CanView = Annotated[Ctx, Depends(require("users.view"))]
CanManage = Annotated[Ctx, Depends(require("users.manage"))]


@router.get("", response_model=list[UserOut])
async def list_users(
    ctx: CanView,
    status_filter: Annotated[Literal["active", "paused", "deactivated"] | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[UserOut]:
    """Employees within the caller's scope (everyone, for System Administrators and Management)."""
    scope = await get_scope(ctx)
    users = await repository.list_users(ctx.db, scope, ctx.user.id, status=status_filter, search=q)
    return await service.to_out(ctx, list(users))


@router.get("/{user_id}", response_model=UserOut)
async def get_user(ctx: CanView, user_id: uuid.UUID) -> UserOut:
    user = await repository.get_user(ctx.db, await get_scope(ctx), ctx.user.id, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return (await service.to_out(ctx, [user]))[0]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(ctx: CanManage, body: UserCreate) -> UserOut:
    return await service.create_user(ctx, body)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(ctx: CanManage, user_id: uuid.UUID, body: UserUpdate) -> UserOut:
    return await service.update_user(ctx, user_id, body)


@router.post("/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(ctx: CanManage, user_id: uuid.UUID) -> UserOut:
    """Permanent. Signs the person out everywhere immediately."""
    return await service.deactivate_user(ctx, user_id)


@router.put("/{user_id}/practices", response_model=UserOut)
async def set_practices(ctx: CanManage, user_id: uuid.UUID, body: IdList) -> UserOut:
    return await service.set_practices(ctx, user_id, set(body.ids))


@router.put("/{user_id}/teams", response_model=UserOut)
async def set_teams(ctx: CanManage, user_id: uuid.UUID, body: IdList) -> UserOut:
    return await service.set_teams(ctx, user_id, set(body.ids))
