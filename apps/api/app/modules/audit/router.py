import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.context import Ctx, require
from app.modules.audit.enrich import enrich
from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import AuditPage
from app.modules.users.models import User

router = APIRouter(prefix="/audit-events", tags=["audit"])

TIMEZONE_NOTE = "Dates are whole UTC days."


@router.get("", response_model=AuditPage)
async def list_audit_events(
    ctx: Annotated[Ctx, Depends(require("audit.view"))],
    action: Annotated[
        str | None, Query(max_length=60, description="Exact action or a prefix ending in '.'")
    ] = None,
    actor_user_id: uuid.UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[date | None, Query(description=TIMEZONE_NOTE)] = None,
    date_to: Annotated[date | None, Query(description=TIMEZONE_NOTE)] = None,
    before_id: Annotated[
        int | None, Query(description="Paging: pass next_before_id from the last page")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    """
    Newest first. In M0 every holder of audit.view sees all events, because they are all platform
    events (sign-ins, users, practices, roles). Claim events arrive in M3 with practice scoping.
    """
    statement = select(AuditEvent, User).outerjoin(User, User.id == AuditEvent.actor_user_id)
    if action:
        statement = statement.where(
            AuditEvent.action.startswith(action) if action.endswith(".") else AuditEvent.action == action
        )
    if actor_user_id:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        statement = statement.where(AuditEvent.entity_id == entity_id)
    if date_from:
        statement = statement.where(
            AuditEvent.occurred_at >= datetime.combine(date_from, time.min, tzinfo=UTC)
        )
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        statement = statement.where(AuditEvent.occurred_at < end)
    if before_id:
        statement = statement.where(AuditEvent.id < before_id)

    rows = (await ctx.db.execute(statement.order_by(AuditEvent.id.desc()).limit(limit + 1))).all()
    events = await enrich(ctx, rows[:limit])
    return AuditPage(events=events, next_before_id=events[-1].id if len(rows) > limit else None)
