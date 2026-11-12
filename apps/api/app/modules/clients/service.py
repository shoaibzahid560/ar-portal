"""
Client organisations and client accounts (Roles & Access specification, sections 2-5).

The portal team (clients.manage) creates a client organisation, links the practices it owns, approves the
reports it may run, and adds its accounts. A Client Reporting Admin may add and deactivate their own
organisation's Client Reporting Users only when the portal team has delegated that.

Client accounts are a separate branch: they hold only client roles, never internal roles or grants, and they
reach only their own organisation's practices.
"""

import re
import uuid
from datetime import datetime
from typing import Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select

from app.core import audit
from app.core.context import Ctx
from app.core.schemas import NamedRef, RoleRef
from app.modules.clients.models import ClientOrganisation, ClientOrgPractice, ClientOrgReport
from app.modules.notifications import service as notify
from app.modules.practices.models import Practice, UserPractice
from app.modules.roles.models import Role
from app.modules.users import repository as users_repo
from app.modules.users.models import User

# The client report catalogue: reports that can be approved for clients, all built without internal data.
CLIENT_REPORTS = {
    "statement": "AR statement",
    "aging": "Aging summary",
    "recovery": "Recovery summary",
}
CLIENT_ROLES = ("client_admin", "client_user")


# ---- Shapes ---------------------------------------------------------------------------------------------


def _strip(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Required")
    return value


class ClientOrgIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=2000)
    practice_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    reports: list[Literal["statement", "aging", "recovery"]] = Field(default_factory=list)
    patient_detail: bool = False
    users_delegated: bool = False

    _name = field_validator("name")(_strip)


class ClientOrgUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "paused"] | None = None
    practice_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)
    reports: list[Literal["statement", "aging", "recovery"]] | None = None
    patient_detail: bool | None = None
    users_delegated: bool | None = None


class ClientOrgOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    notes: str
    patient_detail: bool
    users_delegated: bool
    practices: list[NamedRef]
    reports: list[str]
    user_count: int
    created_at: datetime


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL.match(value):
        raise ValueError("Enter a valid email address")
    return value


class ClientUserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    full_name: str = Field(min_length=1, max_length=120)
    role_key: Literal["client_admin", "client_user"]
    practice_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)

    _name = field_validator("full_name")(_strip)
    _email = field_validator("email")(_email)


class ClientUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=120)
    status: Literal["active", "paused"] | None = None
    practice_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)


class ClientUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: RoleRef
    status: str
    practices: list[NamedRef]
    last_login_at: datetime | None


# ---- Organisations (portal team) ------------------------------------------------------------------------


async def _org_out(ctx: Ctx, orgs: list[ClientOrganisation]) -> list[ClientOrgOut]:
    ids = [o.id for o in orgs]
    practices: dict[uuid.UUID, list[NamedRef]] = {i: [] for i in ids}
    for org_id, pid, name in await ctx.db.execute(
        select(ClientOrgPractice.org_id, Practice.id, Practice.name)
        .join(Practice, Practice.id == ClientOrgPractice.practice_id)
        .where(ClientOrgPractice.org_id.in_(ids))
        .order_by(Practice.name)
    ):
        practices[org_id].append(NamedRef(id=pid, name=name))
    reports: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    for org_id, key in await ctx.db.execute(
        select(ClientOrgReport.org_id, ClientOrgReport.report_key).where(ClientOrgReport.org_id.in_(ids))
    ):
        reports[org_id].append(key)
    counts = dict(
        (
            await ctx.db.execute(
                select(User.client_org_id, func.count())
                .where(User.client_org_id.in_(ids), User.status != "deactivated")
                .group_by(User.client_org_id)
            )
        ).all()
    )
    return [
        ClientOrgOut(
            id=o.id,
            name=o.name,
            status=o.status,
            notes=o.notes,
            patient_detail=o.patient_detail,
            users_delegated=o.users_delegated,
            practices=practices[o.id],
            reports=sorted(reports[o.id], key=list(CLIENT_REPORTS).index),
            user_count=counts.get(o.id, 0),
            created_at=o.created_at,
        )
        for o in orgs
    ]


async def list_orgs(ctx: Ctx) -> list[ClientOrgOut]:
    orgs = list(await ctx.db.scalars(select(ClientOrganisation).order_by(ClientOrganisation.name)))
    return await _org_out(ctx, orgs)


async def _load_org(ctx: Ctx, org_id: uuid.UUID) -> ClientOrganisation:
    org = await ctx.db.get(ClientOrganisation, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client organisation not found.")
    return org


async def _check_practices(ctx: Ctx, practice_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    wanted = set(practice_ids)
    found = set(await ctx.db.scalars(select(Practice.id).where(Practice.id.in_(wanted)))) if wanted else set()
    if wanted - found:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more practices do not exist.")
    return wanted


async def _org_snapshot(ctx: Ctx, org: ClientOrganisation) -> dict:
    [out] = await _org_out(ctx, [org])
    return {
        "name": out.name,
        "status": out.status,
        "patient_detail": out.patient_detail,
        "users_delegated": out.users_delegated,
        "practices": [p.name for p in out.practices],
        "reports": [CLIENT_REPORTS[r] for r in out.reports],
    }


async def create_org(ctx: Ctx, body: ClientOrgIn) -> ClientOrgOut:
    if await ctx.db.scalar(
        select(ClientOrganisation.id).where(func.lower(ClientOrganisation.name) == body.name.lower())
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "A client organisation with this name already exists.")
    practices = await _check_practices(ctx, body.practice_ids)
    org = ClientOrganisation(
        name=body.name,
        notes=body.notes,
        patient_detail=body.patient_detail,
        users_delegated=body.users_delegated,
    )
    ctx.db.add(org)
    await ctx.db.flush()
    ctx.db.add_all(ClientOrgPractice(org_id=org.id, practice_id=p) for p in practices)
    ctx.db.add_all(ClientOrgReport(org_id=org.id, report_key=r) for r in set(body.reports))
    await ctx.db.flush()
    audit.record(
        ctx.db,
        action="client.created",
        entity_type="client",
        entity_id=org.id,
        actor_user_id=ctx.user.id,
        after=await _org_snapshot(ctx, org),
    )
    await ctx.db.commit()
    return (await _org_out(ctx, [org]))[0]


async def update_org(ctx: Ctx, org_id: uuid.UUID, body: ClientOrgUpdate) -> ClientOrgOut:
    org = await _load_org(ctx, org_id)
    before = await _org_snapshot(ctx, org)
    sent = body.model_fields_set
    if "name" in sent and body.name:
        name = body.name.strip()
        clash = await ctx.db.scalar(
            select(ClientOrganisation.id).where(
                func.lower(ClientOrganisation.name) == name.lower(), ClientOrganisation.id != org.id
            )
        )
        if clash:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "A client organisation with this name already exists."
            )
        org.name = name
    for field in ("notes", "status", "patient_detail", "users_delegated"):
        if field in sent and getattr(body, field) is not None:
            setattr(org, field, getattr(body, field))
    if body.practice_ids is not None:
        practices = await _check_practices(ctx, body.practice_ids)
        await ctx.db.execute(delete(ClientOrgPractice).where(ClientOrgPractice.org_id == org.id))
        ctx.db.add_all(ClientOrgPractice(org_id=org.id, practice_id=p) for p in practices)
        # Client accounts lose any practice the organisation no longer owns.
        members = select(User.id).where(User.client_org_id == org.id)
        await ctx.db.execute(
            delete(UserPractice).where(
                UserPractice.user_id.in_(members), UserPractice.practice_id.not_in(practices)
            )
        )
    if body.reports is not None:
        await ctx.db.execute(delete(ClientOrgReport).where(ClientOrgReport.org_id == org.id))
        ctx.db.add_all(ClientOrgReport(org_id=org.id, report_key=r) for r in set(body.reports))
    await ctx.db.flush()
    after = await _org_snapshot(ctx, org)
    changed = {k: v for k, v in after.items() if before[k] != v}
    if changed:
        audit.record(
            ctx.db,
            action="client.changed",
            entity_type="client",
            entity_id=org.id,
            actor_user_id=ctx.user.id,
            before={k: before[k] for k in changed},
            after=changed,
        )
        if "patient_detail" in changed or "status" in changed:
            notify.send(
                ctx.db,
                await notify.oversight(ctx.db),
                kind="client.changed",
                title=f"{ctx.user.full_name} changed {org.name}: "
                + ", ".join(
                    {"patient_detail": "patient names in reports", "status": "status"}[k]
                    for k in changed
                    if k in ("patient_detail", "status")
                ),
                link="/admin/clients",
                actor=ctx.user.id,
            )
    if "status" in changed and org.status == "paused":
        for user_id in await ctx.db.scalars(select(User.id).where(User.client_org_id == org.id)):
            await users_repo.revoke_all_sessions(ctx.db, user_id)
    await ctx.db.commit()
    return (await _org_out(ctx, [org]))[0]


# ---- Client accounts (portal team, or a delegated client admin for their own organisation) ---------------


async def client_org_for(ctx: Ctx, org_id: uuid.UUID | None) -> ClientOrganisation:
    """
    The organisation whose accounts this person may manage: any, for the portal team; their own, for a
    Client Reporting Admin the portal team delegated to.
    """
    if ctx.can("clients.manage") and ctx.user.client_org_id is None:
        if org_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a client organisation.")
        return await _load_org(ctx, org_id)
    if ctx.user.client_org_id is None or not ctx.can("client_users.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: client_users.manage")
    if org_id is not None and org_id != ctx.user.client_org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client organisation not found.")
    org = await _load_org(ctx, ctx.user.client_org_id)
    if not org.users_delegated:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "The portal team hasn't given your organisation user management."
        )
    return org


def _portal_team(ctx: Ctx) -> bool:
    return ctx.user.client_org_id is None


async def _org_practices(ctx: Ctx, org: ClientOrganisation) -> set[uuid.UUID]:
    return set(
        await ctx.db.scalars(select(ClientOrgPractice.practice_id).where(ClientOrgPractice.org_id == org.id))
    )


async def _user_out(ctx: Ctx, users: list[User]) -> list[ClientUserOut]:
    roles = {r.id: r for r in await ctx.db.scalars(select(Role))}
    practices = await users_repo.practices_for(ctx.db, [u.id for u in users])
    return [
        ClientUserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=RoleRef(key=roles[u.role_id].key, name=roles[u.role_id].name),
            status=u.status,
            practices=practices.get(u.id, []),
            last_login_at=u.last_login_at,
        )
        for u in users
    ]


async def list_client_users(ctx: Ctx, org_id: uuid.UUID | None) -> list[ClientUserOut]:
    org = await client_org_for(ctx, org_id)
    users = list(
        await ctx.db.scalars(select(User).where(User.client_org_id == org.id).order_by(User.full_name))
    )
    return await _user_out(ctx, users)


async def _client_user(ctx: Ctx, org: ClientOrganisation, user_id: uuid.UUID) -> User:
    user = await ctx.db.get(User, user_id)
    if user is None or user.client_org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client account not found.")
    return user


async def create_client_user(ctx: Ctx, org_id: uuid.UUID | None, body: ClientUserIn) -> ClientUserOut:
    org = await client_org_for(ctx, org_id)
    if body.role_key == "client_admin" and not _portal_team(ctx):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the portal team adds Client Reporting Admins.")
    owned = await _org_practices(ctx, org)
    practices = set(body.practice_ids) or (owned if body.role_key == "client_admin" else set())
    if not practices:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose at least one practice.")
    if practices - owned:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Client accounts can only reach their organisation's practices."
        )
    email = body.email
    if await users_repo.email_exists(ctx.db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Someone with this email already has an account.")
    role_id = await ctx.db.scalar(select(Role.id).where(Role.key == body.role_key))
    user = User(email=email, full_name=body.full_name, role_id=role_id, client_org_id=org.id)
    ctx.db.add(user)
    await ctx.db.flush()
    ctx.db.add_all(UserPractice(user_id=user.id, practice_id=p) for p in practices)
    await ctx.db.flush()
    [out] = await _user_out(ctx, [user])
    audit.record(
        ctx.db,
        action="client.user_created",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=ctx.user.id,
        after={"client": org.name, "role": out.role.name, "practices": [p.name for p in out.practices]},
    )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="client.user_created",
        title=f"{ctx.user.full_name} added {out.role.name} {user.full_name} for {org.name}",
        link="/admin/clients",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    return out


async def update_client_user(
    ctx: Ctx, org_id: uuid.UUID | None, user_id: uuid.UUID, body: ClientUserUpdate
) -> ClientUserOut:
    org = await client_org_for(ctx, org_id)
    user = await _client_user(ctx, org, user_id)
    if not _portal_team(ctx) and (
        user.id == ctx.user.id or user.role_id != await _role_id(ctx, "client_user")
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can change your organisation's Client Reporting Users."
        )
    before = (await _user_out(ctx, [user]))[0]
    if body.full_name:
        user.full_name = body.full_name.strip()
    if body.status:
        user.status = body.status
        if body.status != "active":
            await users_repo.revoke_all_sessions(ctx.db, user.id)
    if body.practice_ids is not None:
        practices = set(body.practice_ids)
        if not practices or practices - await _org_practices(ctx, org):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose practices of this organisation.")
        await ctx.db.execute(delete(UserPractice).where(UserPractice.user_id == user.id))
        ctx.db.add_all(UserPractice(user_id=user.id, practice_id=p) for p in practices)
    await ctx.db.flush()
    after = (await _user_out(ctx, [user]))[0]
    audit.record(
        ctx.db,
        action="client.user_changed",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=ctx.user.id,
        before={
            "name": before.full_name,
            "status": before.status,
            "practices": [p.name for p in before.practices],
        },
        after={
            "name": after.full_name,
            "status": after.status,
            "practices": [p.name for p in after.practices],
        },
    )
    await ctx.db.commit()
    return after


async def deactivate_client_user(ctx: Ctx, org_id: uuid.UUID | None, user_id: uuid.UUID) -> ClientUserOut:
    org = await client_org_for(ctx, org_id)
    user = await _client_user(ctx, org, user_id)
    if user.id == ctx.user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't deactivate your own account.")
    if not _portal_team(ctx) and user.role_id != await _role_id(ctx, "client_user"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can deactivate your organisation's Client Reporting Users."
        )
    user.status = "deactivated"
    await users_repo.revoke_all_sessions(ctx.db, user.id)
    audit.record(
        ctx.db,
        action="client.user_deactivated",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=ctx.user.id,
        after={"client": org.name},
    )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="client.user_deactivated",
        title=f"{ctx.user.full_name} deactivated {user.full_name} ({org.name})",
        link="/admin/clients",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    return (await _user_out(ctx, [user]))[0]


async def _role_id(ctx: Ctx, key: str) -> int:
    return await ctx.db.scalar(select(Role.id).where(Role.key == key))
