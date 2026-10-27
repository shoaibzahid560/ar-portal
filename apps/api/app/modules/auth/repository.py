import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import UserSession
from app.modules.practices.models import Practice, Team, TeamMember, UserPractice
from app.modules.roles.models import Role, RolePermission
from app.modules.users.models import User


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email.strip().lower()))


async def get_session_with_user(db: AsyncSession, token_hash: str) -> tuple[UserSession, User] | None:
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == token_hash)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def get_role(db: AsyncSession, role_id: int) -> Role:
    role = await db.get(Role, role_id)
    if role is None:
        raise LookupError(f"Role {role_id} does not exist")
    return role


async def get_role_by_key(db: AsyncSession, key: str) -> Role | None:
    return await db.scalar(select(Role).where(Role.key == key))


async def get_permission_keys(db: AsyncSession, role_id: int) -> set[str]:
    rows = await db.scalars(select(RolePermission.permission_key).where(RolePermission.role_id == role_id))
    return set(rows)


async def get_user_practices(db: AsyncSession, user_id: uuid.UUID) -> list[Practice]:
    rows = await db.scalars(
        select(Practice)
        .join(UserPractice, UserPractice.practice_id == Practice.id)
        .where(UserPractice.user_id == user_id)
        .order_by(Practice.name)
    )
    return list(rows)


async def get_user_teams(db: AsyncSession, user_id: uuid.UUID) -> list[Team]:
    rows = await db.scalars(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.name)
    )
    return list(rows)
