"""The role and permission matrix. Editing it is audited and cannot lock out System Administrators."""

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.context import Ctx
from app.modules.notifications import service as notify
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.roles.schemas import PermissionOut, RoleOut, RolesResponse

# Removing these from the System Administrator would leave nobody able to fix the matrix or add users.
ADMIN_REQUIRED = frozenset({"roles.manage", "users.manage", "users.view"})


async def matrix(db: AsyncSession) -> RolesResponse:
    roles = (await db.scalars(select(Role).order_by(Role.id))).all()
    permissions = (await db.scalars(select(Permission).order_by(Permission.module, Permission.key))).all()
    granted: dict[int, list[str]] = defaultdict(list)
    for role_id, key in await db.execute(select(RolePermission.role_id, RolePermission.permission_key)):
        granted[role_id].append(key)
    return RolesResponse(
        roles=[
            RoleOut(
                id=r.id, key=r.key, name=r.name, description=r.description, permissions=sorted(granted[r.id])
            )
            for r in roles
        ],
        permissions=[
            PermissionOut(key=p.key, module=p.module, description=p.description) for p in permissions
        ],
    )


async def set_permissions(ctx: Ctx, role_key: str, keys: list[str]) -> RolesResponse:
    role = await ctx.db.scalar(select(Role).where(Role.key == role_key))
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found.")
    wanted = set(keys)
    known = set(await ctx.db.scalars(select(Permission.key)))
    if wanted - known:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown permissions: {', '.join(sorted(wanted - known))}"
        )
    if role.key == "system_admin" and not ADMIN_REQUIRED <= wanted:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The System Administrator must keep: " + ", ".join(sorted(ADMIN_REQUIRED)),
        )

    current = set(
        await ctx.db.scalars(select(RolePermission.permission_key).where(RolePermission.role_id == role.id))
    )
    if current != wanted:
        await ctx.db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        ctx.db.add_all(RolePermission(role_id=role.id, permission_key=key) for key in wanted)
        audit.record(
            ctx.db,
            action="role.permissions_changed",
            entity_type="role",
            entity_id=role.key,
            actor_user_id=ctx.user.id,
            before={"permissions": sorted(current)},
            after={"permissions": sorted(wanted)},
        )
        added, removed = len(wanted - current), len(current - wanted)
        notify.send(
            ctx.db,
            await notify.oversight(ctx.db),
            kind="role.permissions_changed",
            title=f"{ctx.user.full_name} changed the {role.name} permissions",
            body=f"{added} added, {removed} removed",
            link="/admin/settings?view=roles",
            actor=ctx.user.id,
        )
        await ctx.db.commit()
    return await matrix(ctx.db)
