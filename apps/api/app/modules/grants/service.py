"""
Additional grants (Roles & Access specification, section 4). A grant gives one person one permission,
everywhere or in one practice, with a reason, grantor, approver, dates and optional expiry.

- Standard grants take effect straight away; the grantor is recorded as the approver.
- Elevated grants (access beyond a practice, user/role/grant administration) wait for a second person
  with grants.approve, and must be confirmed every 90 days.
- Nobody can grant to themselves, approve their own request, or grant a permission they don't hold.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core import audit
from app.core.access import users_with
from app.core.context import Ctx
from app.core.schemas import NamedRef
from app.modules.grants.models import PermissionGrant
from app.modules.grants.schemas import GrantCreate, GrantOut
from app.modules.notifications import service as notify
from app.modules.practices.models import Practice
from app.modules.roles.models import Permission
from app.modules.users.models import User

ELEVATED = frozenset(
    {
        "scope.all_practices",
        "users.manage",
        "users.manage_owners",
        "roles.manage",
        "grants.manage",
        "grants.approve",
        "reports.staff",  # staff-level reports (specification, section 4)
    }
)
REVIEW_EVERY = timedelta(days=90)


def _now() -> datetime:
    return datetime.now(UTC)


def state_of(grant: PermissionGrant) -> str:
    if grant.status == "active" and grant.expires_at is not None and grant.expires_at <= _now():
        return "expired"
    return grant.status


async def _names(ctx: Ctx, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await ctx.db.execute(select(User.id, User.full_name).where(User.id.in_(wanted)))).all())


async def to_out(ctx: Ctx, grants: list[PermissionGrant]) -> list[GrantOut]:
    people = await _names(
        ctx,
        {g.user_id for g in grants}
        | {g.requested_by for g in grants}
        | {g.approved_by for g in grants}
        | {g.ended_by for g in grants},
    )
    practice_ids = {g.practice_id for g in grants if g.practice_id}
    practices = (
        dict(
            (
                await ctx.db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(practice_ids)))
            ).all()
        )
        if practice_ids
        else {}
    )
    descriptions = dict((await ctx.db.execute(select(Permission.key, Permission.description))).all())

    def ref(person: uuid.UUID | None) -> NamedRef | None:
        return NamedRef(id=person, name=people.get(person, "")) if person else None

    now = _now()
    return [
        GrantOut(
            id=g.id,
            person=NamedRef(id=g.user_id, name=people.get(g.user_id, "")),
            permission=g.permission_key,
            permission_description=descriptions.get(g.permission_key, g.permission_key),
            elevated=g.permission_key in ELEVATED,
            practice=NamedRef(id=g.practice_id, name=practices.get(g.practice_id, ""))
            if g.practice_id
            else None,
            reason=g.reason,
            state=state_of(g),
            requested_by=NamedRef(id=g.requested_by, name=people.get(g.requested_by, "")),
            approved_by=ref(g.approved_by),
            created_at=g.created_at,
            decided_at=g.decided_at,
            expires_at=g.expires_at,
            review_due_at=g.review_due_at,
            review_overdue=state_of(g) == "active" and g.review_due_at is not None and g.review_due_at <= now,
            ended_at=g.ended_at,
            ended_by=ref(g.ended_by),
            end_reason=g.end_reason,
            can_approve=g.status == "pending" and _may_approve(ctx, g),
        )
        for g in grants
    ]


def _may_approve(ctx: Ctx, grant: PermissionGrant) -> bool:
    return (
        ctx.can("grants.approve")
        and ctx.user.id not in (grant.requested_by, grant.user_id)
        and _holds(ctx, grant.permission_key, grant.practice_id)
    )


def _holds(ctx: Ctx, permission: str, practice_id: uuid.UUID | None) -> bool:
    """Does the acting person hold this permission at least as widely as it would be granted?"""
    if practice_id is None:
        return permission in ctx.access.everywhere
    return ctx.access.has(permission, practice_id)


def _may_manage(ctx: Ctx, practice_id: uuid.UUID | None) -> bool:
    """Everywhere-grants need access to every practice; one-practice grants need grants.manage there."""
    if practice_id is None:
        return ctx.access.all_practices and "grants.manage" in ctx.access.everywhere
    return ctx.access.has("grants.manage", practice_id)


def _label(grant: PermissionGrant, description: str, practice: str | None) -> str:
    return f"{description} ({'in ' + practice if practice else 'in all their practices'})"


async def _load(ctx: Ctx, grant_id: int) -> PermissionGrant:
    grant = await ctx.db.get(PermissionGrant, grant_id)
    if grant is None or not (_may_manage(ctx, grant.practice_id) or ctx.can("grants.approve")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grant not found.")
    return grant


async def _describe(ctx: Ctx, grant: PermissionGrant) -> tuple[str, str, str | None]:
    person = await ctx.db.get(User, grant.user_id)
    description = await ctx.db.scalar(
        select(Permission.description).where(Permission.key == grant.permission_key)
    )
    practice = await ctx.db.get(Practice, grant.practice_id) if grant.practice_id else None
    return (
        person.full_name if person else "someone",
        description or grant.permission_key,
        practice.name if practice else None,
    )


def _record(ctx: Ctx, action: str, grant: PermissionGrant, **after: object) -> None:
    audit.record(
        ctx.db,
        action=action,
        entity_type="grant",
        entity_id=str(grant.id),
        actor_user_id=ctx.user.id,
        practice_id=grant.practice_id,
        after={
            "user_id": str(grant.user_id),
            "permission": grant.permission_key,
            "practice_id": str(grant.practice_id) if grant.practice_id else None,
            **after,
        },
    )


async def create(ctx: Ctx, body: GrantCreate) -> GrantOut:
    if body.user_id == ctx.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't give yourself a permission.")
    person = await ctx.db.get(User, body.user_id)
    if person is None or person.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Grants can only be given to active people.")
    if person.client_org_id is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Client accounts can't be given internal permissions."
        )
    if await ctx.db.scalar(select(Permission.key).where(Permission.key == body.permission)) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown permission.")
    if body.practice_id is not None and await ctx.db.get(Practice, body.practice_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Practice does not exist.")
    if body.permission == "scope.all_practices" and body.practice_id is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Access to every practice can't be limited to one practice."
        )
    if not _may_manage(ctx, body.practice_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't give permissions there.")
    if not _holds(ctx, body.permission, body.practice_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only give permissions you hold yourself.")
    expires_at = datetime.combine(body.expires_on, time.max, tzinfo=UTC) if body.expires_on else None
    if expires_at is not None and expires_at <= _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The end date must be in the future.")

    elevated = body.permission in ELEVATED
    now = _now()
    grant = PermissionGrant(
        user_id=body.user_id,
        permission_key=body.permission,
        practice_id=body.practice_id,
        reason=body.reason,
        status="pending" if elevated else "active",
        requested_by=ctx.user.id,
        approved_by=None if elevated else ctx.user.id,
        decided_at=None if elevated else now,
        expires_at=expires_at,
    )
    ctx.db.add(grant)
    await ctx.db.flush()
    name, description, practice = await _describe(ctx, grant)
    label = _label(grant, description, practice)
    if elevated:
        _record(ctx, "grant.requested", grant, reason=body.reason)
        approvers = await users_with(ctx.db, "grants.approve")
        notify.send(
            ctx.db,
            approvers - {grant.user_id},
            kind="grant.requested",
            title=f"{ctx.user.full_name} asks to give {name}: {description}",
            body=f"Needs your approval. Reason: {body.reason}",
            link="/admin/users?view=grants",
            actor=ctx.user.id,
        )
    else:
        _record(ctx, "grant.given", grant, reason=body.reason)
        notify.send(
            ctx.db, {grant.user_id}, kind="grant.given", title=f"You were given: {label}", actor=ctx.user.id
        )
        notify.send(
            ctx.db,
            await notify.oversight(ctx.db),
            kind="grant.given",
            title=f"{ctx.user.full_name} gave {name}: {label}",
            link="/admin/users?view=grants",
            actor=ctx.user.id,
        )
    await ctx.db.commit()
    await ctx.db.refresh(grant)
    return (await to_out(ctx, [grant]))[0]


async def decide(ctx: Ctx, grant_id: int, approve: bool, reason: str | None) -> GrantOut:
    grant = await _load(ctx, grant_id)
    if grant.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This grant has already been decided.")
    if not _may_approve(ctx, grant):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "A second person who holds this permission must approve it (not the requester or the recipient).",
        )
    now = _now()
    grant.decided_at = now
    name, description, practice = await _describe(ctx, grant)
    label = _label(grant, description, practice)
    if approve:
        grant.status, grant.approved_by, grant.review_due_at = "active", ctx.user.id, now + REVIEW_EVERY
        _record(ctx, "grant.approved", grant)
        notify.send(
            ctx.db, {grant.user_id}, kind="grant.given", title=f"You were given: {label}", actor=ctx.user.id
        )
        notify.send(
            ctx.db,
            {grant.requested_by},
            kind="grant.approved",
            title=f"{ctx.user.full_name} approved {description} for {name}",
            link="/admin/users?view=grants",
            actor=ctx.user.id,
        )
    else:
        grant.status, grant.ended_at, grant.ended_by, grant.end_reason = "rejected", now, ctx.user.id, reason
        _record(ctx, "grant.rejected", grant, reason=reason)
        notify.send(
            ctx.db,
            {grant.requested_by},
            kind="grant.rejected",
            title=f"{ctx.user.full_name} turned down {description} for {name}",
            body=reason,
            link="/admin/users?view=grants",
            actor=ctx.user.id,
        )
    await ctx.db.commit()
    await ctx.db.refresh(grant)
    return (await to_out(ctx, [grant]))[0]


async def revoke(ctx: Ctx, grant_id: int, reason: str | None) -> GrantOut:
    grant = await _load(ctx, grant_id)
    if not _may_manage(ctx, grant.practice_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't end grants there.")
    if grant.status not in ("pending", "active"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This grant has already ended.")
    grant.status, grant.ended_at, grant.ended_by, grant.end_reason = "revoked", _now(), ctx.user.id, reason
    _record(ctx, "grant.revoked", grant, reason=reason)
    _, description, practice = await _describe(ctx, grant)
    notify.send(
        ctx.db,
        {grant.user_id},
        kind="grant.revoked",
        title=f"No longer given: {_label(grant, description, practice)}",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(grant)
    return (await to_out(ctx, [grant]))[0]


async def confirm_review(ctx: Ctx, grant_id: int) -> GrantOut:
    """Periodic review of an elevated grant: still needed, so it stays for another 90 days."""
    grant = await _load(ctx, grant_id)
    if state_of(grant) != "active" or grant.review_due_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only active elevated grants are reviewed.")
    if not _may_approve(ctx, grant) and not (ctx.can("grants.approve") and ctx.user.id != grant.user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Reviews are done by an approver other than the recipient."
        )
    now = _now()
    grant.reviewed_at, grant.reviewed_by, grant.review_due_at = now, ctx.user.id, now + REVIEW_EVERY
    _record(ctx, "grant.reviewed", grant)
    await ctx.db.commit()
    await ctx.db.refresh(grant)
    return (await to_out(ctx, [grant]))[0]
