from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Ctx, CurrentCtx, require
from app.modules.lists import service
from app.modules.lists.schemas import ListKey, ListsResponse, OptionCreate, OptionUpdate

router = APIRouter(prefix="/lists", tags=["lists"])

CanManage = Annotated[Ctx, Depends(require("lists.manage"))]


@router.get("", response_model=ListsResponse)
async def get_lists(ctx: CurrentCtx) -> ListsResponse:
    """The dropdown options for claims. Retired options are included, marked inactive."""
    return await service.all_lists(ctx.db)


@router.post("/{list_key}", response_model=ListsResponse, status_code=201)
async def add_option(ctx: CanManage, list_key: ListKey, body: OptionCreate) -> ListsResponse:
    return await service.add_option(ctx, list_key, body.value)


@router.patch("/items/{item_id}", response_model=ListsResponse)
async def update_option(ctx: CanManage, item_id: int, body: OptionUpdate) -> ListsResponse:
    """Retire an option (it stays on existing claims but can't be chosen) or restore it."""
    return await service.set_active(ctx, item_id, body.active)
