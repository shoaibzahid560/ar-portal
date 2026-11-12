import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.context import Ctx, require
from app.core.schemas import NamedRef
from app.modules.reports import service
from app.modules.reports.schemas import (
    CatalogueItem,
    ExportOut,
    ExportRequest,
    Filters,
    Overview,
    ReportRun,
    Targets,
)

router = APIRouter(prefix="/reports", tags=["reports"])

CanView = Annotated[Ctx, Depends(require("reports.view"))]
CanExport = Annotated[Ctx, Depends(require("reports.export"))]
CanSettings = Annotated[Ctx, Depends(require("settings.manage"))]


@router.get("/catalogue", response_model=list[CatalogueItem])
async def catalogue(ctx: CanView) -> list[CatalogueItem]:
    """The reports this person may run. Staff-level reports need reports.staff."""
    return service.catalogue(ctx)


@router.get("/people", response_model=list[NamedRef])
async def people_in_scope(ctx: CanView) -> list[NamedRef]:
    """People assigned to claims this person can see: the choices for the Person filter."""
    return await service.people_in_scope(ctx)


@router.get("/overview", response_model=Overview)
async def overview(ctx: CanView, practice_id: Annotated[list[uuid.UUID] | None, Query()] = None) -> Overview:
    """The AR performance dashboard, within the caller's scope."""
    return await service.overview(ctx, practice_id or [])


@router.get("/targets", response_model=Targets)
async def get_targets(ctx: CanView) -> Targets:
    return await service.get_targets(ctx)


@router.put("/targets", response_model=Targets)
async def set_targets(ctx: CanSettings, body: Targets) -> Targets:
    """Report targets and alert thresholds (management decision #7). Recorded in the audit log."""
    return await service.set_targets(ctx, body)


@router.get("/exports", response_model=list[ExportOut])
async def list_exports(ctx: CanView, show: Literal["mine", "everyone"] = "mine") -> list[ExportOut]:
    """Generated report files. "everyone" lists all files (without download) for oversight holders."""
    return await service.list_exports(ctx, show == "everyone")


@router.get("/exports/{export_id}/download")
async def download(ctx: CanExport, export_id: uuid.UUID) -> Response:
    record, data = await service.download(ctx, export_id)
    return Response(
        data,
        media_type=service.MEDIA[record.format],
        headers={
            "Content-Disposition": f'attachment; filename="{record.file_name}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{key}/run", response_model=ReportRun)
async def run(ctx: CanView, key: str, body: Filters) -> ReportRun:
    """Run a report on screen: the first 500 rows, with totals over all of them."""
    return await service.run(ctx, key, body)


@router.post("/{key}/exports", response_model=ExportOut, status_code=201)
async def export(ctx: CanExport, key: str, body: ExportRequest) -> ExportOut:
    """Generate a CSV, Excel or PDF file of the report. Logged, and Management is notified."""
    return await service.export(ctx, key, body.format, body.filters)
