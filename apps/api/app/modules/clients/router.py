import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core.context import Ctx, require
from app.core.schemas import NamedRef
from app.modules.clients import reports, service
from app.modules.clients.reports import ClientCatalogueItem, ClientContext, ClientExportRequest, ClientFilters
from app.modules.clients.service import (
    ClientOrgIn,
    ClientOrgOut,
    ClientOrgUpdate,
    ClientUserIn,
    ClientUserOut,
    ClientUserUpdate,
)
from app.modules.reports.schemas import ExportOut, ReportRun
from app.modules.reports.service import MEDIA

# ---- Portal team: client organisations and their accounts ----------------------------------------------

router = APIRouter(prefix="/clients", tags=["clients"])
CanManage = Annotated[Ctx, Depends(require("clients.manage"))]


@router.get("", response_model=list[ClientOrgOut])
async def list_orgs(ctx: CanManage) -> list[ClientOrgOut]:
    return await service.list_orgs(ctx)


@router.post("", response_model=ClientOrgOut, status_code=201)
async def create_org(ctx: CanManage, body: ClientOrgIn) -> ClientOrgOut:
    return await service.create_org(ctx, body)


@router.patch("/{org_id}", response_model=ClientOrgOut)
async def update_org(ctx: CanManage, org_id: uuid.UUID, body: ClientOrgUpdate) -> ClientOrgOut:
    """Name, status, practices, approved reports, patient detail and user-management delegation."""
    return await service.update_org(ctx, org_id, body)


@router.get("/{org_id}/users", response_model=list[ClientUserOut])
async def list_users(ctx: CanManage, org_id: uuid.UUID) -> list[ClientUserOut]:
    return await service.list_client_users(ctx, org_id)


@router.post("/{org_id}/users", response_model=ClientUserOut, status_code=201)
async def create_user(ctx: CanManage, org_id: uuid.UUID, body: ClientUserIn) -> ClientUserOut:
    return await service.create_client_user(ctx, org_id, body)


@router.patch("/{org_id}/users/{user_id}", response_model=ClientUserOut)
async def update_user(
    ctx: CanManage, org_id: uuid.UUID, user_id: uuid.UUID, body: ClientUserUpdate
) -> ClientUserOut:
    return await service.update_client_user(ctx, org_id, user_id, body)


@router.post("/{org_id}/users/{user_id}/deactivate", response_model=ClientUserOut)
async def deactivate_user(ctx: CanManage, org_id: uuid.UUID, user_id: uuid.UUID) -> ClientUserOut:
    return await service.deactivate_client_user(ctx, org_id, user_id)


# ---- Client accounts: their own reports, and their users when delegated ----------------------------------

portal = APIRouter(prefix="/client-portal", tags=["client portal"])
CanView = Annotated[Ctx, Depends(require("client_reports.view"))]
CanDownload = Annotated[Ctx, Depends(require("client_reports.download"))]
CanManageUsers = Annotated[Ctx, Depends(require("client_users.manage"))]


@portal.get("/context", response_model=ClientContext)
async def client_context(ctx: CanView) -> ClientContext:
    return await reports.context(ctx)


@portal.get("/catalogue", response_model=list[ClientCatalogueItem])
async def client_catalogue(ctx: CanView) -> list[ClientCatalogueItem]:
    """The reports the portal team approved for this organisation."""
    return await reports.catalogue(ctx)


@portal.post("/reports/{key}/run", response_model=ReportRun)
async def run(ctx: CanView, key: str, body: ClientFilters) -> ReportRun:
    return await reports.run(ctx, key, body)


@portal.post("/reports/{key}/exports", response_model=ExportOut, status_code=201)
async def export(ctx: CanDownload, key: str, body: ClientExportRequest) -> ExportOut:
    return await reports.export(ctx, key, body.format, body.filters)


@portal.get("/exports", response_model=list[ExportOut])
async def list_exports(ctx: CanView) -> list[ExportOut]:
    return await reports.list_exports(ctx)


@portal.get("/exports/{export_id}/download")
async def download(ctx: CanDownload, export_id: uuid.UUID) -> Response:
    record, data = await reports.download(ctx, export_id)
    return Response(
        data,
        media_type=MEDIA[record.format],
        headers={
            "Content-Disposition": f'attachment; filename="{record.file_name}"',
            "Cache-Control": "no-store",
        },
    )


@portal.get("/practices", response_model=list[NamedRef])
async def org_practices(ctx: CanManageUsers) -> list[NamedRef]:
    return await reports.org_practice_choices(ctx)


@portal.get("/users", response_model=list[ClientUserOut])
async def portal_users(ctx: CanManageUsers) -> list[ClientUserOut]:
    """A delegated Client Reporting Admin's own organisation's accounts."""
    return await service.list_client_users(ctx, None)


@portal.post("/users", response_model=ClientUserOut, status_code=201)
async def portal_create_user(ctx: CanManageUsers, body: ClientUserIn) -> ClientUserOut:
    return await service.create_client_user(ctx, None, body)


@portal.patch("/users/{user_id}", response_model=ClientUserOut)
async def portal_update_user(
    ctx: CanManageUsers, user_id: uuid.UUID, body: ClientUserUpdate
) -> ClientUserOut:
    return await service.update_client_user(ctx, None, user_id, body)


@portal.post("/users/{user_id}/deactivate", response_model=ClientUserOut)
async def portal_deactivate_user(ctx: CanManageUsers, user_id: uuid.UUID) -> ClientUserOut:
    return await service.deactivate_client_user(ctx, None, user_id)
