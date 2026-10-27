import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.modules.practices.models import Practice, Team, TeamMember, UserPractice
from app.modules.users.models import User


async def list_practices(db: AsyncSession, scope: Scope, *, status: str | None) -> Sequence[Practice]:
    statement = select(Practice)
    if not scope.company_wide:
        statement = statement.where(Practice.id.in_(scope.practice_ids))
    if status:
        statement = statement.where(Practice.status == status)
    return (await db.scalars(statement.order_by(Practice.name))).all()


async def get_practice(db: AsyncSession, scope: Scope, practice_id: uuid.UUID) -> Practice | None:
    if not scope.company_wide and practice_id not in scope.practice_ids:
        return None
    return await db.get(Practice, practice_id)


async def practice_counts(db: AsyncSession, ids: list[uuid.UUID]) -> tuple[dict, dict]:
    users = dict(
        (
            await db.execute(
                select(UserPractice.practice_id, func.count())
                .where(UserPractice.practice_id.in_(ids))
                .group_by(UserPractice.practice_id)
            )
        ).all()
    )
    teams = dict(
        (
            await db.execute(
                select(Team.practice_id, func.count())
                .where(Team.practice_id.in_(ids))
                .group_by(Team.practice_id)
            )
        ).all()
    )
    return users, teams


async def practice_name_taken(db: AsyncSession, name: str, *, except_id: uuid.UUID | None = None) -> bool:
    statement = select(func.count()).select_from(Practice).where(func.lower(Practice.name) == name.lower())
    if except_id:
        statement = statement.where(Practice.id != except_id)
    return await db.scalar(statement) > 0


async def list_teams(db: AsyncSession, scope: Scope) -> Sequence[Team]:
    statement = select(Team)
    if not scope.company_wide:
        statement = statement.where(
            or_(Team.id.in_(scope.team_ids), Team.practice_id.in_(scope.practice_ids))
        )
    return (await db.scalars(statement.order_by(Team.name))).all()


async def get_team(db: AsyncSession, scope: Scope, team_id: uuid.UUID) -> Team | None:
    if not scope.company_wide and team_id not in scope.team_ids:
        return None
    return await db.get(Team, team_id)


async def team_name_taken(
    db: AsyncSession, name: str, practice_id: uuid.UUID | None, *, except_id: uuid.UUID | None = None
) -> bool:
    statement = select(func.count()).select_from(Team).where(func.lower(Team.name) == name.lower())
    statement = statement.where(
        Team.practice_id == practice_id if practice_id is not None else Team.practice_id.is_(None)
    )
    if except_id:
        statement = statement.where(Team.id != except_id)
    return await db.scalar(statement) > 0


async def member_counts(db: AsyncSession, team_ids: list[uuid.UUID]) -> dict:
    return dict(
        (
            await db.execute(
                select(TeamMember.team_id, func.count())
                .where(TeamMember.team_id.in_(team_ids))
                .group_by(TeamMember.team_id)
            )
        ).all()
    )


async def names_of_practices(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict((await db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(ids)))).all())


async def names_of_users(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all())


async def active_user_exists(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return (
        await db.scalar(
            select(func.count()).select_from(User).where(User.id == user_id, User.status == "active")
        )
        > 0
    )
