import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import case, func, select

from app.core.clock import business_today
from app.core.context import Ctx, require
from app.core.scope import get_scope
from app.modules.audit.enrich import enrich
from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import AuditEventOut
from app.modules.claims import repository, service
from app.modules.claims.models import Claim
from app.modules.claims.schemas import (
    Assignee,
    BulkAssign,
    BulkResult,
    ClaimDetail,
    ClaimPage,
    ClaimSummary,
    ClaimUpdate,
    ClaimView,
    NoteCreate,
    Resolve,
    StatusCount,
)
from app.modules.users.models import User

router = APIRouter(prefix="/claims", tags=["claims"])

CanView = Annotated[Ctx, Depends(require("claims.view"))]
CanWork = Annotated[Ctx, Depends(require("claims.work"))]
CanReview = Annotated[Ctx, Depends(require("claims.review"))]
VIEWS: tuple[ClaimView, ...] = (
    "all",
    "mine",
    "unassigned",
    "due-today",
    "tomorrow",
    "overdue",
    "needs-review",
)


@router.get("", response_model=ClaimPage)
async def list_claims(
    ctx: CanView,
    view: ClaimView = "all",
    q: Annotated[str | None, Query(max_length=100)] = None,
    claim_status: Annotated[str | None, Query(max_length=80)] = None,
    practice_id: uuid.UUID | None = None,
    upload_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClaimPage:
    """Claims the caller may see. AR Associates only ever see claims assigned to them."""
    statement = repository.visible(select(Claim), ctx, await get_scope(ctx))
    if view != "merged":
        statement = repository.active(statement)
    statement = repository.apply_view(statement, view, ctx, business_today())
    statement = repository.apply_filters(
        statement, q=q, claim_status=claim_status, practice_id=practice_id, upload_id=upload_id
    )
    claims, total = await repository.page(ctx.db, statement, limit=limit, offset=offset)
    return ClaimPage(claims=await service.list_items(ctx, list(claims)), total=total)


@router.get("/counts", response_model=dict[str, int])
async def claim_counts(ctx: CanView) -> dict[str, int]:
    """How many claims are in each view, for the badges in the side panel."""
    base = repository.active(repository.visible(select(Claim.id), ctx, await get_scope(ctx)))
    today = business_today()
    counts = {}
    for view in VIEWS:
        statement = repository.apply_view(base, view, ctx, today)
        counts[view] = await ctx.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    merged = repository.apply_view(
        repository.visible(select(Claim.id), ctx, await get_scope(ctx)), "merged", ctx, today
    )
    counts["merged"] = await ctx.db.scalar(select(func.count()).select_from(merged.subquery())) or 0
    counts["open"] = counts["needs-review"]  # the Review screen's own view name
    return counts


@router.get("/summary", response_model=ClaimSummary)
async def claim_summary(ctx: CanView) -> ClaimSummary:
    """Numbers for the dashboard, within the caller's scope."""
    visible = repository.active(repository.visible(select(Claim), ctx, await get_scope(ctx))).subquery()
    today = business_today()
    totals = (
        await ctx.db.execute(
            select(
                func.count(),
                func.count().filter(visible.c.assigned_user_id.is_(None)),
                func.count().filter(visible.c.followup_date == today),
                func.count().filter(visible.c.followup_date < today),
                func.count().filter(visible.c.needs_review.is_(True)),
                func.coalesce(func.sum(visible.c.billed), 0),
            )
        )
    ).one()
    status_label = case((visible.c.claim_status.is_(None), "No status yet"), else_=visible.c.claim_status)
    rows = await ctx.db.execute(
        select(status_label, func.count(), func.coalesce(func.sum(visible.c.billed), 0))
        .group_by(status_label)
        .order_by(func.count().desc())
    )
    return ClaimSummary(
        total=totals[0],
        unassigned=totals[1],
        due_today=totals[2],
        overdue=totals[3],
        needs_review=totals[4],
        billed_total=Decimal(totals[5]),
        by_status=[StatusCount(status=s, count=c, billed=Decimal(b)) for s, c, b in rows],
    )


@router.get("/assignees", response_model=list[Assignee])
async def assignees_for_practices(
    ctx: CanWork, practice_id: Annotated[list[uuid.UUID], Query(min_length=1, max_length=50)]
) -> list[Assignee]:
    """For bulk assignment: people who are active AR staff of every given practice."""
    people = await service.assignable_for(ctx, await get_scope(ctx), set(practice_id))
    return [Assignee(id=i, name=n, role=r) for i, n, r in people]


@router.post("/bulk-assign", response_model=BulkResult)
async def bulk_assign(ctx: CanWork, body: BulkAssign) -> BulkResult:
    """Assign (or unassign) up to 500 claims at once. Each claim's history records the change."""
    return BulkResult(updated=await service.bulk_assign(ctx, body.claim_ids, body.assigned_user_id))


@router.get("/{claim_id}", response_model=ClaimDetail)
async def get_claim(ctx: CanView, claim_id: uuid.UUID) -> ClaimDetail:
    return await service.detail(ctx, await service.load_visible(ctx, claim_id))


@router.patch("/{claim_id}", response_model=ClaimDetail)
async def update_claim(ctx: CanWork, claim_id: uuid.UUID, body: ClaimUpdate) -> ClaimDetail:
    """Fill in the work fields, or change who the claim is assigned to."""
    return await service.update(ctx, claim_id, body)


@router.post("/{claim_id}/notes", response_model=ClaimDetail, status_code=201)
async def add_note(ctx: CanWork, claim_id: uuid.UUID, body: NoteCreate) -> ClaimDetail:
    return await service.add_note(ctx, claim_id, body.body)


@router.post("/{claim_id}/eob", response_model=ClaimDetail)
async def attach_eob(ctx: CanWork, claim_id: uuid.UUID, file: Annotated[UploadFile, File()]) -> ClaimDetail:
    return await service.attach_eob(ctx, claim_id, file)


@router.get("/{claim_id}/eob")
async def download_eob(ctx: CanView, claim_id: uuid.UUID) -> Response:
    data, name, media_type = await service.read_eob(ctx, claim_id)
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "._- ") or "eob"
    return Response(
        data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "no-store"},
    )


@router.get("/{claim_id}/assignees", response_model=list[Assignee])
async def assignees(ctx: CanWork, claim_id: uuid.UUID) -> list[Assignee]:
    """Who this claim can be assigned to: active AR staff with access to its practice."""
    claim = await service.load_visible(ctx, claim_id)
    return [
        Assignee(id=i, name=n, role=r) for i, n, r in await repository.assignees(ctx.db, claim.practice_id)
    ]


@router.get("/{claim_id}/history", response_model=list[AuditEventOut])
async def history(ctx: CanView, claim_id: uuid.UUID) -> list[AuditEventOut]:
    """Everything that happened to this claim, newest first."""
    claim = await service.load_visible(ctx, claim_id)
    rows = (
        await ctx.db.execute(
            select(AuditEvent, User)
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.entity_type == "claim", AuditEvent.entity_id == str(claim.id))
            .order_by(AuditEvent.id.desc())
            .limit(200)
        )
    ).all()
    return await enrich(ctx, rows)


@router.get("/{claim_id}/matches", response_model=list[ClaimDetail])
async def matches(ctx: CanReview, claim_id: uuid.UUID) -> list[ClaimDetail]:
    """Earlier claims for the same patient, subscriber ID and service date: what this line may belong to."""
    return await service.matches(ctx, claim_id)


@router.post("/{claim_id}/resolve", response_model=ClaimDetail)
async def resolve(ctx: CanReview, claim_id: uuid.UUID, body: Resolve) -> ClaimDetail:
    """Same claim: the earlier claim takes this line's uploaded values and the line is merged into it.
    Separate claim: both stay. Returns the claim that carries on."""
    return await service.resolve(ctx, claim_id, body.decision, body.target_id)
