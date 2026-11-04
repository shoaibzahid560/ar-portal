"""
Turns raw audit events into something a person can read: names instead of IDs, claim and upload numbers
with links, the text of notes, and which permissions changed. Note text is only included when the reader
may see that claim; everything else here is already visible to anyone who can read the audit log.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.core.context import Ctx
from app.core.scope import get_scope
from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import Actor, AuditEventOut
from app.modules.claims import repository as claims
from app.modules.claims.models import Claim, ClaimNote
from app.modules.claims.schemas import claim_label
from app.modules.practices.models import Practice, Team
from app.modules.roles.models import Permission, Role
from app.modules.uploads.models import Upload
from app.modules.uploads.schemas import upload_label
from app.modules.users.models import User

LIST_NAMES = {
    "claim_status": "Claim Status",
    "pay_status": "Pay Status",
    "check_status": "Check Status",
    "action_taken": "Action Taken",
}


def _ids(values: set[str]) -> set[uuid.UUID]:
    out = set()
    for value in values:
        try:
            out.add(uuid.UUID(value))
        except ValueError:
            continue
    return out


async def enrich(ctx: Ctx, rows: Sequence[tuple[AuditEvent, User | None]]) -> list[AuditEventOut]:
    db = ctx.db
    by_type: dict[str, set[str]] = {}
    for event, _ in rows:
        by_type.setdefault(event.entity_type, set()).add(event.entity_id)

    # Claims: numbers, and which ones the reader may see (for note text).
    claim_ids = _ids(by_type.get("claim", set()))
    claim_numbers: dict[uuid.UUID, int] = {}
    visible_claims: set[uuid.UUID] = set()
    if claim_ids:
        claim_numbers = dict(
            (await db.execute(select(Claim.id, Claim.number).where(Claim.id.in_(claim_ids)))).all()
        )
        visible = claims.visible(select(Claim.id).where(Claim.id.in_(claim_ids)), ctx, await get_scope(ctx))
        visible_claims = set(await db.scalars(visible))

    uploads = _ids(by_type.get("upload", set()))
    upload_numbers = (
        dict((await db.execute(select(Upload.id, Upload.number).where(Upload.id.in_(uploads)))).all())
        if uploads
        else {}
    )
    practices = _ids(by_type.get("practice", set()))
    practice_names = (
        dict((await db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(practices)))).all())
        if practices
        else {}
    )
    teams = _ids(by_type.get("team", set()))
    team_names = (
        dict((await db.execute(select(Team.id, Team.name).where(Team.id.in_(teams)))).all()) if teams else {}
    )
    role_names = dict((await db.execute(select(Role.key, Role.name))).all()) if "role" in by_type else {}

    # People named anywhere: users as records, and assignees in before/after.
    people_ids = _ids(by_type.get("user", set()))
    for event, _ in rows:
        for values in (event.before or {}, event.after or {}):
            if values.get("assigned_user_id"):
                people_ids |= _ids({str(values["assigned_user_id"])})
    names = (
        {
            str(k): v
            for k, v in (
                await db.execute(select(User.id, User.full_name).where(User.id.in_(people_ids)))
            ).all()
        }
        if people_ids
        else {}
    )

    # Permission descriptions, for "which permissions were added or removed".
    permission_keys = {
        key
        for event, _ in rows
        if event.action == "role.permissions_changed"
        for values in (event.before or {}, event.after or {})
        for key in values.get("permissions", [])
    }
    descriptions = (
        dict(
            (
                await db.execute(
                    select(Permission.key, Permission.description).where(Permission.key.in_(permission_keys))
                )
            ).all()
        )
        if permission_keys
        else {}
    )

    # Note text, for note events on claims the reader may see. The note and its audit event were written in
    # the same transaction, so they share author and timestamp (older events have no note_id stored).
    note_events = [
        e for e, _ in rows if e.action == "claim.note_added" and _ids({e.entity_id}) & visible_claims
    ]
    notes_by_id: dict[int, str] = {}
    notes_by_moment: dict[tuple[str, str, str], str] = {}
    if note_events:
        candidates = await db.execute(
            select(
                ClaimNote.id,
                ClaimNote.claim_id,
                ClaimNote.author_user_id,
                ClaimNote.created_at,
                ClaimNote.body,
            ).where(ClaimNote.claim_id.in_(_ids({e.entity_id for e in note_events})))
        )
        for note_id, claim_id, author, created_at, body in candidates:
            notes_by_id[note_id] = body
            notes_by_moment[(str(claim_id), str(author), created_at.isoformat())] = body

    out = []
    for event, user in rows:
        label, link, note, summary = None, None, None, None
        entity = event.entity_id
        match event.entity_type:
            case "claim":
                key = next(iter(_ids({entity})), None)
                if key in claim_numbers:
                    label, link = claim_label(claim_numbers[key]), f"/claims/{entity}"
            case "upload":
                key = next(iter(_ids({entity})), None)
                if key in upload_numbers:
                    label, link = upload_label(upload_numbers[key]), f"/uploads/{entity}"
            case "user":
                label, link = names.get(entity), "/admin/users"
            case "practice":
                key = next(iter(_ids({entity})), None)
                label, link = practice_names.get(key) if key else None, "/admin/practices"
            case "team":
                key = next(iter(_ids({entity})), None)
                label, link = team_names.get(key) if key else None, "/admin/practices?view=teams"
            case "role":
                label, link = role_names.get(entity, entity), "/admin/settings?view=roles"
            case "list":
                label, link = LIST_NAMES.get(entity, entity), "/admin/settings?view=lists"
            case "auth":
                label = entity

        if event.action == "claim.note_added" and _ids({entity}) & visible_claims:
            after = event.after or {}
            note = notes_by_id.get(after.get("note_id", -1)) or notes_by_moment.get(
                (entity, str(event.actor_user_id), event.occurred_at.isoformat())
            )
        if event.action == "role.permissions_changed":
            before = set((event.before or {}).get("permissions", []))
            after_set = set((event.after or {}).get("permissions", []))
            added = [descriptions.get(k, k) for k in sorted(after_set - before)]
            removed = [descriptions.get(k, k) for k in sorted(before - after_set)]
            summary = [f"Added: {a}" for a in added] + [f"Removed: {r}" for r in removed]

        mentioned = {
            str(values["assigned_user_id"])
            for values in (event.before or {}, event.after or {})
            if values.get("assigned_user_id")
        }
        out.append(
            AuditEventOut(
                id=event.id,
                occurred_at=event.occurred_at,
                actor=Actor(id=user.id, name=user.full_name, email=user.email) if user else None,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                before=event.before,
                after=event.after,
                people={k: names[k] for k in mentioned if k in names},
                label=label,
                link=link,
                note=note,
                summary=summary,
            )
        )
    return out
