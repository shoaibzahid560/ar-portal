"""
Effective access (Roles & Access specification, section 1):

    role defaults (primary role + additional roles) + approved additional grants,
    constrained by practice scope.

A person's primary role, and any additional role given without a practice, apply in every practice they
are assigned to. An additional role given for one practice applies there only. "scope.all_practices"
(from a role that applies everywhere) lifts the practice limit. Every data check asks this object
"may this person do X in practice P?", so the rule lives in one place and never depends on role names.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.grants.models import PermissionGrant
from app.modules.practices.models import Team, TeamMember, UserPractice
from app.modules.roles.models import RolePermission, UserRole

ALL_PRACTICES = "scope.all_practices"


@dataclass(frozen=True)
class Access:
    everywhere: frozenset[str]
    by_practice: Mapping[uuid.UUID, frozenset[str]] = field(default_factory=dict)
    practice_ids: frozenset[uuid.UUID] = frozenset()
    team_ids: frozenset[uuid.UUID] = frozenset()

    @property
    def all_practices(self) -> bool:
        return ALL_PRACTICES in self.everywhere

    @property
    def reachable_practice_ids(self) -> frozenset[uuid.UUID]:
        """Practices the person works in at all: their own, plus any where they hold a role or grant."""
        return self.practice_ids | frozenset(self.by_practice)

    def held(self) -> frozenset[str]:
        """Every permission held anywhere. Used to decide whether a screen or route applies at all."""
        held = set(self.everywhere)
        for permissions in self.by_practice.values():
            held |= permissions
        return frozenset(held)

    def has(self, permission: str, practice_id: uuid.UUID) -> bool:
        """May this person do `permission` in this practice?"""
        if permission in self.everywhere and (self.all_practices or practice_id in self.practice_ids):
            return True
        return permission in self.by_practice.get(practice_id, frozenset())

    def practices_with(self, permission: str) -> frozenset[uuid.UUID] | None:
        """The practices where this person holds `permission`. None means every practice."""
        if permission in self.everywhere and self.all_practices:
            return None
        found = set(self.practice_ids) if permission in self.everywhere else set()
        found |= {p for p, permissions in self.by_practice.items() if permission in permissions}
        return frozenset(found)


def active_grant():  # type: ignore[no-untyped-def]
    """SQL condition: an approved grant that hasn't been ended and hasn't expired."""
    return and_(
        PermissionGrant.status == "active",
        or_(PermissionGrant.expires_at.is_(None), PermissionGrant.expires_at > datetime.now(UTC)),
    )


async def load_access(db: AsyncSession, user_id: uuid.UUID, primary_role_id: int) -> Access:
    assignments = list(
        await db.execute(select(UserRole.role_id, UserRole.practice_id).where(UserRole.user_id == user_id))
    )
    role_ids = {primary_role_id} | {role_id for role_id, _ in assignments}
    grants: dict[int, set[str]] = {role_id: set() for role_id in role_ids}
    for role_id, key in await db.execute(
        select(RolePermission.role_id, RolePermission.permission_key).where(
            RolePermission.role_id.in_(role_ids)
        )
    ):
        grants[role_id].add(key)

    everywhere = set(grants[primary_role_id])
    by_practice: dict[uuid.UUID, set[str]] = {}
    for role_id, practice_id in assignments:
        if practice_id is None:
            everywhere |= grants[role_id]
        else:
            by_practice.setdefault(practice_id, set()).update(grants[role_id])
    # Approved grants that haven't ended or expired.
    for key, practice_id in await db.execute(
        select(PermissionGrant.permission_key, PermissionGrant.practice_id).where(
            PermissionGrant.user_id == user_id, active_grant()
        )
    ):
        if practice_id is None:
            everywhere.add(key)
        else:
            by_practice.setdefault(practice_id, set()).add(key)
    # A role or grant for one practice never lifts the practice limit.
    for permissions in by_practice.values():
        permissions.discard(ALL_PRACTICES)

    # Membership only: a role or grant for one practice applies there alone, so it must not make the
    # primary role apply in that practice too.
    practices = set(await db.scalars(select(UserPractice.practice_id).where(UserPractice.user_id == user_id)))
    teams = set(
        await db.scalars(
            select(Team.id)
            .outerjoin(TeamMember, TeamMember.team_id == Team.id)
            .where(or_(TeamMember.user_id == user_id, Team.manager_user_id == user_id))
        )
    )
    return Access(
        everywhere=frozenset(everywhere),
        by_practice={p: frozenset(v) for p, v in by_practice.items()},
        practice_ids=frozenset(practices),
        team_ids=frozenset(teams),
    )


async def users_with(
    db: AsyncSession, permission: str, practice_id: uuid.UUID | None = None
) -> set[uuid.UUID]:
    """
    Active people who hold `permission`: anywhere (practice_id None), or in one practice. Mirrors Access.has,
    in SQL, for questions about other people (who can be assigned here, who reviews this practice's lines).
    """
    from app.modules.users.models import User  # local import: users imports nothing from here

    holding = select(RolePermission.role_id).where(RolePermission.permission_key == permission)
    granted = select(PermissionGrant.user_id).where(
        PermissionGrant.permission_key == permission, active_grant()
    )
    if practice_id is None:
        condition = or_(
            User.role_id.in_(holding),
            User.id.in_(select(UserRole.user_id).where(UserRole.role_id.in_(holding))),
            User.id.in_(granted),
        )
    else:
        everywhere_roles = select(RolePermission.role_id).where(
            RolePermission.permission_key == ALL_PRACTICES
        )
        works_here = or_(
            User.id.in_(select(UserPractice.user_id).where(UserPractice.practice_id == practice_id)),
            User.role_id.in_(everywhere_roles),
            User.id.in_(
                select(UserRole.user_id).where(
                    UserRole.role_id.in_(everywhere_roles), UserRole.practice_id.is_(None)
                )
            ),
        )
        condition = or_(
            and_(User.role_id.in_(holding), works_here),
            and_(
                User.id.in_(
                    select(UserRole.user_id).where(
                        UserRole.role_id.in_(holding), UserRole.practice_id.is_(None)
                    )
                ),
                works_here,
            ),
            User.id.in_(
                select(UserRole.user_id).where(
                    UserRole.role_id.in_(holding), UserRole.practice_id == practice_id
                )
            ),
            and_(User.id.in_(granted.where(PermissionGrant.practice_id.is_(None))), works_here),
            User.id.in_(granted.where(PermissionGrant.practice_id == practice_id)),
        )
    return set(await db.scalars(select(User.id).where(User.status == "active", condition)))
