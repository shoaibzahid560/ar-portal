"""
Turns an uploaded AR sheet into claims.

Each line gets a fingerprint from its practice, patient, service date, subscriber ID, payer and billed
amount. A line whose fingerprint already exists is the same claim uploaded again and is skipped, so
uploading next week's sheet doesn't duplicate the lines carried over. Identical lines within one file are
numbered (first, second, ...) so genuine repeats are all kept. A new line for a patient, subscriber and
service date that already has a claim is created but marked "needs review": it may be a changed amount
on an existing claim. Proper matching of changed lines arrives with M2.
"""

import hashlib
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import PurePath

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core import audit
from app.core.clock import business_today
from app.core.config import get_settings
from app.core.context import Ctx
from app.core.schemas import NamedRef
from app.core.scope import Scope, get_scope
from app.core.storage import get_storage
from app.modules.claims.models import Claim
from app.modules.claims.schemas import claim_label
from app.modules.notifications import service as notify
from app.modules.practices.models import Practice
from app.modules.uploads.models import Upload, UploadError
from app.modules.uploads.parser import ParsedRow, SheetError, parse_sheet
from app.modules.uploads.schemas import RowErrorOut, UploadDetail, UploadOut, upload_label
from app.modules.users.models import User


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def fingerprint(practice_id: uuid.UUID, row: ParsedRow, occurrence: int) -> str:
    parts = [
        str(practice_id),
        _norm(row.patient_name),
        row.service_date.isoformat(),
        row.subscriber_id,
        _norm(row.insurance_carrier),
        f"{row.billed:.2f}",
        str(occurrence),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def similar_key(row_patient: str, service_date: object, subscriber_id: str) -> tuple[str, str, str]:
    return _norm(row_patient), str(service_date), subscriber_id


def visible_uploads(statement, scope: Scope):  # type: ignore[no-untyped-def]
    return statement if scope.company_wide else statement.where(Upload.practice_id.in_(scope.practice_ids))


async def to_out(ctx: Ctx, uploads: list[Upload]) -> list[UploadOut]:
    practice_ids = {u.practice_id for u in uploads}
    user_ids = {u.uploaded_by for u in uploads}
    practices = (
        dict(
            (
                await ctx.db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(practice_ids)))
            ).all()
        )
        if practice_ids
        else {}
    )
    users = (
        dict((await ctx.db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))).all())
        if user_ids
        else {}
    )
    return [
        UploadOut(
            id=u.id,
            number=upload_label(u.number),
            practice=NamedRef(id=u.practice_id, name=practices.get(u.practice_id, "")),
            uploaded_by=NamedRef(id=u.uploaded_by, name=users.get(u.uploaded_by, "")),
            file_name=u.file_name,
            file_size=u.file_size,
            status=u.status,
            failure_reason=u.failure_reason,
            total_rows=u.total_rows,
            created_claims=u.created_claims,
            duplicate_rows=u.duplicate_rows,
            error_rows=u.error_rows,
            review_rows=u.review_rows,
            created_at=u.created_at,
            completed_at=u.completed_at,
        )
        for u in uploads
    ]


async def detail(ctx: Ctx, upload: Upload) -> UploadDetail:
    [base] = await to_out(ctx, [upload])
    errors = await ctx.db.scalars(
        select(UploadError)
        .where(UploadError.upload_id == upload.id)
        .order_by(UploadError.row_number, UploadError.id)
    )
    return UploadDetail(
        **base.model_dump(),
        errors=[
            RowErrorOut(row_number=e.row_number, column=e.column_name, message=e.message) for e in errors
        ],
    )


async def load_visible(ctx: Ctx, upload_id: uuid.UUID) -> Upload:
    upload = await ctx.db.scalar(
        visible_uploads(select(Upload).where(Upload.id == upload_id), await get_scope(ctx))
    )
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found.")
    return upload


async def create_upload(ctx: Ctx, practice_id: uuid.UUID, file_name: str, data: bytes) -> UploadDetail:
    scope = await get_scope(ctx)
    practice = await ctx.db.get(Practice, practice_id)
    if practice is None or (not scope.company_wide and practice_id not in scope.practice_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only upload for practices assigned to you.")
    if practice.status != "active":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This practice is paused. Make it active before uploading."
        )
    name = PurePath(file_name or "upload").name
    if PurePath(name).suffix.lower() not in (".xlsx", ".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload an .xlsx or .csv file.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 4 MB.")

    checksum = hashlib.sha256(data).hexdigest()
    earlier = await ctx.db.scalar(
        select(Upload).where(
            Upload.practice_id == practice_id, Upload.checksum == checksum, Upload.status == "completed"
        )
    )
    if earlier is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This exact file was already uploaded as {upload_label(earlier.number)} "
            f"on {earlier.created_at:%d %b %Y}.",
        )

    upload = Upload(
        practice_id=practice_id,
        uploaded_by=ctx.user.id,
        file_name=name,
        storage_key="",
        file_size=len(data),
        checksum=checksum,
        status="processing",
    )
    ctx.db.add(upload)
    await ctx.db.flush()
    upload.storage_key = f"uploads/{practice_id}/{upload.id}/{name}"
    get_storage().save(upload.storage_key, data)

    try:
        result = parse_sheet(data, name, today=business_today())
    except SheetError as error:
        upload.status, upload.failure_reason = "failed", str(error)
        upload.completed_at = datetime.now(UTC)
        audit.record(
            ctx.db,
            action="upload.failed",
            entity_type="upload",
            entity_id=upload.id,
            actor_user_id=ctx.user.id,
            practice_id=practice_id,
            after={"file_name": name, "reason": str(error)},
        )
        label = upload_label(upload.number)
        notify.send(
            ctx.db,
            {ctx.user.id} | await notify.oversight(ctx.db),
            kind="upload.failed",
            title=f"{label} for {practice.name} failed",
            body=str(error),
            link=f"/uploads/{upload.id}",
        )
        await ctx.db.commit()
        await ctx.db.refresh(upload)
        return await detail(ctx, upload)

    await _create_claims(ctx, upload, result.rows)
    ctx.db.add_all(
        UploadError(upload_id=upload.id, row_number=p.row_number, column_name=p.column, message=p.message)
        for p in result.problems
    )
    upload.total_rows = result.total_rows
    upload.error_rows = len({p.row_number for p in result.problems})
    upload.status = "completed"
    upload.completed_at = datetime.now(UTC)
    audit.record(
        ctx.db,
        action="upload.completed",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=practice_id,
        after={
            "file_name": name,
            "total_rows": upload.total_rows,
            "created_claims": upload.created_claims,
            "duplicate_rows": upload.duplicate_rows,
            "error_rows": upload.error_rows,
            "review_rows": upload.review_rows,
        },
    )
    await _notify_completed(ctx, upload, practice.name)
    await ctx.db.commit()
    await ctx.db.refresh(upload)
    return await detail(ctx, upload)


async def _notify_completed(ctx: Ctx, upload: Upload, practice_name: str) -> None:
    label, link = upload_label(upload.number), f"/uploads/{upload.id}"
    summary = (
        f"{upload.created_claims} new, {upload.duplicate_rows} already in the system, "
        f"{upload.error_rows} with errors, {upload.review_rows} need review"
    )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="upload.completed",
        title=f"{label} uploaded for {practice_name}",
        body=summary,
        link=link,
        actor=ctx.user.id,
    )
    if upload.error_rows:
        # The uploader is told even though they made the upload: this is something they need to fix.
        notify.send(
            ctx.db,
            {ctx.user.id},
            kind="upload.errors",
            title=f"{label}: {upload.error_rows} row(s) with errors",
            body="Download the error report, fix the rows and upload them again.",
            link=link,
        )
    if upload.review_rows:
        notify.send(
            ctx.db,
            await notify.practice_reviewers(ctx.db, upload.practice_id) | {ctx.user.id},
            kind="review.waiting",
            title=f"{upload.review_rows} line(s) from {label} need review",
            body=f"{practice_name}: possible changes to claims already in the system.",
            link="/review?view=open",
        )


async def _create_claims(ctx: Ctx, upload: Upload, rows: list[ParsedRow]) -> None:
    practice_id = upload.practice_id
    seen: Counter[str] = Counter()
    prints: list[tuple[ParsedRow, str]] = []
    for row in rows:
        base = fingerprint(practice_id, row, 0)
        seen[base] += 1
        prints.append((row, fingerprint(practice_id, row, seen[base])))

    existing = set(
        await ctx.db.scalars(
            select(Claim.fingerprint).where(
                Claim.practice_id == practice_id, Claim.fingerprint.in_([p for _, p in prints])
            )
        )
    )
    similar: dict[tuple[str, str, str], int] = {}
    for patient, service_date, subscriber_id, number in await ctx.db.execute(
        select(Claim.patient_name, Claim.service_date, Claim.subscriber_id, func.min(Claim.number))
        .where(Claim.practice_id == practice_id)
        .group_by(Claim.patient_name, Claim.service_date, Claim.subscriber_id)
    ):
        similar.setdefault(similar_key(patient, service_date, subscriber_id), number)

    new_claims: list[Claim] = []
    for row, print_ in prints:
        if print_ in existing:
            upload.duplicate_rows += 1
            continue
        match = similar.get(similar_key(row.patient_name, row.service_date, row.subscriber_id))
        claim = Claim(
            practice_id=practice_id,
            upload_id=upload.id,
            fingerprint=print_,
            patient_name=row.patient_name,
            service_date=row.service_date,
            subscriber_id=row.subscriber_id,
            patient_dob=row.patient_dob,
            insurance_carrier=row.insurance_carrier,
            subscriber_name=row.subscriber_name,
            subscriber_dob=row.subscriber_dob,
            billed=row.billed,
            needs_review=match is not None,
            review_reason=(
                f"An earlier upload already has a claim for this patient, subscriber and service date "
                f"({claim_label(match)}). Check whether this line is new or a change to that claim."
            )
            if match is not None
            else None,
        )
        new_claims.append(claim)
    ctx.db.add_all(new_claims)
    await ctx.db.flush()
    upload.created_claims = len(new_claims)
    upload.review_rows = sum(1 for c in new_claims if c.needs_review)
    for claim in new_claims:
        audit.record(
            ctx.db,
            action="claim.imported",
            entity_type="claim",
            entity_id=claim.id,
            actor_user_id=ctx.user.id,
            practice_id=practice_id,
            after={"upload": upload_label(upload.number), "needs_review": claim.needs_review},
        )
