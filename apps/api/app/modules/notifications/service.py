"""
Who is told about what (project brief, section 8). Notifications are written in the same transaction as
the change they describe. Titles use claim and upload numbers, never patient details, and the person who
made the change is never notified about their own action.
"""

import uuid
from collections.abc import Iterable
from datetime import date

from sqlalchemy import Text, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.claims.models import Claim
from app.modules.notifications.models import Notification
from app.modules.practices.models import UserPractice
from app.modules.roles.models import Role, RolePermission
from app.modules.users.models import User


def send(
    db: AsyncSession,
    recipients: Iterable[uuid.UUID | None],
    *,
    kind: str,
    title: str,
    link: str | None = None,
    body: str | None = None,
    actor: uuid.UUID | None = None,
) -> None:
    for recipient in {r for r in recipients if r is not None and r != actor}:
        db.add(
            Notification(
                recipient_user_id=recipient, kind=kind, title=title, body=body, link=link, actor_user_id=actor
            )
        )


async def _active_with_permission(db: AsyncSession, permission: str) -> set[uuid.UUID]:
    rows = await db.scalars(
        select(User.id)
        .join(Role, Role.id == User.role_id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .where(RolePermission.permission_key == permission, User.status == "active")
    )
    return set(rows)


async def oversight(db: AsyncSession) -> set[uuid.UUID]:
    """Management and System Administrators (anyone holding notifications.oversight)."""
    return await _active_with_permission(db, "notifications.oversight")


async def practice_reviewers(db: AsyncSession, practice_id: uuid.UUID) -> set[uuid.UUID]:
    """People who resolve review items and work in this practice (AR Leads and Managers by default)."""
    reviewers = await _active_with_permission(db, "claims.review")
    members = set(
        await db.scalars(select(UserPractice.user_id).where(UserPractice.practice_id == practice_id))
    )
    return reviewers & members


async def create_followup_reminders(db: AsyncSession, user_id: uuid.UUID, today: date) -> None:
    """
    One reminder per claim when its follow-up date arrives, and one when it has passed. Created when the
    person next opens the portal, so no background job is needed; the dedupe key keeps them unique.
    """
    number = func.concat("CLM-", func.lpad(func.cast(Claim.number, Text()), 6, "0"))
    for kind, condition, wording in (
        ("followup.due", Claim.followup_date == today, " follow-up is due today"),
        ("followup.overdue", Claim.followup_date < today, " follow-up is overdue"),
    ):
        source = select(
            Claim.assigned_user_id,
            literal(kind),
            func.concat(number, wording),
            func.concat("/claims/", func.cast(Claim.id, Text())),
            func.concat(kind, ":", func.cast(Claim.id, Text()), ":", func.cast(Claim.followup_date, Text())),
        ).where(Claim.assigned_user_id == user_id, Claim.merged_into_id.is_(None), condition)
        statement = (
            insert(Notification)
            .from_select(["recipient_user_id", "kind", "title", "link", "dedupe_key"], source)
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
        )
        await db.execute(statement)
