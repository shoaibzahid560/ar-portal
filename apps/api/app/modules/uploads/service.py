"""
Import batches (Roles & Access specification, section 6):

1. Upload: an importer chooses an authorised practice and uploads the AR sheet. A file-name check warns when
   the sheet seems to belong to a different practice.
2. Validate and preview: nothing is created yet. Each valid line is classified:
   - new:       no claim for it yet
   - duplicate: exactly this line is already in the system (skipped)
   - changed:   the same patient, subscriber ID and service date already has a claim, with different values
   - repeat:    an identical line earlier in the same file
3. Decide: for changed and repeated lines a reviewer chooses update an existing claim, create a new claim,
   or skip. Nothing is merged or overwritten silently.
4. Submit, then approve and commit by a second person: claims are created (new IDs only for confirmed new
   claims) or updated (existing IDs kept). Rejected or discarded batches create nothing.
5. Reverse: a committed batch can be undone while none of its claims has been worked.

A line's fingerprint comes from its practice, patient, service date, subscriber ID, payer, billed amount, and
how many identical lines precede it in the file. Fingerprints of committed lines are kept (on the claim, or as
a claim print when a line updated an existing claim), so the same line in a later sheet is recognised.
"""

import hashlib
import re
import uuid
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update

from app.core import audit
from app.core.access import users_with
from app.core.clock import business_today
from app.core.config import get_settings
from app.core.context import Ctx
from app.core.schemas import NamedRef
from app.core.storage import get_storage
from app.modules.claims.models import Claim, ClaimNote, ClaimPrint
from app.modules.claims.schemas import claim_label
from app.modules.notifications import service as notify
from app.modules.practices.models import Practice
from app.modules.uploads.models import Upload, UploadError, UploadRow
from app.modules.uploads.parser import ParsedRow, SheetError, parse_sheet
from app.modules.uploads.schemas import (
    Candidate,
    RowErrorOut,
    UploadActions,
    UploadDetail,
    UploadOut,
    UploadRowOut,
    upload_label,
)
from app.modules.users.models import User

# The uploaded values of a claim, in the AR sheet's order.
UPLOAD_FIELDS = (
    "patient_name",
    "service_date",
    "subscriber_id",
    "patient_dob",
    "insurance_carrier",
    "subscriber_name",
    "subscriber_dob",
    "billed",
)
# Work recorded on a claim. A batch whose claims have any of this can't be reversed.
WORK_FIELDS = (
    "allowed_amount",
    "recovered_amount",
    "patient_responsibility",
    "claim_status",
    "pay_status",
    "check_status",
    "cashed_date",
    "action_taken",
    "payment_posted_date",
    "followup_date",
    "eob_storage_key",
    "assigned_user_id",
)
OPEN_STATUSES = ("preview", "submitted")


def _now() -> datetime:
    return datetime.now(UTC)


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def _code(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


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


def visit_key(patient: str, service_date: object, subscriber_id: str) -> tuple[str, str, str]:
    return _norm(patient), str(service_date), subscriber_id


def _values(row: ParsedRow) -> dict[str, Any]:
    """A line's values in plain JSON form, for the preview."""
    return {
        "patient_name": row.patient_name,
        "service_date": row.service_date.isoformat(),
        "subscriber_id": row.subscriber_id,
        "patient_dob": row.patient_dob.isoformat() if row.patient_dob else None,
        "insurance_carrier": row.insurance_carrier,
        "subscriber_name": row.subscriber_name,
        "subscriber_dob": row.subscriber_dob.isoformat() if row.subscriber_dob else None,
        "billed": f"{row.billed:.2f}",
    }


def _claim_values(claim: Claim) -> dict[str, Any]:
    return {
        field: (
            value.isoformat()
            if isinstance(value, date)
            else f"{value:.2f}"
            if isinstance(value, Decimal)
            else value
        )
        for field in UPLOAD_FIELDS
        if (value := getattr(claim, field)) is not None or True
    }


def _typed(values: dict[str, Any]) -> dict[str, Any]:
    """Preview values back to claim column types."""
    out: dict[str, Any] = {}
    for field in UPLOAD_FIELDS:
        value = values.get(field)
        if value is None:
            out[field] = None
        elif field in ("service_date", "patient_dob", "subscriber_dob"):
            out[field] = date.fromisoformat(value)
        elif field == "billed":
            out[field] = Decimal(value)
        else:
            out[field] = value
    return out


# ---- Visibility and lookups ---------------------------------------------------------------------------


def visible_uploads(statement, ctx: Ctx):  # type: ignore[no-untyped-def]
    """Uploads of the practices where the person holds uploads.view, plus the person's own uploads."""
    practices = ctx.access.practices_with("uploads.view")
    if practices is None:
        return statement
    return statement.where(or_(Upload.practice_id.in_(practices), Upload.uploaded_by == ctx.user.id))


async def load_visible(ctx: Ctx, upload_id: uuid.UUID) -> Upload:
    upload = await ctx.db.scalar(visible_uploads(select(Upload).where(Upload.id == upload_id), ctx))
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found.")
    return upload


async def _known_prints(ctx: Ctx, practice_id: uuid.UUID, prints: list[str]) -> dict[str, uuid.UUID]:
    """Fingerprints already in the system, and the claim each belongs to."""
    if not prints:
        return {}
    known = dict(
        (
            await ctx.db.execute(
                select(Claim.fingerprint, Claim.id).where(
                    Claim.practice_id == practice_id, Claim.fingerprint.in_(prints)
                )
            )
        ).all()
    )
    known.update(
        (
            await ctx.db.execute(
                select(ClaimPrint.fingerprint, ClaimPrint.claim_id).where(
                    ClaimPrint.practice_id == practice_id, ClaimPrint.fingerprint.in_(prints)
                )
            )
        ).all()
    )
    return known


async def _visits(ctx: Ctx, practice_id: uuid.UUID) -> dict[tuple[str, str, str], list[uuid.UUID]]:
    """Active claims of the practice, grouped by patient, service date and subscriber ID."""
    visits: dict[tuple[str, str, str], list[uuid.UUID]] = {}
    rows = await ctx.db.execute(
        select(Claim.id, Claim.patient_name, Claim.service_date, Claim.subscriber_id)
        .where(Claim.practice_id == practice_id, Claim.merged_into_id.is_(None), Claim.withdrawn_at.is_(None))
        .order_by(Claim.number)
    )
    for claim_id, patient, service_date, subscriber_id in rows:
        visits.setdefault(visit_key(patient, service_date, subscriber_id), []).append(claim_id)
    return visits


# ---- Output -----------------------------------------------------------------------------------------


async def _undecided(ctx: Ctx, upload_id: uuid.UUID) -> int:
    return (
        await ctx.db.scalar(
            select(func.count())
            .select_from(UploadRow)
            .where(
                UploadRow.upload_id == upload_id,
                UploadRow.classification.in_(("changed", "repeat")),
                UploadRow.decision.is_(None),
            )
        )
        or 0
    )


async def to_out(ctx: Ctx, uploads: list[Upload]) -> list[UploadOut]:
    practice_ids = {u.practice_id for u in uploads}
    people_ids = {
        p
        for u in uploads
        for p in (u.uploaded_by, u.submitted_by, u.decided_by, u.reversed_by)
        if p is not None
    }
    practices = (
        dict(
            (
                await ctx.db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(practice_ids)))
            ).all()
        )
        if practice_ids
        else {}
    )
    people = (
        dict((await ctx.db.execute(select(User.id, User.full_name).where(User.id.in_(people_ids)))).all())
        if people_ids
        else {}
    )
    undecided: dict[uuid.UUID, int] = {}
    open_ids = [u.id for u in uploads if u.status in OPEN_STATUSES]
    if open_ids:
        undecided = dict(
            (
                await ctx.db.execute(
                    select(UploadRow.upload_id, func.count())
                    .where(
                        UploadRow.upload_id.in_(open_ids),
                        UploadRow.classification.in_(("changed", "repeat")),
                        UploadRow.decision.is_(None),
                    )
                    .group_by(UploadRow.upload_id)
                )
            ).all()
        )

    def ref(person: uuid.UUID | None) -> NamedRef | None:
        return NamedRef(id=person, name=people.get(person, "")) if person else None

    return [
        UploadOut(
            id=u.id,
            number=upload_label(u.number),
            practice=NamedRef(id=u.practice_id, name=practices.get(u.practice_id, "")),
            uploaded_by=NamedRef(id=u.uploaded_by, name=people.get(u.uploaded_by, "")),
            file_name=u.file_name,
            file_size=u.file_size,
            status=u.status,
            failure_reason=u.failure_reason,
            mapping_warning=u.mapping_warning,
            total_rows=u.total_rows,
            new_rows=u.new_rows,
            duplicate_rows=u.duplicate_rows,
            changed_rows=u.changed_rows,
            repeat_rows=u.repeat_rows,
            error_rows=u.error_rows,
            undecided_rows=undecided.get(u.id, 0),
            created_claims=u.created_claims,
            updated_claims=u.updated_claims,
            skipped_rows=u.skipped_rows,
            review_rows=u.review_rows,
            created_at=u.created_at,
            completed_at=u.completed_at,
            submitted_by=ref(u.submitted_by),
            submitted_at=u.submitted_at,
            decided_by=ref(u.decided_by),
            decided_at=u.decided_at,
            decision_reason=u.decision_reason,
            reversed_by=ref(u.reversed_by),
            reversed_at=u.reversed_at,
            reverse_reason=u.reverse_reason,
        )
        for u in uploads
    ]


def _commit_blocker(ctx: Ctx, upload: Upload, undecided: int) -> str | None:
    if upload.status != "submitted":
        return "Only submitted uploads can be committed." if upload.status == "preview" else None
    if ctx.user.id in (upload.uploaded_by, upload.submitted_by):
        return "Someone other than the person who uploaded or submitted it must approve it."
    if undecided:
        return f"{undecided} line(s) still need a decision."
    return None


async def detail(ctx: Ctx, upload: Upload) -> UploadDetail:
    [base] = await to_out(ctx, [upload])
    errors = await ctx.db.scalars(
        select(UploadError)
        .where(UploadError.upload_id == upload.id)
        .order_by(UploadError.row_number, UploadError.id)
    )
    practice = upload.practice_id
    is_open = upload.status in OPEN_STATUSES
    undecided = base.undecided_rows
    blocker = _commit_blocker(ctx, upload, undecided)
    may_commit = ctx.access.has("uploads.commit", practice)
    actions = UploadActions(
        can_submit=upload.status == "preview" and ctx.access.has("uploads.create", practice),
        can_discard=is_open and (ctx.user.id == upload.uploaded_by or may_commit),
        can_decide=is_open and ctx.access.has("claims.review", practice),
        can_commit=upload.status == "submitted" and may_commit and blocker is None,
        can_reject=upload.status == "submitted" and may_commit and ctx.user.id != upload.uploaded_by,
        can_reverse=upload.status == "committed" and ctx.access.has("uploads.reverse", practice),
        commit_blocked_because=blocker if may_commit else None,
    )
    return UploadDetail(
        **base.model_dump(),
        errors=[
            RowErrorOut(row_number=e.row_number, column=e.column_name, message=e.message) for e in errors
        ],
        actions=actions,
    )


async def rows_out(ctx: Ctx, upload: Upload, classification: str | None) -> list[UploadRowOut]:
    statement = select(UploadRow).where(UploadRow.upload_id == upload.id)
    if classification == "needs-decision":
        statement = statement.where(UploadRow.classification.in_(("changed", "repeat")))
    elif classification:
        statement = statement.where(UploadRow.classification == classification)
    rows = list(await ctx.db.scalars(statement.order_by(UploadRow.row_number)))

    claim_ids = {uuid.UUID(c) for r in rows for c in r.match_claim_ids} | {
        r.result_claim_id for r in rows if r.result_claim_id
    }
    claims = (
        {c.id: c for c in await ctx.db.scalars(select(Claim).where(Claim.id.in_(claim_ids)))}
        if claim_ids
        else {}
    )
    deciders_ids = {r.decided_by for r in rows if r.decided_by}
    people_ids = deciders_ids | {c.assigned_user_id for c in claims.values() if c.assigned_user_id}
    people = (
        dict((await ctx.db.execute(select(User.id, User.full_name).where(User.id.in_(people_ids)))).all())
        if people_ids
        else {}
    )
    out = []
    for r in rows:
        candidates = [
            Candidate(
                id=c.id,
                number=claim_label(c.number),
                values=_claim_values(c),
                claim_status=c.claim_status,
                assigned_to=people.get(c.assigned_user_id) if c.assigned_user_id else None,
            )
            for claim_id in r.match_claim_ids
            if (c := claims.get(uuid.UUID(claim_id))) is not None
        ]
        result = claims.get(r.result_claim_id) if r.result_claim_id else None
        out.append(
            UploadRowOut(
                id=r.id,
                row_number=r.row_number,
                classification=r.classification,  # type: ignore[arg-type]
                values=r.data,
                candidates=candidates,
                decision=r.decision,  # type: ignore[arg-type]
                target_claim_id=r.target_claim_id,
                decided_by=people.get(r.decided_by) if r.decided_by else None,
                result_claim=NamedRef(id=result.id, name=claim_label(result.number)) if result else None,
            )
        )
    return out


# ---- 1 and 2: upload, validate, preview -------------------------------------------------------------------


async def _check_practice_mapping(ctx: Ctx, practice: Practice, file_name: str) -> str | None:
    """
    Blocks a file whose name names a different practice; warns when it names none. Matching ignores case,
    spaces and punctuation, and uses each practice's import code, or its name when no code is set.
    """
    name = _code(PurePath(file_name).stem)
    own = _code(practice.import_code or practice.name)
    others = await ctx.db.scalars(select(Practice).where(Practice.id != practice.id))
    for other in others:
        code = _code(other.import_code or other.name)
        # Very short codes would match by accident, so they're not used to block.
        if len(code) >= 4 and code in name and not (own and own in name):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"This file name looks like {other.name}'s sheet. Choose that practice, or check the file.",
            )
    if own and own not in name:
        return (
            f"The file name doesn't mention {practice.name}. "
            f"Check this is {practice.name}'s sheet before submitting."
        )
    return None


async def create_upload(ctx: Ctx, practice_id: uuid.UUID, file_name: str, data: bytes) -> UploadDetail:
    practice = await ctx.db.get(Practice, practice_id)
    if practice is None or not ctx.access.has("uploads.create", practice_id):
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
    mapping_warning = await _check_practice_mapping(ctx, practice, name)

    checksum = hashlib.sha256(data).hexdigest()
    earlier = await ctx.db.scalar(
        select(Upload).where(
            Upload.practice_id == practice_id,
            Upload.checksum == checksum,
            Upload.status.in_((*OPEN_STATUSES, "committed")),
        )
    )
    if earlier is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This exact file was already uploaded as {upload_label(earlier.number)} "
            f"on {earlier.created_at:%d %b %Y} ({earlier.status}).",
        )

    upload = Upload(
        practice_id=practice_id,
        uploaded_by=ctx.user.id,
        file_name=name,
        storage_key="",
        file_size=len(data),
        checksum=checksum,
        status="processing",
        mapping_warning=mapping_warning,
    )
    ctx.db.add(upload)
    await ctx.db.flush()
    upload.storage_key = f"uploads/{practice_id}/{upload.id}/{name}"
    get_storage().save(upload.storage_key, data)
    label = upload_label(upload.number)

    try:
        result = parse_sheet(data, name, today=business_today())
    except SheetError as error:
        upload.status, upload.failure_reason, upload.completed_at = "failed", str(error), _now()
        audit.record(
            ctx.db,
            action="upload.failed",
            entity_type="upload",
            entity_id=upload.id,
            actor_user_id=ctx.user.id,
            practice_id=practice_id,
            after={"file_name": name, "reason": str(error)},
        )
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

    await _stage_rows(ctx, upload, result.rows)
    ctx.db.add_all(
        UploadError(upload_id=upload.id, row_number=p.row_number, column_name=p.column, message=p.message)
        for p in result.problems
    )
    upload.total_rows = result.total_rows
    upload.error_rows = len({p.row_number for p in result.problems})
    upload.status = "preview"
    audit.record(
        ctx.db,
        action="upload.previewed",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=practice_id,
        after={
            "file_name": name,
            "total_rows": upload.total_rows,
            "new_rows": upload.new_rows,
            "duplicate_rows": upload.duplicate_rows,
            "changed_rows": upload.changed_rows,
            "repeat_rows": upload.repeat_rows,
            "error_rows": upload.error_rows,
        },
    )
    if upload.error_rows:
        notify.send(
            ctx.db,
            {ctx.user.id},
            kind="upload.errors",
            title=f"{label}: {upload.error_rows} row(s) with errors",
            body="Download the error report, fix the rows and upload them again.",
            link=f"/uploads/{upload.id}",
        )
    await ctx.db.commit()
    await ctx.db.refresh(upload)
    return await detail(ctx, upload)


async def _stage_rows(ctx: Ctx, upload: Upload, rows: list[ParsedRow]) -> None:
    practice_id = upload.practice_id
    seen: Counter[str] = Counter()
    staged: list[tuple[ParsedRow, str, int]] = []
    for row in rows:
        base = fingerprint(practice_id, row, 0)
        seen[base] += 1
        staged.append((row, fingerprint(practice_id, row, seen[base]), seen[base]))
    known = await _known_prints(ctx, practice_id, [p for _, p, _ in staged])
    visits = await _visits(ctx, practice_id)

    for row, print_, occurrence in staged:
        if print_ in known:
            classification, matches = "duplicate", [str(known[print_])]
        elif occurrence > 1:
            classification, matches = "repeat", []
        elif (key := visit_key(row.patient_name, row.service_date, row.subscriber_id)) in visits:
            classification, matches = "changed", [str(c) for c in visits[key]]
        else:
            classification, matches = "new", []
        ctx.db.add(
            UploadRow(
                upload_id=upload.id,
                row_number=row.row_number,
                classification=classification,
                data=_values(row),
                fingerprint=print_,
                match_claim_ids=matches,
            )
        )
        setattr(upload, f"{classification}_rows", getattr(upload, f"{classification}_rows") + 1)


# ---- 3: decide ---------------------------------------------------------------------------------------------


async def decide_row(
    ctx: Ctx, upload_id: uuid.UUID, row_id: int, decision: str, target_claim_id: uuid.UUID | None
) -> UploadRowOut:
    upload = await load_visible(ctx, upload_id)
    if not ctx.access.has("claims.review", upload.practice_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required in this practice: claims.review")
    if upload.status not in OPEN_STATUSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Decisions can only change before the upload is committed."
        )
    row = await ctx.db.scalar(
        select(UploadRow).where(UploadRow.id == row_id, UploadRow.upload_id == upload.id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found.")
    allowed = {"changed": {"update", "create", "skip"}, "repeat": {"create", "skip"}}.get(
        row.classification, set()
    )
    if decision not in allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This line doesn't take that decision.")
    if decision == "update":
        if target_claim_id is None or str(target_claim_id) not in row.match_claim_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose which existing claim this line updates.")
    else:
        target_claim_id = None
    row.decision, row.target_claim_id, row.decided_by, row.decided_at = (
        decision,
        target_claim_id,
        ctx.user.id,
        _now(),
    )
    audit.record(
        ctx.db,
        action="upload.line_decided",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=upload.practice_id,
        after={
            "row": row.row_number,
            "decision": decision,
            "target_claim_id": str(target_claim_id) if target_claim_id else None,
        },
    )
    await ctx.db.commit()
    [out] = [r for r in await rows_out(ctx, upload, None) if r.id == row.id]
    return out


# ---- 4: submit, approve and commit, reject, discard -------------------------------------------------


async def _require_status(upload: Upload, *allowed: str) -> None:
    if upload.status not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"This upload is {upload.status}; that isn't possible now."
        )


async def submit(ctx: Ctx, upload_id: uuid.UUID) -> UploadDetail:
    upload = await load_visible(ctx, upload_id)
    await _require_status(upload, "preview")
    if not ctx.access.has("uploads.create", upload.practice_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required in this practice: uploads.create")
    upload.status, upload.submitted_by, upload.submitted_at = "submitted", ctx.user.id, _now()
    audit.record(
        ctx.db,
        action="upload.submitted",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=upload.practice_id,
    )
    practice = await ctx.db.get(Practice, upload.practice_id)
    undecided = await _undecided(ctx, upload.id)
    notify.send(
        ctx.db,
        await users_with(ctx.db, "uploads.commit", upload.practice_id) - {upload.uploaded_by},
        kind="upload.awaiting_approval",
        title=(
            f"{upload_label(upload.number)} for {practice.name if practice else 'a practice'} "
            "is waiting for approval"
        ),
        body=f"{upload.new_rows} new line(s); {undecided} need a decision."
        if undecided
        else f"{upload.new_rows} new line(s).",
        link=f"/uploads/{upload.id}",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(upload)
    return await detail(ctx, upload)


async def _clear_preview(ctx: Ctx, upload: Upload) -> None:
    """The preview held patient details only for the decision; once decided they aren't kept twice."""
    await ctx.db.execute(update(UploadRow).where(UploadRow.upload_id == upload.id).values(data=None))


async def discard(ctx: Ctx, upload_id: uuid.UUID) -> UploadDetail:
    upload = await load_visible(ctx, upload_id)
    await _require_status(upload, *OPEN_STATUSES)
    if ctx.user.id != upload.uploaded_by and not ctx.access.has("uploads.commit", upload.practice_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the person who uploaded it, or an approver, can discard it."
        )
    upload.status, upload.decided_by, upload.decided_at = "discarded", ctx.user.id, _now()
    await _clear_preview(ctx, upload)
    audit.record(
        ctx.db,
        action="upload.discarded",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=upload.practice_id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(upload)
    return await detail(ctx, upload)


async def reject(ctx: Ctx, upload_id: uuid.UUID, reason: str | None) -> UploadDetail:
    upload = await load_visible(ctx, upload_id)
    await _require_status(upload, "submitted")
    if not ctx.access.has("uploads.commit", upload.practice_id) or ctx.user.id == upload.uploaded_by:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A second person with approval rights must decide this upload."
        )
    upload.status, upload.decided_by, upload.decided_at, upload.decision_reason = (
        "rejected",
        ctx.user.id,
        _now(),
        reason,
    )
    await _clear_preview(ctx, upload)
    audit.record(
        ctx.db,
        action="upload.rejected",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=upload.practice_id,
        after={"reason": reason},
    )
    notify.send(
        ctx.db,
        {upload.uploaded_by, upload.submitted_by},
        kind="upload.rejected",
        title=f"{ctx.user.full_name} turned down {upload_label(upload.number)}",
        body=reason,
        link=f"/uploads/{upload.id}",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(upload)
    return await detail(ctx, upload)


async def commit(ctx: Ctx, upload_id: uuid.UUID) -> UploadDetail:
    upload = await load_visible(ctx, upload_id)
    await _require_status(upload, "submitted")
    if not ctx.access.has("uploads.commit", upload.practice_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required in this practice: uploads.commit")
    blocker = _commit_blocker(ctx, upload, await _undecided(ctx, upload.id))
    if blocker:
        code = status.HTTP_403_FORBIDDEN if "Someone other" in blocker else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, blocker)

    practice_id = upload.practice_id
    rows = list(
        await ctx.db.scalars(
            select(UploadRow).where(UploadRow.upload_id == upload.id).order_by(UploadRow.row_number)
        )
    )
    # Another batch may have been committed since the preview: check again, so nothing is created twice.
    known = await _known_prints(ctx, practice_id, [r.fingerprint for r in rows])
    targets = {
        c.id: c
        for c in await ctx.db.scalars(
            select(Claim).where(Claim.id.in_([r.target_claim_id for r in rows if r.target_claim_id]))
        )
    }
    stale = [
        r.row_number
        for r in rows
        if r.decision == "update"
        and ((t := targets.get(r.target_claim_id)) is None or t.merged_into_id or t.withdrawn_at)
    ]
    if stale:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The claim chosen for row(s) {', '.join(map(str, stale))} is no longer available. "
            "Decide those lines again.",
        )

    created: list[tuple[UploadRow, Claim]] = []
    now = _now()
    for row in rows:
        wants_new = row.classification == "new" or (
            row.classification in ("changed", "repeat") and row.decision == "create"
        )
        if row.classification == "duplicate" or row.decision == "skip":
            upload.skipped_rows += 1
        elif row.decision == "update":
            target = targets[row.target_claim_id]
            new_values = _typed(row.data or {})
            before = {f: getattr(target, f) for f in UPLOAD_FIELDS if getattr(target, f) != new_values[f]}
            row.previous = _claim_values(target)
            for field in before:
                setattr(target, field, new_values[field])
            target.updated_at = now
            if row.fingerprint not in known:
                ctx.db.add(
                    ClaimPrint(
                        practice_id=practice_id,
                        fingerprint=row.fingerprint,
                        claim_id=target.id,
                        upload_id=upload.id,
                    )
                )
                known[row.fingerprint] = target.id
            row.result_claim_id = target.id
            upload.updated_claims += 1
            audit.record(
                ctx.db,
                action="claim.updated_from_upload",
                entity_type="claim",
                entity_id=target.id,
                actor_user_id=ctx.user.id,
                practice_id=practice_id,
                before={f: _plain(v) for f, v in before.items()} or None,
                after={
                    **{f: _plain(new_values[f]) for f in before},
                    "from_upload": upload_label(upload.number),
                },
            )
        elif wants_new:
            if row.fingerprint in known:  # committed by another batch since the preview
                upload.skipped_rows += 1
                continue
            claim = Claim(
                practice_id=practice_id,
                upload_id=upload.id,
                fingerprint=row.fingerprint,
                **_typed(row.data or {}),
            )
            ctx.db.add(claim)
            known[row.fingerprint] = uuid.uuid4()  # placeholder: the claim's id is known after flush
            created.append((row, claim))
    await ctx.db.flush()
    for row, claim in created:
        row.result_claim_id = claim.id
        audit.record(
            ctx.db,
            action="claim.imported",
            entity_type="claim",
            entity_id=claim.id,
            actor_user_id=ctx.user.id,
            practice_id=practice_id,
            after={"upload": upload_label(upload.number)},
        )
    upload.created_claims = len(created)
    upload.status, upload.decided_by, upload.decided_at, upload.completed_at = (
        "committed",
        ctx.user.id,
        now,
        now,
    )
    await _clear_preview(ctx, upload)
    label = upload_label(upload.number)
    audit.record(
        ctx.db,
        action="upload.committed",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=practice_id,
        after={
            "created_claims": upload.created_claims,
            "updated_claims": upload.updated_claims,
            "skipped_rows": upload.skipped_rows,
        },
    )
    practice = await ctx.db.get(Practice, practice_id)
    summary = (
        f"{upload.created_claims} new claims, {upload.updated_claims} updated, {upload.skipped_rows} skipped"
    )
    notify.send(
        ctx.db,
        {upload.uploaded_by, upload.submitted_by},
        kind="upload.committed",
        title=f"{ctx.user.full_name} approved and committed {label}",
        body=summary,
        link=f"/uploads/{upload.id}",
        actor=ctx.user.id,
    )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="upload.completed",
        title=f"{label} committed for {practice.name if practice else 'a practice'}",
        body=summary,
        link=f"/uploads/{upload.id}",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(upload)
    return await detail(ctx, upload)


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, str | int | bool):
        return value
    return str(value)


# ---- 5: reverse --------------------------------------------------------------------------------------


async def reverse(ctx: Ctx, upload_id: uuid.UUID, reason: str | None) -> UploadDetail:
    upload = await load_visible(ctx, upload_id)
    await _require_status(upload, "committed")
    if not ctx.access.has("uploads.reverse", upload.practice_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Permission required in this practice: uploads.reverse"
        )
    if not reason or len(reason.strip()) < 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a reason for reversing this upload.")

    created = list(
        await ctx.db.scalars(select(Claim).where(Claim.upload_id == upload.id, Claim.withdrawn_at.is_(None)))
    )
    noted = set(
        await ctx.db.scalars(
            select(ClaimNote.claim_id).where(ClaimNote.claim_id.in_([c.id for c in created]))
        )
    )
    worked = [c for c in created if c.id in noted or any(getattr(c, f) is not None for f in WORK_FIELDS)]
    if worked:
        numbers = ", ".join(claim_label(c.number) for c in worked[:10])
        more = f" and {len(worked) - 10} more" if len(worked) > 10 else ""
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Work has been recorded on {len(worked)} claim(s) from this upload ({numbers}{more}). "
            "Those claims must be cleared or unassigned before the upload can be reversed.",
        )

    now = _now()
    for claim in created:
        claim.withdrawn_at = now
        claim.fingerprint = f"withdrawn:{claim.id}"  # frees the line, so it can be uploaded again
        audit.record(
            ctx.db,
            action="claim.withdrawn",
            entity_type="claim",
            entity_id=claim.id,
            actor_user_id=ctx.user.id,
            practice_id=claim.practice_id,
            after={"upload": upload_label(upload.number), "reason": reason},
        )
    updates = list(
        await ctx.db.scalars(
            select(UploadRow).where(
                UploadRow.upload_id == upload.id,
                UploadRow.decision == "update",
                UploadRow.previous.is_not(None),
            )
        )
    )
    for row in updates:
        target = await ctx.db.get(Claim, row.target_claim_id)
        if target is None:
            continue
        restored = _typed(row.previous or {})
        before = {f: _plain(getattr(target, f)) for f in UPLOAD_FIELDS if getattr(target, f) != restored[f]}
        for field in UPLOAD_FIELDS:
            setattr(target, field, restored[field])
        target.updated_at = now
        audit.record(
            ctx.db,
            action="claim.update_reversed",
            entity_type="claim",
            entity_id=target.id,
            actor_user_id=ctx.user.id,
            practice_id=target.practice_id,
            before=before or None,
            after={**{f: _plain(restored[f]) for f in before}, "upload": upload_label(upload.number)},
        )
    await ctx.db.execute(delete(ClaimPrint).where(ClaimPrint.upload_id == upload.id))
    upload.status, upload.reversed_by, upload.reversed_at, upload.reverse_reason = (
        "reversed",
        ctx.user.id,
        now,
        reason,
    )
    audit.record(
        ctx.db,
        action="upload.reversed",
        entity_type="upload",
        entity_id=upload.id,
        actor_user_id=ctx.user.id,
        practice_id=upload.practice_id,
        after={"withdrawn_claims": len(created), "restored_claims": len(updates), "reason": reason},
    )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db) | {upload.uploaded_by},
        kind="upload.reversed",
        title=f"{ctx.user.full_name} reversed {upload_label(upload.number)}",
        body=reason,
        link=f"/uploads/{upload.id}",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(upload)
    return await detail(ctx, upload)
