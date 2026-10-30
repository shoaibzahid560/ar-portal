"""The four dropdowns from the AR sheet. Options are added or retired, never renamed or deleted,
so values already saved on claims always keep their meaning."""

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.context import Ctx
from app.modules.lists.models import LIST_KEYS, OptionListItem
from app.modules.lists.schemas import ListsResponse, OptionOut


async def all_lists(db: AsyncSession) -> ListsResponse:
    grouped: dict[str, list[OptionOut]] = defaultdict(list)
    items = await db.scalars(
        select(OptionListItem).order_by(OptionListItem.list_key, OptionListItem.sort_order)
    )
    for item in items:
        grouped[item.list_key].append(OptionOut(id=item.id, value=item.value, active=item.active))
    return ListsResponse(**{key: grouped[key] for key in LIST_KEYS})


async def active_values(db: AsyncSession) -> dict[str, set[str]]:
    rows = await db.execute(
        select(OptionListItem.list_key, OptionListItem.value).where(OptionListItem.active)
    )
    values: dict[str, set[str]] = defaultdict(set)
    for key, value in rows:
        values[key].add(value)
    return values


async def add_option(ctx: Ctx, list_key: str, value: str) -> ListsResponse:
    exists = await ctx.db.scalar(
        select(func.count())
        .select_from(OptionListItem)
        .where(OptionListItem.list_key == list_key, func.lower(OptionListItem.value) == value.lower())
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "This option already exists. Restore it instead.")
    position = await ctx.db.scalar(
        select(func.coalesce(func.max(OptionListItem.sort_order), -1) + 1).where(
            OptionListItem.list_key == list_key
        )
    )
    item = OptionListItem(list_key=list_key, value=value, sort_order=position)
    ctx.db.add(item)
    await ctx.db.flush()
    audit.record(
        ctx.db,
        action="list.option_added",
        entity_type="list",
        entity_id=list_key,
        actor_user_id=ctx.user.id,
        after={"value": value},
    )
    await ctx.db.commit()
    return await all_lists(ctx.db)


async def set_active(ctx: Ctx, item_id: int, active: bool) -> ListsResponse:
    item = await ctx.db.get(OptionListItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Option not found.")
    if item.active != active:
        item.active = active
        audit.record(
            ctx.db,
            action="list.option_restored" if active else "list.option_retired",
            entity_type="list",
            entity_id=item.list_key,
            actor_user_id=ctx.user.id,
            after={"value": item.value, "active": active},
        )
        await ctx.db.commit()
    return await all_lists(ctx.db)
