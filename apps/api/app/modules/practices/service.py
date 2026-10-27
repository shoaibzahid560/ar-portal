"""Rules for practices and teams. Every change is audited in the same transaction."""

import uuid

from fastapi import HTTPException, status

from app.core import audit
from app.core.context import Ctx
from app.core.scope import get_scope, require_within_scope
from app.modules.practices import repository
from app.modules.practices.models import Practice, Team
from app.modules.practices.schemas import (
    PracticeCreate,
    PracticeOut,
    PracticeUpdate,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)


async def practices_out(ctx: Ctx, practices: list[Practice]) -> list[PracticeOut]:
    users, teams = await repository.practice_counts(ctx.db, [p.id for p in practices])
    return [
        PracticeOut(
            id=p.id,
            name=p.name,
            status=p.status,
            notes=p.notes,
            user_count=users.get(p.id, 0),
            team_count=teams.get(p.id, 0),
            created_at=p.created_at,
        )
        for p in practices
    ]


async def teams_out(ctx: Ctx, teams: list[Team]) -> list[TeamOut]:
    practice_names = await repository.names_of_practices(
        ctx.db, {t.practice_id for t in teams if t.practice_id}
    )
    manager_names = await repository.names_of_users(
        ctx.db, {t.manager_user_id for t in teams if t.manager_user_id}
    )
    members = await repository.member_counts(ctx.db, [t.id for t in teams])
    return [
        TeamOut(
            id=t.id,
            name=t.name,
            practice_id=t.practice_id,
            practice_name=practice_names.get(t.practice_id) if t.practice_id else None,
            manager_user_id=t.manager_user_id,
            manager_name=manager_names.get(t.manager_user_id) if t.manager_user_id else None,
            member_count=members.get(t.id, 0),
            created_at=t.created_at,
        )
        for t in teams
    ]


async def create_practice(ctx: Ctx, body: PracticeCreate) -> PracticeOut:
    if await repository.practice_name_taken(ctx.db, body.name):
        raise HTTPException(status.HTTP_409_CONFLICT, "A practice with this name already exists.")
    practice = Practice(name=body.name, notes=body.notes)
    ctx.db.add(practice)
    await ctx.db.flush()
    audit.record(
        ctx.db,
        action="practice.created",
        entity_type="practice",
        entity_id=practice.id,
        actor_user_id=ctx.user.id,
        practice_id=practice.id,
        after={"name": practice.name},
    )
    await ctx.db.commit()
    await ctx.db.refresh(practice)
    return (await practices_out(ctx, [practice]))[0]


async def update_practice(ctx: Ctx, practice_id: uuid.UUID, body: PracticeUpdate) -> PracticeOut:
    practice = await repository.get_practice(ctx.db, await get_scope(ctx), practice_id)
    if practice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Practice not found.")
    before: dict[str, object] = {}
    after: dict[str, object] = {}
    for field in body.model_fields_set:
        new = getattr(body, field)
        if new is None or new == getattr(practice, field):
            continue
        if field == "name" and await repository.practice_name_taken(ctx.db, new, except_id=practice.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "A practice with this name already exists.")
        before[field], after[field] = getattr(practice, field), new
        setattr(practice, field, new)
    if after:
        audit.record(
            ctx.db,
            action="practice.updated",
            entity_type="practice",
            entity_id=practice.id,
            actor_user_id=ctx.user.id,
            practice_id=practice.id,
            before=before,
            after=after,
        )
    await ctx.db.commit()
    await ctx.db.refresh(practice)
    return (await practices_out(ctx, [practice]))[0]


async def _validate_team_links(ctx: Ctx, practice_id: uuid.UUID | None, manager_id: uuid.UUID | None) -> None:
    scope = await get_scope(ctx)
    if practice_id is not None:
        if not await repository.names_of_practices(ctx.db, {practice_id}):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Practice does not exist.")
        require_within_scope(scope, practice_ids={practice_id})
    if manager_id is not None and not await repository.active_user_exists(ctx.db, manager_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The manager must be an active user.")


async def create_team(ctx: Ctx, body: TeamCreate) -> TeamOut:
    await _validate_team_links(ctx, body.practice_id, body.manager_user_id)
    if await repository.team_name_taken(ctx.db, body.name, body.practice_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A team with this name already exists here.")
    team = Team(name=body.name, practice_id=body.practice_id, manager_user_id=body.manager_user_id)
    ctx.db.add(team)
    await ctx.db.flush()
    audit.record(
        ctx.db,
        action="team.created",
        entity_type="team",
        entity_id=team.id,
        actor_user_id=ctx.user.id,
        practice_id=team.practice_id,
        after={
            "name": team.name,
            "practice_id": str(team.practice_id) if team.practice_id else None,
            "manager_user_id": str(team.manager_user_id) if team.manager_user_id else None,
        },
    )
    await ctx.db.commit()
    await ctx.db.refresh(team)
    return (await teams_out(ctx, [team]))[0]


async def update_team(ctx: Ctx, team_id: uuid.UUID, body: TeamUpdate) -> TeamOut:
    team = await repository.get_team(ctx.db, await get_scope(ctx), team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    sent = body.model_fields_set
    new_practice = body.practice_id if "practice_id" in sent else team.practice_id
    new_manager = body.manager_user_id if "manager_user_id" in sent else team.manager_user_id
    new_name = body.name if "name" in sent and body.name else team.name
    await _validate_team_links(ctx, new_practice, new_manager)
    if (new_name, new_practice) != (team.name, team.practice_id) and await repository.team_name_taken(
        ctx.db, new_name, new_practice, except_id=team.id
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "A team with this name already exists here.")

    before: dict[str, object] = {}
    after: dict[str, object] = {}
    for field, new in (("name", new_name), ("practice_id", new_practice), ("manager_user_id", new_manager)):
        old = getattr(team, field)
        if old != new:
            before[field] = str(old) if old is not None else None
            after[field] = str(new) if new is not None else None
            setattr(team, field, new)
    if after:
        audit.record(
            ctx.db,
            action="team.updated",
            entity_type="team",
            entity_id=team.id,
            actor_user_id=ctx.user.id,
            practice_id=team.practice_id,
            before=before,
            after=after,
        )
    await ctx.db.commit()
    await ctx.db.refresh(team)
    return (await teams_out(ctx, [team]))[0]
