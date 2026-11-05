"""Rules for working claims. Every change is audited in the same transaction as the change itself."""

import uuid
from datetime import UTC, date, datetime
from pathlib import PurePath
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select

from app.core import audit
from app.core.access import users_with
from app.core.clock import aging, business_today
from app.core.config import get_settings
from app.core.context import Ctx
from app.core.schemas import NamedRef
from app.core.storage import get_storage
from app.modules.claims import repository
from app.modules.claims.models import Claim, ClaimNote
from app.modules.claims.schemas import (
    ClaimDetail,
    ClaimListItem,
    ClaimRef,
    ClaimUpdate,
    EobOut,
    NoteOut,
    PersonRef,
    UploadRef,
    claim_label,
)
from app.modules.lists.service import active_values
from app.modules.notifications import service as notify
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
    statement = repository.visible(select(Claim).where(Claim.id == claim_id), ctx)
    claim = await ctx.db.scalar(statement)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found.")
    return claim


async def list_items(ctx: Ctx, claims: list[Claim]) -> list[ClaimListItem]:
    today = business_today()
    practices = await repository.practice_names(ctx.db, {c.practice_id for c in claims})
    people = await repository.people(ctx.db, {c.assigned_user_id for c in claims if c.assigned_user_id})
    targets = await repository.numbers(ctx.db, {c.merged_into_id for c in claims if c.merged_into_id})
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
                work_state=c.work_state,
                priority=c.priority,
                returned=c.returned,
                merged_into=ClaimRef(id=c.merged_into_id, number=claim_label(targets[c.merged_into_id]))
                if c.merged_into_id in targets
                else None,
            )
        )
    return items


async def detail(ctx: Ctx, claim: Claim) -> ClaimDetail:
    [base] = await list_items(ctx, [claim])
    live = claim.merged_into_id is None and claim.withdrawn_at is None
    upload = await ctx.db.get(Upload, claim.upload_id)
    notes = await repository.notes(ctx.db, claim.id)
    authors = await repository.people(
        ctx.db,
        {n.author_user_id for n in notes}
        | {p for p in (claim.state_changed_by, claim.completion_requested_by) if p is not None},
    )
    state = claim.work_state
    has = ctx.access.has
    closer = has("claims.close", claim.practice_id) and live

    def person(user_id: uuid.UUID | None) -> PersonRef | None:
        return PersonRef(id=user_id, name=authors.get(user_id, ("Unknown", ""))[0]) if user_id else None

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
        can_work=has("claims.work", claim.practice_id) and live and state == "open",
        can_assign=has("claims.assign", claim.practice_id) and live and state == "open",
        can_review=ctx.access.has("claims.review", claim.practice_id) and claim.needs_review and live,
        withdrawn=claim.withdrawn_at is not None,
        state_reason=claim.state_reason,
        state_changed_by=person(claim.state_changed_by),
        state_changed_at=claim.state_changed_at,
        completion_requested_by=person(claim.completion_requested_by),
        can_note=has("claims.work", claim.practice_id) and live and state != "closed",
        can_request_completion=has("claims.work", claim.practice_id) and live and state == "open",
        can_review_completion=closer
        and state == "pending_completion"
        and ctx.user.id != claim.completion_requested_by,
        can_close=closer and state == "open",
        can_reopen=closer and state == "closed",
        can_prioritize=has("claims.prioritize", claim.practice_id) and live and state != "closed",
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


def _require_in_practice(ctx: Ctx, permission: str, claim: Claim) -> None:
    """The person may see this claim; may they also do this here? (Roles can differ per practice.)"""
    if not ctx.access.has(permission, claim.practice_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permission required in this practice: {permission}")


def _require_active(claim: Claim) -> None:
    if claim.merged_into_id is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This line was merged into another claim. Work on that claim."
        )


async def update(ctx: Ctx, claim_id: uuid.UUID, body: ClaimUpdate) -> ClaimDetail:
    claim = await load_visible(ctx, claim_id)
    _require_active(claim)
    sent = body.model_fields_set
    work_fields = sent - {"assigned_user_id", "needs_review", "priority"}
    if claim.work_state == "closed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This claim is closed. Reopen it first.")
    if claim.work_state == "pending_completion" and (work_fields or "assigned_user_id" in sent):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This claim is waiting for completion review. "
            "A reviewer returns it, continues it or closes it first.",
        )
    if "priority" in sent:
        _require_in_practice(ctx, "claims.prioritize", claim)
        if body.priority is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a priority.")
    if work_fields:
        _require_in_practice(ctx, "claims.work", claim)
    if "assigned_user_id" in sent:
        _require_in_practice(ctx, "claims.assign", claim)
    if "needs_review" in sent:
        _require_in_practice(ctx, "claims.review", claim)
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
        work = after.keys() - assignment - {"needs_review", "priority"}
        if "priority" in after:
            await _record_priority(ctx, [claim], before["priority"], after["priority"])
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
            await _notify_assignment(ctx, [claim], previous={claim.id: _as_uuid(before["assigned_user_id"])})
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
    _require_active(claim)
    if claim.work_state == "closed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This claim is closed. Reopen it to add notes.")
    _require_in_practice(ctx, "claims.work", claim)
    note = ClaimNote(claim_id=claim.id, author_user_id=ctx.user.id, body=body)
    ctx.db.add(note)
    await ctx.db.flush()
    # The note's text stays in claim_notes; the audit event points to it.
    audit.record(
        ctx.db,
        action="claim.note_added",
        entity_type="claim",
        entity_id=claim.id,
        actor_user_id=ctx.user.id,
        practice_id=claim.practice_id,
        after={"note_id": note.id, "characters": len(body)},
    )
    notify.send(
        ctx.db,
        {claim.assigned_user_id},
        kind="claim.note",
        title=f"{ctx.user.full_name} added a note on {claim_label(claim.number)}",
        link=f"/claims/{claim.id}",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    return await detail(ctx, claim)


async def attach_eob(ctx: Ctx, claim_id: uuid.UUID, file: UploadFile) -> ClaimDetail:
    claim = await load_visible(ctx, claim_id)
    _require_active(claim)
    if claim.work_state != "open":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "EOBs can only be attached while the claim is open.")
    _require_in_practice(ctx, "claims.work", claim)
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


# ---- Bulk assignment ----------------------------------------------------------------------------------


async def assignable_for(ctx: Ctx, practice_ids: set[uuid.UUID]) -> list[tuple[uuid.UUID, str, str]]:
    """People who can take claims from every one of these practices."""
    if not all(ctx.access.has("claims.assign", p) for p in practice_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only assign within your practices.")
    return await repository.assignees_all(ctx.db, practice_ids)


async def bulk_assign(ctx: Ctx, claim_ids: list[uuid.UUID], assignee: uuid.UUID | None) -> int:
    """Assigns many claims in one step. All of them change, or none do."""
    wanted = set(claim_ids)
    statement = repository.active(repository.visible(select(Claim).where(Claim.id.in_(wanted)), ctx))
    claims = list(await ctx.db.scalars(statement))
    if len(claims) != len(wanted):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Some of these claims were not found or were merged.")
    for claim in claims:
        _require_in_practice(ctx, "claims.assign", claim)
    if any(c.work_state != "open" for c in claims):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only open claims can be assigned. Some selected claims are closed or in review.",
        )
    if assignee is not None:
        allowed = {
            person_id
            for person_id, _, _ in await repository.assignees_all(ctx.db, {c.practice_id for c in claims})
        }
        if assignee not in allowed:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This person isn't active AR staff of every selected claim's practice.",
            )
    changed = [c for c in claims if c.assigned_user_id != assignee]
    previous = {c.id: c.assigned_user_id for c in changed}
    for claim in changed:
        audit.record(
            ctx.db,
            action="claim.assigned",
            entity_type="claim",
            entity_id=claim.id,
            actor_user_id=ctx.user.id,
            practice_id=claim.practice_id,
            before={"assigned_user_id": _plain(claim.assigned_user_id)},
            after={"assigned_user_id": _plain(assignee), "bulk": True},
        )
        claim.assigned_user_id = assignee
        claim.updated_at = datetime.now(UTC)
    if changed:
        await _notify_assignment(ctx, changed, previous=previous)
    await ctx.db.commit()
    return len(changed)


# ---- Review queue ---------------------------------------------------------------------------------------

UPLOAD_FIELDS = ("billed", "insurance_carrier", "patient_dob", "subscriber_name", "subscriber_dob")
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
)


async def matches(ctx: Ctx, claim_id: uuid.UUID) -> list[ClaimDetail]:
    claim = await load_visible(ctx, claim_id)
    _require_in_practice(ctx, "claims.review", claim)
    return [await detail(ctx, other) for other in await repository.same_visit(ctx.db, claim)]


async def resolve(ctx: Ctx, claim_id: uuid.UUID, decision: str, target_id: uuid.UUID | None) -> ClaimDetail:
    claim = await load_visible(ctx, claim_id)
    _require_active(claim)
    _require_in_practice(ctx, "claims.review", claim)
    if not claim.needs_review:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This claim doesn't need review.")

    if decision == "separate":
        claim.needs_review = False
        audit.record(
            ctx.db,
            action="claim.reviewed",
            entity_type="claim",
            entity_id=claim.id,
            actor_user_id=ctx.user.id,
            practice_id=claim.practice_id,
            after={"decision": "separate claim"},
        )
        await ctx.db.commit()
        await ctx.db.refresh(claim)
        return await detail(ctx, claim)

    candidates = {c.id: c for c in await repository.same_visit(ctx.db, claim)}
    target = candidates.get(target_id) if target_id else None
    if target is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose which earlier claim this line belongs to.")
    notes = await repository.notes(ctx.db, claim.id)
    if notes or claim.assigned_user_id or any(getattr(claim, f) is not None for f in WORK_FIELDS):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This line already has work recorded (assignment, work fields, notes or EOB). "
            "Keep it as a separate claim, or clear that work first.",
        )

    before = {f: _plain(getattr(target, f)) for f in UPLOAD_FIELDS if getattr(target, f) != getattr(claim, f)}
    after = {f: _plain(getattr(claim, f)) for f in before}
    for field in before:
        setattr(target, field, getattr(claim, field))
    target.updated_at = datetime.now(UTC)
    claim.merged_into_id, claim.needs_review = target.id, False
    audit.record(
        ctx.db,
        action="claim.updated_from_upload",
        entity_type="claim",
        entity_id=target.id,
        actor_user_id=ctx.user.id,
        practice_id=target.practice_id,
        before=before or None,
        after={**after, "from_line": claim_label(claim.number)},
    )
    audit.record(
        ctx.db,
        action="claim.merged",
        entity_type="claim",
        entity_id=claim.id,
        actor_user_id=ctx.user.id,
        practice_id=claim.practice_id,
        after={"into": claim_label(target.number)},
    )
    await ctx.db.commit()
    await ctx.db.refresh(target)
    return await detail(ctx, target)


# ---- Notifications ------------------------------------------------------------------------------------


def _as_uuid(value: object) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


async def _notify_assignment(
    ctx: Ctx, claims: list[Claim], *, previous: dict[uuid.UUID, uuid.UUID | None]
) -> None:
    """Tells the new assignee, anyone who lost claims, and Management: one notification each per action."""
    new_owner = claims[0].assigned_user_id  # every claim in one action goes to the same person
    names = await repository.people(ctx.db, {new_owner} if new_owner else set())
    owner_name = names[new_owner][0] if new_owner and new_owner in names else "nobody"
    single = len(claims) == 1
    label = claim_label(claims[0].number) if single else f"{len(claims)} claims"
    link = f"/claims/{claims[0].id}" if single else "/claims?view=mine"

    if new_owner:
        notify.send(
            ctx.db,
            {new_owner},
            kind="claim.assigned",
            title=f"{label} {'was' if single else 'were'} assigned to you by {ctx.user.full_name}",
            link=link,
            actor=ctx.user.id,
        )
    losers: dict[uuid.UUID, list[Claim]] = {}
    for claim in claims:
        old = previous.get(claim.id)
        if old and old != new_owner:
            losers.setdefault(old, []).append(claim)
    for person, lost in losers.items():
        what = f"{claim_label(lost[0].number)} was" if len(lost) == 1 else f"{len(lost)} of your claims were"
        notify.send(
            ctx.db,
            {person},
            kind="claim.reassigned",
            title=f"{what} reassigned to {owner_name}",
            link="/claims?view=mine",
            actor=ctx.user.id,
        )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="claim.assigned.oversight",
        title=f"{ctx.user.full_name} assigned {label} to {owner_name}",
        link=link if single else "/claims?view=all",
        actor=ctx.user.id,
    )


# ---- Lifecycle (Phase D) ------------------------------------------------------------------------------

PRIORITY_LABELS = {"low": "Low", "normal": "Normal", "high": "High", "urgent": "Urgent"}


async def _record_priority(ctx: Ctx, claims: list[Claim], old: Any, new: Any) -> None:
    """Audits a priority change and tells assignees when their claims become High or Urgent."""
    for claim in claims:
        audit.record(
            ctx.db,
            action="claim.prioritized",
            entity_type="claim",
            entity_id=claim.id,
            actor_user_id=ctx.user.id,
            practice_id=claim.practice_id,
            before={"priority": old if isinstance(old, str) else None},
            after={"priority": new},
        )
    if new in ("high", "urgent"):
        by_person: dict[uuid.UUID, list[Claim]] = {}
        for claim in claims:
            if claim.assigned_user_id:
                by_person.setdefault(claim.assigned_user_id, []).append(claim)
        for person_id, theirs in by_person.items():
            what = (
                claim_label(theirs[0].number) + " is"
                if len(theirs) == 1
                else f"{len(theirs)} of your claims are"
            )
            notify.send(
                ctx.db,
                {person_id},
                kind="claim.prioritized",
                title=f"{what} now {PRIORITY_LABELS[new]} priority",
                link=f"/claims/{theirs[0].id}" if len(theirs) == 1 else "/claims?view=high-priority",
                actor=ctx.user.id,
            )


def _step(ctx: Ctx, claim: Claim, *, state: str, reason: str | None, returned: bool = False) -> None:
    claim.work_state, claim.returned = state, returned
    claim.state_changed_by, claim.state_changed_at, claim.state_reason = (
        ctx.user.id,
        datetime.now(UTC),
        reason,
    )
    claim.updated_at = datetime.now(UTC)


def _lifecycle_audit(ctx: Ctx, claim: Claim, action: str, before: str, **after: Any) -> None:
    audit.record(
        ctx.db,
        action=action,
        entity_type="claim",
        entity_id=claim.id,
        actor_user_id=ctx.user.id,
        practice_id=claim.practice_id,
        before={"work_state": before},
        after={"work_state": claim.work_state, **{k: _plain(v) for k, v in after.items() if v is not None}},
    )


def _need_reason(reason: str | None) -> str:
    if not reason or len(reason.strip()) < 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a reason.")
    return reason.strip()


async def _load_live(ctx: Ctx, claim_id: uuid.UUID) -> Claim:
    claim = await load_visible(ctx, claim_id)
    _require_active(claim)
    return claim


async def _finish(ctx: Ctx, claim: Claim) -> ClaimDetail:
    await ctx.db.commit()
    await ctx.db.refresh(claim)
    return await detail(ctx, claim)


async def request_completion(ctx: Ctx, claim_id: uuid.UUID, note: str | None) -> ClaimDetail:
    """The person working the claim says it's done. It locks until a reviewer decides."""
    claim = await _load_live(ctx, claim_id)
    _require_in_practice(ctx, "claims.work", claim)
    if claim.work_state != "open":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only open claims can be marked complete.")
    _step(ctx, claim, state="pending_completion", reason=note)
    claim.completion_requested_by = ctx.user.id
    _lifecycle_audit(ctx, claim, "claim.completion_requested", "open", note=note)
    notify.send(
        ctx.db,
        await users_with(ctx.db, "claims.close", claim.practice_id),
        kind="claim.completion_requested",
        title=f"{claim_label(claim.number)} is ready for completion review ({ctx.user.full_name})",
        body=note,
        link=f"/claims/{claim.id}",
        actor=ctx.user.id,
    )
    return await _finish(ctx, claim)


async def _require_reviewer(ctx: Ctx, claim: Claim) -> None:
    _require_in_practice(ctx, "claims.close", claim)


async def approve_completion(ctx: Ctx, claim_id: uuid.UUID, note: str | None) -> ClaimDetail:
    claim = await _load_live(ctx, claim_id)
    await _require_reviewer(ctx, claim)
    if claim.work_state != "pending_completion":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This claim isn't waiting for completion review.")
    if claim.completion_requested_by == ctx.user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Someone other than the person who marked it complete must approve it."
        )
    _step(ctx, claim, state="closed", reason=note)
    _lifecycle_audit(ctx, claim, "claim.closed", "pending_completion", note=note, approved_completion=True)
    notify.send(
        ctx.db,
        {claim.assigned_user_id, claim.completion_requested_by},
        kind="claim.closed",
        title=f"{ctx.user.full_name} approved and closed {claim_label(claim.number)}",
        body=note,
        link=f"/claims/{claim.id}",
        actor=ctx.user.id,
    )
    return await _finish(ctx, claim)


async def return_for_correction(ctx: Ctx, claim_id: uuid.UUID, reason: str | None) -> ClaimDetail:
    claim = await _load_live(ctx, claim_id)
    await _require_reviewer(ctx, claim)
    if claim.work_state == "closed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Closed claims are reopened, not returned.")
    reason = _need_reason(reason)
    before = claim.work_state
    _step(ctx, claim, state="open", reason=reason, returned=True)
    _lifecycle_audit(ctx, claim, "claim.returned", before, reason=reason)
    notify.send(
        ctx.db,
        {claim.assigned_user_id, claim.completion_requested_by},
        kind="claim.returned",
        title=f"{claim_label(claim.number)} was returned for correction by {ctx.user.full_name}",
        body=reason,
        link=f"/claims/{claim.id}",
        actor=ctx.user.id,
    )
    return await _finish(ctx, claim)


async def continue_followup(ctx: Ctx, claim_id: uuid.UUID, reason: str | None, followup: date) -> ClaimDetail:
    claim = await _load_live(ctx, claim_id)
    await _require_reviewer(ctx, claim)
    if claim.work_state != "pending_completion":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This claim isn't waiting for completion review.")
    old_date = claim.followup_date
    _step(ctx, claim, state="open", reason=reason)
    claim.followup_date = followup
    _lifecycle_audit(
        ctx,
        claim,
        "claim.continued",
        "pending_completion",
        reason=reason,
        followup_date=followup,
        previous_followup=old_date,
    )
    notify.send(
        ctx.db,
        {claim.assigned_user_id, claim.completion_requested_by},
        kind="claim.continued",
        title=f"{claim_label(claim.number)}: continue follow-up by {followup:%d %b %Y}",
        body=reason,
        link=f"/claims/{claim.id}",
        actor=ctx.user.id,
    )
    return await _finish(ctx, claim)


async def close(ctx: Ctx, claim_id: uuid.UUID, reason: str | None) -> ClaimDetail:
    """A reviewer closes an open claim directly, e.g. one found already paid. A reason is required."""
    claim = await _load_live(ctx, claim_id)
    await _require_reviewer(ctx, claim)
    if claim.work_state != "open":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only open claims can be closed this way.")
    reason = _need_reason(reason)
    _step(ctx, claim, state="closed", reason=reason)
    _lifecycle_audit(ctx, claim, "claim.closed", "open", reason=reason)
    notify.send(
        ctx.db,
        {claim.assigned_user_id},
        kind="claim.closed",
        title=f"{ctx.user.full_name} closed {claim_label(claim.number)}",
        body=reason,
        link=f"/claims/{claim.id}",
        actor=ctx.user.id,
    )
    return await _finish(ctx, claim)


async def reopen(ctx: Ctx, claim_id: uuid.UUID, reason: str | None) -> ClaimDetail:
    claim = await _load_live(ctx, claim_id)
    await _require_reviewer(ctx, claim)
    if claim.work_state != "closed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only closed claims can be reopened.")
    reason = _need_reason(reason)
    _step(ctx, claim, state="open", reason=reason)
    claim.completion_requested_by = None
    _lifecycle_audit(ctx, claim, "claim.reopened", "closed", reason=reason)
    notify.send(
        ctx.db,
        {claim.assigned_user_id},
        kind="claim.reopened",
        title=f"{ctx.user.full_name} reopened {claim_label(claim.number)}",
        body=reason,
        link=f"/claims/{claim.id}",
        actor=ctx.user.id,
    )
    return await _finish(ctx, claim)


async def bulk_priority(ctx: Ctx, claim_ids: list[uuid.UUID], priority: str) -> int:
    wanted = set(claim_ids)
    statement = repository.active(repository.visible(select(Claim).where(Claim.id.in_(wanted)), ctx))
    claims = list(await ctx.db.scalars(statement))
    if len(claims) != len(wanted):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Some of these claims were not found or were merged.")
    for claim in claims:
        _require_in_practice(ctx, "claims.prioritize", claim)
    if any(c.work_state == "closed" for c in claims):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Closed claims keep their priority. Reopen them first."
        )
    changed = [c for c in claims if c.priority != priority]
    by_old: dict[str, list[Claim]] = {}
    for claim in changed:
        by_old.setdefault(claim.priority, []).append(claim)
        claim.priority, claim.updated_at = priority, datetime.now(UTC)
    for old, group in by_old.items():
        await _record_priority(ctx, group, old, priority)
    await ctx.db.commit()
    return len(changed)
