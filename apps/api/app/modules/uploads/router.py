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
from app.core.storage import get_storage
from app.modules.notifications import service as notify
from app.modules.uploads import service
from app.modules.uploads.models import Upload
from app.modules.uploads.schemas import (
    Reason,
    RowDecision,
    UploadDetail,
    UploadOut,
    UploadRowOut,
    upload_label,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

# Uploaders who can't see other uploads still see their own, to check the preview and the outcome.
CanView = Annotated[Ctx, Depends(require("uploads.view", "uploads.create"))]
CanCreate = Annotated[Ctx, Depends(require("uploads.create"))]
CanDecide = Annotated[Ctx, Depends(require("claims.review"))]
CanCommit = Annotated[Ctx, Depends(require("uploads.commit"))]
CanReverse = Annotated[Ctx, Depends(require("uploads.reverse"))]
UploadView = Literal["all", "awaiting", "previews", "with-errors", "failed", "reversed"]
VIEWS: tuple[UploadView, ...] = ("all", "awaiting", "previews", "with-errors", "failed", "reversed")


def _filtered(view: str):  # type: ignore[no-untyped-def]
    statement = select(Upload)
    match view:
        case "awaiting":
            return statement.where(Upload.status == "submitted")
        case "previews":
            return statement.where(Upload.status == "preview")
        case "with-errors":
            return statement.where(Upload.error_rows > 0)
        case "failed":
            return statement.where(Upload.status == "failed")
        case "reversed":
            return statement.where(Upload.status == "reversed")
    return statement


@router.post("", response_model=UploadDetail, status_code=status.HTTP_201_CREATED)
async def create_upload(
    ctx: CanCreate, practice_id: Annotated[uuid.UUID, Form()], file: Annotated[UploadFile, File()]
) -> UploadDetail:
    """Upload an AR sheet for one practice. Nothing is created yet: the result is a preview to check."""
    data = await file.read(get_settings().max_upload_bytes + 1)
    return await service.create_upload(ctx, practice_id, file.filename or "", data)


@router.get("", response_model=list[UploadOut])
async def list_uploads(
    ctx: CanView, view: UploadView = "all", limit: Annotated[int, Query(ge=1, le=200)] = 100
) -> list[UploadOut]:
    statement = service.visible_uploads(_filtered(view), ctx)
    uploads = await ctx.db.scalars(statement.order_by(Upload.number.desc()).limit(limit))
    return await service.to_out(ctx, list(uploads))


@router.get("/counts", response_model=dict[str, int])
async def upload_counts(ctx: CanView) -> dict[str, int]:
    counts = {}
    for view in VIEWS:
        statement = service.visible_uploads(_filtered(view), ctx)
        counts[view] = await ctx.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    return counts


@router.get("/{upload_id}", response_model=UploadDetail)
async def get_upload(ctx: CanView, upload_id: uuid.UUID) -> UploadDetail:
    return await service.detail(ctx, await service.load_visible(ctx, upload_id))


@router.get("/{upload_id}/rows", response_model=list[UploadRowOut])
async def upload_rows(
    ctx: CanView,
    upload_id: uuid.UUID,
    show: Literal["needs-decision", "new", "duplicate", "changed", "repeat"] | None = None,
) -> list[UploadRowOut]:
    """The preview's lines and the claims they match. Values are cleared once the batch is decided."""
    return await service.rows_out(ctx, await service.load_visible(ctx, upload_id), show)


@router.patch("/{upload_id}/rows/{row_id}", response_model=UploadRowOut)
async def decide_row(ctx: CanDecide, upload_id: uuid.UUID, row_id: int, body: RowDecision) -> UploadRowOut:
    """Update an existing claim, create a new claim, or skip the line."""
    return await service.decide_row(ctx, upload_id, row_id, body.decision, body.target_claim_id)


@router.post("/{upload_id}/submit", response_model=UploadDetail)
async def submit(ctx: CanCreate, upload_id: uuid.UUID) -> UploadDetail:
    """Send the preview for approval by a second person."""
    return await service.submit(ctx, upload_id)


@router.post("/{upload_id}/discard", response_model=UploadDetail)
async def discard(ctx: CanView, upload_id: uuid.UUID) -> UploadDetail:
    """Drop a preview or a submitted upload. Nothing is created."""
    return await service.discard(ctx, upload_id)


@router.post("/{upload_id}/commit", response_model=UploadDetail)
async def commit(ctx: CanCommit, upload_id: uuid.UUID) -> UploadDetail:
    """Approve and commit: create the new claims and apply the decided updates. Not by the uploader."""
    return await service.commit(ctx, upload_id)


@router.post("/{upload_id}/reject", response_model=UploadDetail)
async def reject(ctx: CanCommit, upload_id: uuid.UUID, body: Reason) -> UploadDetail:
    return await service.reject(ctx, upload_id, body.reason)


@router.post("/{upload_id}/reverse", response_model=UploadDetail)
async def reverse(ctx: CanReverse, upload_id: uuid.UUID, body: Reason) -> UploadDetail:
    """Undo a committed upload while none of its claims has been worked. A reason is required."""
    return await service.reverse(ctx, upload_id, body.reason)


@router.get("/{upload_id}/errors.csv")
async def error_report(ctx: CanView, upload_id: uuid.UUID) -> Response:
    """The row problems as a spreadsheet, to fix the file and upload it again. Contains no cell values."""
    upload = await service.load_visible(ctx, upload_id)
    report = await service.detail(ctx, upload)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Row", "Column", "Problem"])
    writer.writerows([e.row_number, e.column, e.message] for e in report.errors)
    audit.record(
        ctx.db,
        action="upload.errors_downloaded",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=upload.practice_id,
    )
    await ctx.db.commit()
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
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="upload.downloaded",
        title=f"{ctx.user.full_name} downloaded the original file of {upload_label(upload.number)}",
        link=f"/uploads/{upload.id}",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    safe = "".join(ch for ch in upload.file_name if ch.isalnum() or ch in "._- ") or "upload"
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe}"', "Cache-Control": "no-store"},
    )
