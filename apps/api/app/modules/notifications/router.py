from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, update

from app.core.clock import business_today
from app.core.context import CurrentCtx
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationOut, NotificationPage
from app.modules.notifications.service import create_followup_reminders

router = APIRouter(prefix="/notifications", tags=["notifications"])


async def _unread(ctx: CurrentCtx) -> int:
    return (
        await ctx.db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_user_id == ctx.user.id, Notification.read_at.is_(None))
        )
        or 0
    )


@router.get("", response_model=NotificationPage)
async def my_notifications(
    ctx: CurrentCtx, limit: Annotated[int, Query(ge=1, le=200)] = 30
) -> NotificationPage:
    """The signed-in person's own notifications, newest first. Nobody can read anyone else's."""
    await create_followup_reminders(ctx.db, ctx.user.id, business_today())
    await ctx.db.commit()
    rows = await ctx.db.scalars(
        select(Notification)
        .where(Notification.recipient_user_id == ctx.user.id)
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    items = [
        NotificationOut(
            id=n.id,
            kind=n.kind,
            title=n.title,
            body=n.body,
            link=n.link,
            created_at=n.created_at,
            read=n.read_at is not None,
        )
        for n in rows
    ]
    return NotificationPage(items=items, unread=await _unread(ctx))


@router.get("/unread-count", response_model=dict[str, int])
async def unread_count(ctx: CurrentCtx) -> dict[str, int]:
    """For the badge on the bell. Also creates any follow-up reminders that have come due."""
    await create_followup_reminders(ctx.db, ctx.user.id, business_today())
    await ctx.db.commit()
    return {"unread": await _unread(ctx)}


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(ctx: CurrentCtx, notification_id: int) -> None:
    result = await ctx.db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.recipient_user_id == ctx.user.id)
        .values(read_at=func.coalesce(Notification.read_at, datetime.now(UTC)))
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found.")
    await ctx.db.commit()


@router.post("/read-all", status_code=204)
async def mark_all_read(ctx: CurrentCtx) -> None:
    await ctx.db.execute(
        update(Notification)
        .where(Notification.recipient_user_id == ctx.user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await ctx.db.commit()
