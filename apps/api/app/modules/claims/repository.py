import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import Ctx
from app.core.scope import Scope
from app.modules.claims.models import Claim, ClaimNote
from app.modules.practices.models import Practice, UserPractice
from app.modules.roles.models import Role
from app.modules.users.models import User

# People in these roles see only the claims assigned to them (project brief, section 3).
ASSIGNED_ONLY_ROLES = frozenset({"ar_associate"})
# Who a claim can be assigned to: active AR staff of the claim's practice.
ASSIGNABLE_ROLES = ("ar_associate", "ar_lead", "ar_manager")


def visible(statement: Select, ctx: Ctx, scope: Scope) -> Select:
    """Limits any claim query to what the signed-in person may see. Every claim query goes through here."""
    if scope.company_wide:
        return statement
    if ctx.role.key in ASSIGNED_ONLY_ROLES:
        return statement.where(Claim.assigned_user_id == ctx.user.id)
    return statement.where(Claim.practice_id.in_(scope.practice_ids))


def apply_view(statement: Select, view: str, ctx: Ctx, today: date) -> Select:
    match view:
        case "mine":
            return statement.where(Claim.assigned_user_id == ctx.user.id)
        case "unassigned":
            return statement.where(Claim.assigned_user_id.is_(None))
        case "due-today":
            return statement.where(Claim.followup_date == today)
        case "tomorrow":
            return statement.where(Claim.followup_date == today + timedelta(days=1))
        case "overdue":
            return statement.where(Claim.followup_date < today)
        case "needs-review":
            return statement.where(Claim.needs_review.is_(True))
        case _:
            return statement


def apply_filters(
    statement: Select,
    *,
    q: str | None,
    claim_status: str | None,
    practice_id: uuid.UUID | None,
    upload_id: uuid.UUID | None,
) -> Select:
    if q:
        text = q.strip()
        digits = text.upper().removeprefix("CLM-").lstrip("0")
        conditions = [
            Claim.patient_name.ilike(f"%{text}%"),
            Claim.subscriber_id.ilike(f"%{text.replace(' ', '')}%"),
            Claim.insurance_carrier.ilike(f"%{text}%"),
        ]
        if digits.isdigit():
            conditions.append(Claim.number == int(digits))
        statement = statement.where(or_(*conditions))
    if claim_status:
        statement = statement.where(
            Claim.claim_status.is_(None) if claim_status == "__none__" else Claim.claim_status == claim_status
        )
    if practice_id:
        statement = statement.where(Claim.practice_id == practice_id)
    if upload_id:
        statement = statement.where(Claim.upload_id == upload_id)
    return statement


async def page(
    db: AsyncSession, statement: Select, *, limit: int, offset: int
) -> tuple[Sequence[Claim], int]:
    total = await db.scalar(select(func.count()).select_from(statement.subquery()))
    claims = await db.scalars(
        statement.order_by(Claim.service_date, Claim.number).limit(limit).offset(offset)
    )
    return claims.all(), total or 0


async def practice_names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict((await db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(ids)))).all())


async def people(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    if not ids:
        return {}
    rows = await db.execute(
        select(User.id, User.full_name, Role.name).join(Role, Role.id == User.role_id).where(User.id.in_(ids))
    )
    return {user_id: (name, role) for user_id, name, role in rows}


async def notes(db: AsyncSession, claim_id: uuid.UUID) -> Sequence[ClaimNote]:
    rows = await db.scalars(
        select(ClaimNote).where(ClaimNote.claim_id == claim_id).order_by(ClaimNote.created_at.desc())
    )
    return rows.all()


async def assignees(db: AsyncSession, practice_id: uuid.UUID) -> list[tuple[uuid.UUID, str, str]]:
    rows = await db.execute(
        select(User.id, User.full_name, Role.name)
        .join(Role, Role.id == User.role_id)
        .join(UserPractice, UserPractice.user_id == User.id)
        .where(
            UserPractice.practice_id == practice_id, User.status == "active", Role.key.in_(ASSIGNABLE_ROLES)
        )
        .order_by(User.full_name)
    )
    return [tuple(row) for row in rows]
