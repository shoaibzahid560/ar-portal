from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Ctx, CurrentCtx, require
from app.modules.roles import service
from app.modules.roles.schemas import PermissionKeys, RolesResponse

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=RolesResponse)
async def list_roles(ctx: CurrentCtx) -> RolesResponse:
    """Every role with its permissions, plus the full permission list. Any signed-in person may read it."""
    return await service.matrix(ctx.db)


@router.put("/{role_key}/permissions", response_model=RolesResponse)
async def set_role_permissions(
    ctx: Annotated[Ctx, Depends(require("roles.manage"))], role_key: str, body: PermissionKeys
) -> RolesResponse:
    """Replaces one role's permissions. Takes effect on each person's next request."""
    return await service.set_permissions(ctx, role_key, body.permissions)
