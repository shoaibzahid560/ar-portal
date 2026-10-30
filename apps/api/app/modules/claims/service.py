"""Rules for working claims. Every change is audited in the same transaction as the change itself."""

import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select

from app.core import audit
from app.core.clock import aging, business_today
from app.core.config import get_settings
from app.core.context import Ctx
from app.core.schemas import NamedRef
from app.core.scope import get_scope
from app.core.storage import get_storage
from app.modules.claims import repository
from app.modules.claims.models import Claim, ClaimNote
from app.modules.claims.schemas import (
    ClaimDetail,
    ClaimListItem,
    ClaimUpdate,
    EobOut,
    NoteOut,
    PersonRef,
    UploadRef,
    claim_label,
)
from app.modules.lists.service import active_values
from app.modules.uploads.models import Upload

LIST_FIELDS = ("claim_status", "pay_status", "check_status", "action_taken")
EOB_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _plain(value: Any) -> Any:
    """Audit records hold plain JSON values."""
    if value is None or isinstance(value, str | int | bool):
        return value
    return str(value)


async def load_visible(ctx: Ctx, claim_id: uuid.UUID) -> Claim:
    statement = repository.visible(select(Claim).where(Claim.id == claim_id), ctx, await get_scope(ctx))
    claim = await ctx.db.scalar(statement)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found.")
    return claim


async def list_items(ctx: Ctx, claims: list[Claim]) -> list[ClaimListItem]:
    today = business_today()
    practices = await repository.practice_names(ctx.db, {c.practice_id for c in claims})
    people = await repository.people(ctx.db, {c.assigned_user_id for c in claims if c.assigned_user_id})
    items = []
    for c in claims:
        days, bucket = aging(c.service_date, today)
        person = people.get(c.assigned_user_id) if c.assigned_user_id else None
        items.append(
            ClaimListItem(
                id=c.id,
                number=claim_label(c.number),
                practice=NamedRef(id=c.practice_id, name=practices.get(c.practice_id, "")),
                patient_name=c.patient_name,
                service_date=c.service_date,
                subscriber_id=c.subscriber_id,
                insurance_carrier=c.insurance_carrier,
                billed=c.billed,
                claim_status=c.claim_status,
                action_taken=c.action_taken,
                followup_date=c.followup_date,
                assigned_to=PersonRef(id=c.assigned_user_id, name=person[0], role=person[1])
                if person and c.assigned_user_id
                else None,
                aging_days=days,
                aging_bucket=bucket,
                needs_review=c.needs_review,
            )
        )
    return items


async def detail(ctx: Ctx, claim: Claim) -> ClaimDetail:
    [base] = await list_items(ctx, [claim])
    upload = await ctx.db.get(Upload, claim.upload_id)
    notes = await repository.notes(ctx.db, claim.id)
    authors = await repository.people(ctx.db, {n.author_user_id for n in notes})
    return ClaimDetail(
        **base.model_dump(),
        upload=UploadRef(id=claim.upload_id, number=f"UPL-{upload.number:06d}" if upload else ""),
        patient_dob=claim.patient_dob,
        subscriber_name=claim.subscriber_name,
        subscriber_dob=claim.subscriber_dob,
        allowed_amount=claim.allowed_amount,
        recovered_amount=claim.recovered_amount,
        patient_responsibility=claim.patient_responsibility,
        pay_status=claim.pay_status,
        check_status=claim.check_status,
        cashed_date=claim.cashed_date,
        payment_posted_date=claim.payment_posted_date,
        eob=EobOut(file_name=claim.eob_file_name, uploaded_at=claim.eob_uploaded_at)
        if claim.eob_file_name and claim.eob_uploaded_at
        else None,
        review_reason=claim.review_reason,
        notes=[
            NoteOut(
                id=n.id,
                body=n.body,
                created_at=n.created_at,
                author=PersonRef(id=n.author_user_id, name=authors.get(n.author_user_id, ("Unknown", ""))[0]),
            )
            for n in notes
        ],
        can_work=ctx.can("claims.work"),
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


async def update(ctx: Ctx, claim_id: uuid.UUID, body: ClaimUpdate) -> ClaimDetail:
    claim = await load_visible(ctx, claim_id)
    sent = body.model_fields_set
    allowed = await active_values(ctx.db)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in LIST_FIELDS:
        if field not in sent:
            continue
        value = getattr(body, field)
        # A retired option may stay on a claim that already has it, but can't be newly chosen.
        if value is not None and value not in allowed[field] and value != getattr(claim, field):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"“{value}” isn't an option for {field.replace('_', ' ')}."
            )

    if "assigned_user_id" in sent and body.assigned_user_id not in (None, claim.assigned_user_id):
        options = {user_id for user_id, _, _ in await repository.assignees(ctx.db, claim.practice_id)}
        if body.assigned_user_id not in options:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Claims can only be assigned to active AR staff of this practice.",
            )

    for field in sent:
        new = getattr(body, field)
        if field == "needs_review":
            new = False
        old = getattr(claim, field)
        if old != new:
            before[field], after[field] = _plain(old), _plain(new)
            setattr(claim, field, new)

    if after:
        assignment = {"assigned_user_id"} & after.keys()
        work = after.keys() - assignment - {"needs_review"}
        if work:
            audit.record(
                ctx.db,
                action="claim.updated",
                entity_type="claim",
                entity_id=claim.id,
                actor_user_id=ctx.user.id,
                practice_id=claim.practice_id,
                before={k: before[k] for k in work},
                after={k: after[k] for k in work},
            )
        if assignment:
            audit.record(
                ctx.db,
                action="claim.assigned",
                entity_type="claim",
                entity_id=claim.id,
                actor_user_id=ctx.user.id,
                practice_id=claim.practice_id,
                before={"assigned_user_id": before["assigned_user_id"]},
                after={"assigned_user_id": after["assigned_user_id"]},
            )
        if "needs_review" in after:
            audit.record(
                ctx.db,
                action="claim.reviewed",
                entity_type="claim",
                entity_id=claim.id,
                actor_user_id=ctx.user.id,
                practice_id=claim.practice_id,
            )
        claim.updated_at = datetime.now(UTC)
        await ctx.db.commit()
        await ctx.db.refresh(claim)
    return await detail(ctx, claim)


async def add_note(ctx: Ctx, claim_id: uuid.UUID, body: str) -> ClaimDetail:
    claim = await load_visible(ctx, claim_id)
    ctx.db.add(ClaimNote(claim_id=claim.id, author_user_id=ctx.user.id, body=body))
    audit.record(
        ctx.db,
        action="claim.note_added",
        entity_type="claim",
        entity_id=claim.id,
        actor_user_id=ctx.user.id,
        practice_id=claim.practice_id,
        after={"characters": len(body)},
    )
    await ctx.db.commit()
    return await detail(ctx, claim)


async def attach_eob(ctx: Ctx, claim_id: uuid.UUID, file: UploadFile) -> ClaimDetail:
    claim = await load_visible(ctx, claim_id)
    name = PurePath(file.filename or "eob").name
    extension = PurePath(name).suffix.lower()
    if extension not in EOB_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Attach the EOB as a PDF or an image (PNG, JPG, WEBP)."
        )
    data = await file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The EOB file is larger than 4 MB.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The EOB file is empty.")
    key = f"claims/{claim.id}/eob/{uuid.uuid4().hex}{extension}"
    get_storage().save(key, data)
    previous = claim.eob_file_name
    claim.eob_storage_key, claim.eob_file_name, claim.eob_uploaded_at = key, name, datetime.now(UTC)
    audit.record(
        ctx.db,
        action="claim.eob_attached",
        entity_type="claim",
        entity_id=claim.id,
        actor_user_id=ctx.user.id,
        practice_id=claim.practice_id,
        before={"file_name": previous} if previous else None,
        after={"file_name": name},
    )
    await ctx.db.commit()
    await ctx.db.refresh(claim)
    return await detail(ctx, claim)


async def read_eob(ctx: Ctx, claim_id: uuid.UUID) -> tuple[bytes, str, str]:
    claim = await load_visible(ctx, claim_id)
    if not claim.eob_storage_key or not claim.eob_file_name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This claim has no EOB attached.")
    data = get_storage().read(claim.eob_storage_key)
    audit.record(
        ctx.db,
        action="claim.eob_downloaded",
        entity_type="claim",
        entity_id=claim.id,
        actor_user_id=ctx.user.id,
        practice_id=claim.practice_id,
    )
    await ctx.db.commit()
    extension = PurePath(claim.eob_file_name).suffix.lower()
    return data, claim.eob_file_name, EOB_TYPES.get(extension, "application/octet-stream")
