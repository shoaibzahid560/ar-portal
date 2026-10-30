import csv
import io
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select

from app.core import audit
from app.core.config import get_settings
from app.core.context import Ctx, require
from app.core.scope import get_scope
from app.core.storage import get_storage
from app.modules.uploads import service
from app.modules.uploads.models import Upload
from app.modules.uploads.schemas import UploadDetail, UploadOut, upload_label

router = APIRouter(prefix="/uploads", tags=["uploads"])

CanView = Annotated[Ctx, Depends(require("uploads.view"))]
CanCreate = Annotated[Ctx, Depends(require("uploads.create"))]
UploadView = Literal["all", "with-errors", "failed"]


def _filtered(view: str):  # type: ignore[no-untyped-def]
    statement = select(Upload)
    if view == "with-errors":
        statement = statement.where(Upload.error_rows > 0)
    elif view == "failed":
        statement = statement.where(Upload.status == "failed")
    return statement


@router.post("", response_model=UploadDetail, status_code=status.HTTP_201_CREATED)
async def create_upload(
    ctx: CanCreate, practice_id: Annotated[uuid.UUID, Form()], file: Annotated[UploadFile, File()]
) -> UploadDetail:
    """Upload an AR sheet for one practice. Valid lines become claims; problems are listed by row."""
    data = await file.read(get_settings().max_upload_bytes + 1)
    return await service.create_upload(ctx, practice_id, file.filename or "", data)


@router.get("", response_model=list[UploadOut])
async def list_uploads(
    ctx: CanView, view: UploadView = "all", limit: Annotated[int, Query(ge=1, le=200)] = 100
) -> list[UploadOut]:
    statement = service.visible_uploads(_filtered(view), await get_scope(ctx))
    uploads = await ctx.db.scalars(statement.order_by(Upload.number.desc()).limit(limit))
    return await service.to_out(ctx, list(uploads))


@router.get("/counts", response_model=dict[str, int])
async def upload_counts(ctx: CanView) -> dict[str, int]:
    scope = await get_scope(ctx)
    counts = {}
    for view in ("all", "with-errors", "failed"):
        statement = service.visible_uploads(_filtered(view), scope)
        counts[view] = await ctx.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    return counts


@router.get("/{upload_id}", response_model=UploadDetail)
async def get_upload(ctx: CanView, upload_id: uuid.UUID) -> UploadDetail:
    return await service.detail(ctx, await service.load_visible(ctx, upload_id))


@router.get("/{upload_id}/errors.csv")
async def error_report(ctx: CanView, upload_id: uuid.UUID) -> Response:
    """The row problems as a spreadsheet, to fix the file and upload it again. Contains no cell values."""
    upload = await service.load_visible(ctx, upload_id)
    report = await service.detail(ctx, upload)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Row", "Column", "Problem"])
    writer.writerows([e.row_number, e.column, e.message] for e in report.errors)
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{upload_label(upload.number)}-errors.csv"'},
    )


@router.get("/{upload_id}/file")
async def original_file(ctx: CanView, upload_id: uuid.UUID) -> Response:
    """The file exactly as it was uploaded. Every download is recorded in the audit log."""
    upload = await service.load_visible(ctx, upload_id)
    data = get_storage().read(upload.storage_key)
    audit.record(
        ctx.db,
        action="upload.downloaded",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=upload.practice_id,
    )
    await ctx.db.commit()
    safe = "".join(ch for ch in upload.file_name if ch.isalnum() or ch in "._- ") or "upload"
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe}"', "Cache-Control": "no-store"},
    )
