"""
Data scope: which practices, teams and people the signed-in person may see or manage.
Every list query and every assignment check goes through here, so the rule lives in one place.
"""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.context import Ctx
from app.modules.practices.models import Team


@dataclass(frozen=True)
class Scope:
    company_wide: bool
    practice_ids: frozenset[uuid.UUID]
    team_ids: frozenset[uuid.UUID]


async def get_scope(ctx: Ctx) -> Scope:
    """The practices and teams a person works in (company-wide with scope.all_practices)."""
    access = ctx.access
    if access.all_practices:
        return Scope(company_wide=True, practice_ids=frozenset(), team_ids=frozenset())
    practices = access.reachable_practice_ids
    # Teams they belong to or lead, plus every team that sits inside one of their practices.
    practice_teams = (
        await ctx.db.scalars(select(Team.id).where(Team.practice_id.in_(practices))) if practices else []
    )
    return Scope(company_wide=False, practice_ids=practices, team_ids=access.team_ids | set(practice_teams))


def require_within_scope(
    scope: Scope, *, practice_ids: set[uuid.UUID] | None = None, team_ids: set[uuid.UUID] | None = None
) -> None:
    """403 if someone tries to grant access to a practice or team outside their own scope."""
    if scope.company_wide:
        return
    if (practice_ids and not practice_ids <= scope.practice_ids) or (
        team_ids and not team_ids <= scope.team_ids
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can only assign practices and teams within your scope."
        )
