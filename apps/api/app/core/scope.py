"""
Data scope: which practices, teams and people the signed-in person may see or manage.
Every list query and every assignment check goes through here, so the rule lives in one place.
"""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.context import Ctx
from app.modules.practices.models import Team, TeamMember, UserPractice

# Roles that see the whole company (project brief, section 3). Everyone else sees only their
# own practices and teams. Management decision #1 may change how practice and team scope combine.
COMPANY_WIDE_ROLES = frozenset({"system_admin", "management"})


@dataclass(frozen=True)
class Scope:
    company_wide: bool
    practice_ids: frozenset[uuid.UUID]
    team_ids: frozenset[uuid.UUID]


async def get_scope(ctx: Ctx) -> Scope:
    if ctx.role.key in COMPANY_WIDE_ROLES:
        return Scope(company_wide=True, practice_ids=frozenset(), team_ids=frozenset())
    practice_ids = await ctx.db.scalars(
        select(UserPractice.practice_id).where(UserPractice.user_id == ctx.user.id)
    )
    own_teams = await ctx.db.scalars(select(TeamMember.team_id).where(TeamMember.user_id == ctx.user.id))
    practices = frozenset(practice_ids)
    # Teams they belong to, plus every team that sits inside one of their practices.
    practice_teams = (
        await ctx.db.scalars(select(Team.id).where(Team.practice_id.in_(practices))) if practices else []
    )
    return Scope(
        company_wide=False, practice_ids=practices, team_ids=frozenset(own_teams) | set(practice_teams)
    )


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
