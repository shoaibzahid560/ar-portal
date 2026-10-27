"""Rules for managing employees. Every change is audited in the same transaction."""

import uuid

from fastapi import HTTPException, status

from app.core import audit
from app.core.context import Ctx
from app.core.schemas import RoleRef
from app.core.scope import Scope, get_scope, require_within_scope
from app.modules.users import repository
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserOut, UserUpdate


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


async def to_out(ctx: Ctx, users: list[User]) -> list[UserOut]:
    ids = [u.id for u in users]
    roles = await repository.roles_by_id(ctx.db)
    practices = await repository.practices_for(ctx.db, ids)
    teams = await repository.teams_for(ctx.db, ids)
    return [
        UserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            employee_code=u.employee_code,
            phone=u.phone,
            status=u.status,
            role=RoleRef(key=roles[u.role_id].key, name=roles[u.role_id].name),
            practices=practices.get(u.id, []),
            teams=teams.get(u.id, []),
            last_login_at=u.last_login_at,
            created_at=u.created_at,
        )
        for u in users
    ]


async def _load(ctx: Ctx, scope: Scope, user_id: uuid.UUID) -> User:
    user = await repository.get_user(ctx.db, scope, ctx.user.id, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return user


async def _check_assignments(
    ctx: Ctx, scope: Scope, practice_ids: set[uuid.UUID], team_ids: set[uuid.UUID]
) -> None:
    if practice_ids - await repository.existing_practice_ids(ctx.db, practice_ids):
        raise _bad_request("One or more practices do not exist.")
    if team_ids - await repository.existing_team_ids(ctx.db, team_ids):
        raise _bad_request("One or more teams do not exist.")
    require_within_scope(scope, practice_ids=practice_ids, team_ids=team_ids)


async def _guard_last_admin(ctx: Ctx, user: User) -> None:
    roles = await repository.roles_by_id(ctx.db)
    if (
        roles[user.role_id].key == "system_admin"
        and await repository.count_active_admins(ctx.db, excluding=user.id) == 0
    ):
        raise _bad_request("This is the last active System Administrator. Add another one first.")


async def create_user(ctx: Ctx, body: UserCreate) -> UserOut:
    scope = await get_scope(ctx)
    role = await repository.get_role_by_key(ctx.db, body.role_key)
    if role is None:
        raise _bad_request("Unknown role.")
    if await repository.email_exists(ctx.db, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists.")
    if body.employee_code and await repository.employee_code_exists(ctx.db, body.employee_code):
        raise HTTPException(status.HTTP_409_CONFLICT, "This employee code is already in use.")
    practice_ids, team_ids = set(body.practice_ids), set(body.team_ids)
    await _check_assignments(ctx, scope, practice_ids, team_ids)

    user = User(
        email=body.email,
        full_name=body.full_name,
        employee_code=body.employee_code,
        phone=body.phone,
        role_id=role.id,
        status="active",
    )
    ctx.db.add(user)
    await ctx.db.flush()
    await repository.replace_practices(ctx.db, user.id, practice_ids)
    await repository.replace_teams(ctx.db, user.id, team_ids)
    audit.record(
        ctx.db,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=ctx.user.id,
        after={
            "email": user.email,
            "full_name": user.full_name,
            "employee_code": user.employee_code,
            "role": role.key,
            "practice_ids": sorted(map(str, practice_ids)),
            "team_ids": sorted(map(str, team_ids)),
        },
    )
    await ctx.db.commit()
    await ctx.db.refresh(user)
    return (await to_out(ctx, [user]))[0]


async def update_user(ctx: Ctx, user_id: uuid.UUID, body: UserUpdate) -> UserOut:
    scope = await get_scope(ctx)
    user = await _load(ctx, scope, user_id)
    sent = body.model_fields_set
    roles = await repository.roles_by_id(ctx.db)
    before: dict[str, object] = {}
    after: dict[str, object] = {}

    def change(field: str, old: object, new: object) -> None:
        if old != new:
            before[field], after[field] = old, new

    if "role_key" in sent or "status" in sent:
        if user.id == ctx.user.id:
            raise _bad_request("You can't change your own role or status.")
    if "full_name" in sent and body.full_name is not None:
        change("full_name", user.full_name, body.full_name)
        user.full_name = body.full_name
    if "employee_code" in sent:
        if body.employee_code and await repository.employee_code_exists(
            ctx.db, body.employee_code, except_user=user.id
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "This employee code is already in use.")
        change("employee_code", user.employee_code, body.employee_code)
        user.employee_code = body.employee_code
    if "phone" in sent:
        change("phone", user.phone, body.phone)
        user.phone = body.phone
    if "role_key" in sent and body.role_key is not None:
        role = await repository.get_role_by_key(ctx.db, body.role_key)
        if role is None:
            raise _bad_request("Unknown role.")
        if role.id != user.role_id:
            await _guard_last_admin(ctx, user)
            change("role", roles[user.role_id].key, role.key)
            user.role_id = role.id
    if "status" in sent and body.status is not None and body.status != user.status:
        if user.status == "deactivated":
            raise _bad_request("Deactivated accounts stay deactivated. Create a new account if needed.")
        if body.status != "active":
            await _guard_last_admin(ctx, user)
        change("status", user.status, body.status)
        user.status = body.status

    if after:
        audit.record(
            ctx.db,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=ctx.user.id,
            before=before,
            after=after,
        )
    await ctx.db.commit()
    await ctx.db.refresh(user)
    return (await to_out(ctx, [user]))[0]


async def deactivate_user(ctx: Ctx, user_id: uuid.UUID) -> UserOut:
    scope = await get_scope(ctx)
    user = await _load(ctx, scope, user_id)
    if user.id == ctx.user.id:
        raise _bad_request("You can't deactivate your own account.")
    if user.status != "deactivated":
        await _guard_last_admin(ctx, user)
        audit.record(
            ctx.db,
            action="user.deactivated",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=ctx.user.id,
            before={"status": user.status},
            after={"status": "deactivated"},
        )
        user.status = "deactivated"
        await repository.revoke_all_sessions(ctx.db, user.id)
        await ctx.db.commit()
        await ctx.db.refresh(user)
    return (await to_out(ctx, [user]))[0]


async def set_practices(ctx: Ctx, user_id: uuid.UUID, practice_ids: set[uuid.UUID]) -> UserOut:
    scope = await get_scope(ctx)
    user = await _load(ctx, scope, user_id)
    await _check_assignments(ctx, scope, practice_ids, set())
    current = {ref.id for ref in (await repository.practices_for(ctx.db, [user.id])).get(user.id, [])}
    # Someone with limited scope may only change practices inside their scope; the rest stay as they are.
    require_within_scope(scope, practice_ids=current ^ practice_ids)
    if current != practice_ids:
        await repository.replace_practices(ctx.db, user.id, practice_ids)
        audit.record(
            ctx.db,
            action="user.practices_changed",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=ctx.user.id,
            before={"practice_ids": sorted(map(str, current))},
            after={"practice_ids": sorted(map(str, practice_ids))},
        )
        await ctx.db.commit()
    return (await to_out(ctx, [user]))[0]


async def set_teams(ctx: Ctx, user_id: uuid.UUID, team_ids: set[uuid.UUID]) -> UserOut:
    scope = await get_scope(ctx)
    user = await _load(ctx, scope, user_id)
    await _check_assignments(ctx, scope, set(), team_ids)
    current = {ref.id for ref in (await repository.teams_for(ctx.db, [user.id])).get(user.id, [])}
    require_within_scope(scope, team_ids=current ^ team_ids)
    if current != team_ids:
        await repository.replace_teams(ctx.db, user.id, team_ids)
        audit.record(
            ctx.db,
            action="user.teams_changed",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=ctx.user.id,
            before={"team_ids": sorted(map(str, current))},
            after={"team_ids": sorted(map(str, team_ids))},
        )
        await ctx.db.commit()
    return (await to_out(ctx, [user]))[0]
