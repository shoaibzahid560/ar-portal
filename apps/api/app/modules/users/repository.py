import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import NamedRef
from app.core.scope import Scope
from app.modules.auth.models import UserSession
from app.modules.practices.models import Practice, Team, TeamMember, UserPractice
from app.modules.roles.models import Role
from app.modules.users.models import User


def _scoped(statement: Select, scope: Scope, viewer_id: uuid.UUID) -> Select:
    """Limits a user query to people who share a practice or team with the viewer (plus themselves)."""
    if scope.company_wide:
        return statement
    in_my_practices = select(UserPractice.user_id).where(UserPractice.practice_id.in_(scope.practice_ids))
    in_my_teams = select(TeamMember.user_id).where(TeamMember.team_id.in_(scope.team_ids))
    return statement.where(or_(User.id == viewer_id, User.id.in_(in_my_practices), User.id.in_(in_my_teams)))


async def list_users(
    db: AsyncSession, scope: Scope, viewer_id: uuid.UUID, *, status: str | None, search: str | None
) -> Sequence[User]:
    statement = _scoped(select(User), scope, viewer_id)
    if status:
        statement = statement.where(User.status == status)
    if search:
        pattern = f"%{search.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(User.full_name).like(pattern),
                User.email.like(pattern),
                User.employee_code.ilike(pattern),
            )
        )
    return (await db.scalars(statement.order_by(User.full_name))).all()


async def get_user(db: AsyncSession, scope: Scope, viewer_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
    return await db.scalar(_scoped(select(User).where(User.id == user_id), scope, viewer_id))


async def email_exists(db: AsyncSession, email: str) -> bool:
    return await db.scalar(select(func.count()).select_from(User).where(User.email == email)) > 0


async def employee_code_exists(db: AsyncSession, code: str, *, except_user: uuid.UUID | None = None) -> bool:
    statement = select(func.count()).select_from(User).where(User.employee_code == code)
    if except_user:
        statement = statement.where(User.id != except_user)
    return await db.scalar(statement) > 0


async def roles_by_id(db: AsyncSession) -> dict[int, Role]:
    return {role.id: role for role in await db.scalars(select(Role))}


async def get_role_by_key(db: AsyncSession, key: str) -> Role | None:
    return await db.scalar(select(Role).where(Role.key == key))


async def count_active_admins(db: AsyncSession, *, excluding: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(User)
        .join(Role, Role.id == User.role_id)
        .where(Role.key == "system_admin", User.status == "active", User.id != excluding)
    )


async def practices_for(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[NamedRef]]:
    result: dict[uuid.UUID, list[NamedRef]] = defaultdict(list)
    rows = await db.execute(
        select(UserPractice.user_id, Practice.id, Practice.name)
        .join(Practice, Practice.id == UserPractice.practice_id)
        .where(UserPractice.user_id.in_(user_ids))
        .order_by(Practice.name)
    )
    for user_id, practice_id, name in rows:
        result[user_id].append(NamedRef(id=practice_id, name=name))
    return result


async def teams_for(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[NamedRef]]:
    result: dict[uuid.UUID, list[NamedRef]] = defaultdict(list)
    rows = await db.execute(
        select(TeamMember.user_id, Team.id, Team.name)
        .join(Team, Team.id == TeamMember.team_id)
        .where(TeamMember.user_id.in_(user_ids))
        .order_by(Team.name)
    )
    for user_id, team_id, name in rows:
        result[user_id].append(NamedRef(id=team_id, name=name))
    return result


async def existing_practice_ids(db: AsyncSession, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    return set(await db.scalars(select(Practice.id).where(Practice.id.in_(ids)))) if ids else set()


async def existing_team_ids(db: AsyncSession, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    return set(await db.scalars(select(Team.id).where(Team.id.in_(ids)))) if ids else set()


async def replace_practices(db: AsyncSession, user_id: uuid.UUID, practice_ids: set[uuid.UUID]) -> None:
    await db.execute(delete(UserPractice).where(UserPractice.user_id == user_id))
    db.add_all(UserPractice(user_id=user_id, practice_id=pid) for pid in practice_ids)


async def replace_teams(db: AsyncSession, user_id: uuid.UUID, team_ids: set[uuid.UUID]) -> None:
    await db.execute(delete(TeamMember).where(TeamMember.user_id == user_id))
    db.add_all(TeamMember(user_id=user_id, team_id=tid) for tid in team_ids)


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
