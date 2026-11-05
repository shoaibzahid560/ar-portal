from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core.context import Ctx, require
from app.modules.grants import service
from app.modules.grants.models import PermissionGrant
from app.modules.grants.schemas import GrantablePermission, GrantCreate, GrantDecision, GrantOut
from app.modules.roles.models import Permission

router = APIRouter(prefix="/grants", tags=["grants"])

CanSee = Annotated[Ctx, Depends(require("grants.manage", "grants.approve"))]
CanManage = Annotated[Ctx, Depends(require("grants.manage"))]
CanApprove = Annotated[Ctx, Depends(require("grants.approve"))]


@router.get("", response_model=list[GrantOut])
async def list_grants(
    ctx: CanSee,
    show: Literal["current", "pending", "review", "ended", "all"] = "current",
    user_id: Annotated[str | None, Query()] = None,
) -> list[GrantOut]:
    """Grants the caller may manage or approve, newest first."""
    statement = select(PermissionGrant)
    if not ctx.access.all_practices:
        practices = ctx.access.practices_with("grants.manage") or frozenset()
        statement = statement.where(PermissionGrant.practice_id.in_(practices))
    if user_id:
        statement = statement.where(PermissionGrant.user_id == user_id)
    if show == "pending":
        statement = statement.where(PermissionGrant.status == "pending")
    elif show in ("current", "review"):
        statement = statement.where(PermissionGrant.status.in_(("pending", "active")))
    elif show == "ended":
        statement = statement.where(
            or_(PermissionGrant.status.in_(("rejected", "revoked")), PermissionGrant.expires_at.is_not(None))
        )
    grants = await service.to_out(
        ctx, list(await ctx.db.scalars(statement.order_by(PermissionGrant.id.desc())))
    )
    if show == "current":
        grants = [g for g in grants if g.state in ("pending", "active")]
    elif show == "review":
        grants = [g for g in grants if g.review_overdue]
    elif show == "ended":
        grants = [g for g in grants if g.state in ("expired", "rejected", "revoked")]
    return grants


@router.get("/permissions", response_model=list[GrantablePermission])
async def grantable(ctx: CanManage) -> list[GrantablePermission]:
    """The permissions the caller holds and could therefore give, marked if they need a second approver."""
    rows = await ctx.db.execute(
        select(Permission.key, Permission.module, Permission.description).order_by(Permission.module)
    )
    return [
        GrantablePermission(key=k, module=m, description=d, elevated=k in service.ELEVATED)
        for k, m, d in rows
        if k in ctx.permissions
    ]


@router.post("", response_model=GrantOut, status_code=201)
async def create_grant(ctx: CanManage, body: GrantCreate) -> GrantOut:
    """Standard permissions take effect now; elevated ones wait for a second person's approval."""
    return await service.create(ctx, body)


@router.post("/{grant_id}/approve", response_model=GrantOut)
async def approve(ctx: CanApprove, grant_id: int) -> GrantOut:
    return await service.decide(ctx, grant_id, approve=True, reason=None)


@router.post("/{grant_id}/reject", response_model=GrantOut)
async def reject(ctx: CanApprove, grant_id: int, body: GrantDecision) -> GrantOut:
    return await service.decide(ctx, grant_id, approve=False, reason=body.reason)


@router.post("/{grant_id}/revoke", response_model=GrantOut)
async def revoke(ctx: CanManage, grant_id: int, body: GrantDecision) -> GrantOut:
    """Ends a grant now. The row stays, with who ended it and why."""
    return await service.revoke(ctx, grant_id, body.reason)


@router.post("/{grant_id}/review", response_model=GrantOut)
async def review(ctx: CanApprove, grant_id: int) -> GrantOut:
    """Confirms an elevated grant is still needed, for another 90 days."""
    return await service.confirm_review(ctx, grant_id)
