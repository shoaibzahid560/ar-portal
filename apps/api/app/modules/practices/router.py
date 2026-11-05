import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.core.context import Ctx, require
from app.core.scope import get_scope
from app.modules.practices import repository, service
from app.modules.practices.schemas import (
    PracticeCreate,
    PracticeOut,
    PracticeUpdate,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)

router = APIRouter(tags=["practices"])

CanView = Annotated[Ctx, Depends(require("practices.view"))]
CanManagePractices = Annotated[Ctx, Depends(require("practices.manage"))]
CanManageTeams = Annotated[Ctx, Depends(require("teams.manage"))]


@router.get("/practices", response_model=list[PracticeOut])
async def list_practices(
    ctx: CanView,
    status_filter: Annotated[Literal["active", "paused"] | None, Query(alias="status")] = None,
    can: Annotated[str | None, Query(max_length=60, description="Only practices where you hold this")] = None,
) -> list[PracticeOut]:
    """Practices within the caller's scope; with `can`, only those where the caller holds that permission."""
    practices = await repository.list_practices(ctx.db, await get_scope(ctx), status=status_filter)
    if can:
        practices = [p for p in practices if ctx.access.has(can, p.id)]
    return await service.practices_out(ctx, list(practices))


@router.post("/practices", response_model=PracticeOut, status_code=status.HTTP_201_CREATED)
async def create_practice(ctx: CanManagePractices, body: PracticeCreate) -> PracticeOut:
    return await service.create_practice(ctx, body)


@router.patch("/practices/{practice_id}", response_model=PracticeOut)
async def update_practice(
    ctx: CanManagePractices, practice_id: uuid.UUID, body: PracticeUpdate
) -> PracticeOut:
    return await service.update_practice(ctx, practice_id, body)


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(ctx: CanView) -> list[TeamOut]:
    """Teams within the caller's scope."""
    teams = await repository.list_teams(ctx.db, await get_scope(ctx))
    return await service.teams_out(ctx, list(teams))


@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(ctx: CanManageTeams, body: TeamCreate) -> TeamOut:
    return await service.create_team(ctx, body)


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(ctx: CanManageTeams, team_id: uuid.UUID, body: TeamUpdate) -> TeamOut:
    return await service.update_team(ctx, team_id, body)
