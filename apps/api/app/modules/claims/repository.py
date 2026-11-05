import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import Select, and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import users_with
from app.core.context import Ctx
from app.modules.claims.models import Claim, ClaimNote
from app.modules.practices.models import Practice, TeamMember
from app.modules.roles.models import Role
from app.modules.users.models import User


def visible(statement: Select, ctx: Ctx) -> Select:
    """
    Limits any claim query to what the signed-in person may see. Every claim query goes through here.
    Per practice: claims.view_practice shows every claim; claims.view_team shows unassigned claims and claims
    of people in the person's teams; claims.view shows only claims assigned to them.
    """
    access = ctx.access
    whole = access.practices_with("claims.view_practice")
    if whole is None:
        return statement
    conditions = []
    if whole:
        conditions.append(Claim.practice_id.in_(whole))

    team = access.practices_with("claims.view_team")
    team_people = select(TeamMember.user_id).where(TeamMember.team_id.in_(access.team_ids))
    team_claims = or_(
        Claim.assigned_user_id.is_(None),
        Claim.assigned_user_id == ctx.user.id,
        Claim.assigned_user_id.in_(team_people),
    )
    if team is None:
        conditions.append(team_claims)
    elif team - whole:
        conditions.append(and_(Claim.practice_id.in_(team - whole), team_claims))

    own = access.practices_with("claims.view")
    if own is None:
        conditions.append(Claim.assigned_user_id == ctx.user.id)
    elif own:
        conditions.append(and_(Claim.practice_id.in_(own), Claim.assigned_user_id == ctx.user.id))

    return statement.where(or_(*conditions)) if conditions else statement.where(false())


def active(statement: Select) -> Select:
    """Leaves out lines merged into an earlier claim and claims withdrawn by a reversed upload.
    Every list, count and total uses this."""
    return statement.where(Claim.merged_into_id.is_(None), Claim.withdrawn_at.is_(None))


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
        case "merged":
            return statement.where(Claim.merged_into_id.is_not(None))
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
    """Who a claim of this practice can be assigned to: active people holding claims.receive there."""
    ids = await users_with(db, "claims.receive", practice_id)
    if not ids:
        return []
    rows = await db.execute(
        select(User.id, User.full_name, Role.name)
        .join(Role, Role.id == User.role_id)
        .where(User.id.in_(ids))
        .order_by(User.full_name)
    )
    return [tuple(row) for row in rows]


async def numbers(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    return dict((await db.execute(select(Claim.id, Claim.number).where(Claim.id.in_(ids)))).all())


async def same_visit(db: AsyncSession, claim: Claim) -> list[Claim]:
    """Other claims of the same practice for the same patient, subscriber ID and service date."""
    rows = await db.scalars(
        select(Claim)
        .where(
            Claim.practice_id == claim.practice_id,
            Claim.service_date == claim.service_date,
            Claim.subscriber_id == claim.subscriber_id,
            Claim.id != claim.id,
            Claim.merged_into_id.is_(None),
            Claim.withdrawn_at.is_(None),
        )
        .order_by(Claim.number)
    )
    name = " ".join(claim.patient_name.lower().split())
    return [c for c in rows if " ".join(c.patient_name.lower().split()) == name]


async def assignees_all(db: AsyncSession, practice_ids: set[uuid.UUID]) -> list[tuple[uuid.UUID, str, str]]:
    """People who are active AR staff of every one of these practices."""
    common: list[tuple[uuid.UUID, str, str]] | None = None
    for practice_id in practice_ids:
        people = await assignees(db, practice_id)
        common = people if common is None else [p for p in common if p in people]
    return common or []
