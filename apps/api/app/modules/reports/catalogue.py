"""
The internal report catalogue (brief sections 6 and 10, specification section 7).

Every report starts from what the signed-in person may see (claims through the claims module's scope,
uploads through the uploads module's scope, staff activity through the practices where they hold
reports.staff), then applies the chosen filters. Filters can only narrow that scope.
"""

import uuid
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import Select, Text, cast, select

from app.core.clock import AGING_BUCKETS, aging
from app.core.config import get_settings
from app.core.context import Ctx
from app.core.scope import get_scope
from app.modules.audit.models import AuditEvent
from app.modules.claims import repository as claims_repo
from app.modules.claims.models import Claim
from app.modules.claims.schemas import claim_label
from app.modules.practices.models import Practice, TeamMember
from app.modules.reports.schemas import Column, Filters, Targets
from app.modules.roles.models import Role
from app.modules.uploads.models import Upload
from app.modules.uploads.schemas import upload_label
from app.modules.uploads.service import visible_uploads
from app.modules.users.models import User

WORK_STATE_LABELS = {"open": "Open", "pending_completion": "Awaiting completion", "closed": "Closed"}
BUCKET_LABELS = [label for _, label in AGING_BUCKETS] + ["120+"]
UPLOAD_STATUS_LABELS = {
    "processing": "Processing",
    "preview": "Preview",
    "submitted": "Waiting for approval",
    "committed": "Committed",
    "rejected": "Turned down",
    "discarded": "Discarded",
    "reversed": "Reversed",
    "failed": "Failed",
}
ACTION_LABELS = {
    "claim.imported": "Imported",
    "claim.updated": "Updated",
    "claim.assigned": "Assigned",
    "claim.note_added": "Note added",
    "claim.eob_attached": "EOB attached",
    "claim.eob_downloaded": "EOB opened",
    "claim.updated_from_upload": "Updated from an upload",
    "claim.reviewed": "Kept as a separate claim",
    "claim.merged": "Merged into another claim",
    "claim.withdrawn": "Withdrawn (upload reversed)",
    "claim.update_reversed": "Update undone (upload reversed)",
    "claim.completion_requested": "Marked complete",
    "claim.closed": "Closed",
    "claim.returned": "Returned for correction",
    "claim.continued": "Sent back to continue",
    "claim.reopened": "Reopened",
    "claim.prioritized": "Priority changed",
}
FIELD_LABELS = {
    "claim_status": "Claim status",
    "pay_status": "Pay status",
    "check_status": "Check status",
    "action_taken": "Action taken",
    "allowed_amount": "Allowed",
    "recovered_amount": "Recovered",
    "patient_responsibility": "Patient responsibility",
    "cashed_date": "Cashed date",
    "payment_posted_date": "Payment posted",
    "followup_date": "Follow-up",
    "assigned_user_id": "Assigned to",
    "work_state": "Work status",
    "priority": "Priority",
    "needs_review": "Needs review",
    "billed": "Billed",
}
# Bookkeeping keys and free text that never go into a ledger (note text stays on the claim screen).
LEDGER_HIDDEN = {
    "body",
    "note",
    "note_id",
    "characters",
    "bulk",
    "from_line",
    "upload",
    "from_upload",
    "reason",
}
LEDGER_LIMIT = 20000


@dataclass
class Result:
    columns: list[Column]
    rows: list[dict[str, Any]]
    group_by: str | None = None  # a column whose value starts a new subtotal group
    sum_keys: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)
    extra_totals: dict[str, Any] = field(default_factory=dict)

    def totals(self) -> dict[str, Any]:
        totals: dict[str, Any] = {key: sum((r.get(key) or 0) for r in self.rows) for key in self.sum_keys}
        totals.update(self.extra_totals)
        return totals


@dataclass(frozen=True)
class Report:
    key: str
    title: str
    description: str
    date_basis: str
    filters: tuple[str, ...]
    contains_phi: bool
    staff: bool
    build: Callable[[Ctx, Filters, date, Targets], Awaitable[Result]]


# ---- Shared helpers ----------------------------------------------------------------------------------


def money(value: Any) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def fmt_money(value: Any) -> str:
    return f"${money(value):,.2f}"


def percent(part: Any, whole: Any) -> float | None:
    whole = Decimal(whole or 0)
    return None if whole == 0 else float(round(Decimal(part or 0) / whole * 100, 1))


def day_bounds(f: Filters, default_days: int | None, today: date) -> tuple[datetime | None, datetime | None]:
    """The date range as instants in the team's time zone. Without dates, the last `default_days`."""
    start, end = f.date_from, f.date_to
    if start is None and end is None and default_days is not None:
        start, end = today - timedelta(days=default_days - 1), today
    zone = ZoneInfo(get_settings().business_timezone)
    lo = datetime.combine(start, time.min, zone).astimezone(UTC) if start else None
    hi = datetime.combine(end, time.max, zone).astimezone(UTC) if end else None
    return lo, hi


async def practice_names(ctx: Ctx, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict((await ctx.db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(ids)))).all())


async def people(ctx: Ctx, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    """Name and primary role, per person."""
    if not ids:
        return {}
    rows = await ctx.db.execute(
        select(User.id, User.full_name, Role.name).join(Role, Role.id == User.role_id).where(User.id.in_(ids))
    )
    return {uid: (name, role) for uid, name, role in rows}


async def team_member_ids(ctx: Ctx, team_id: uuid.UUID) -> set[uuid.UUID]:
    scope = await get_scope(ctx)
    if not scope.company_wide and team_id not in scope.team_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    return set(await ctx.db.scalars(select(TeamMember.user_id).where(TeamMember.team_id == team_id)))


async def scoped_claims(ctx: Ctx, f: Filters, today: date, *, date_column: Any = None) -> list[Claim]:
    """The claims this person may see, narrowed by the filters. `date_column` takes the date range."""
    statement: Select = claims_repo.active(claims_repo.visible(select(Claim), ctx))
    if f.practice_ids:
        statement = statement.where(Claim.practice_id.in_(f.practice_ids))
    if f.payer:
        statement = statement.where(Claim.insurance_carrier.ilike(f"%{f.payer.strip()}%"))
    if f.claim_statuses:
        named = [s for s in f.claim_statuses if s != "No status"]
        condition = Claim.claim_status.in_(named)
        if "No status" in f.claim_statuses:
            condition = condition | Claim.claim_status.is_(None)
        statement = statement.where(condition)
    if f.work_states:
        statement = statement.where(Claim.work_state.in_(f.work_states))
    if f.assigned_user_id:
        statement = statement.where(Claim.assigned_user_id == f.assigned_user_id)
    if f.team_id:
        statement = statement.where(Claim.assigned_user_id.in_(await team_member_ids(ctx, f.team_id)))
    if f.upload_id:
        statement = statement.where(Claim.upload_id == f.upload_id)
    if f.priorities:
        statement = statement.where(Claim.priority.in_(f.priorities))
    if date_column is not None:
        if f.date_from:
            statement = statement.where(date_column >= f.date_from)
        if f.date_to:
            statement = statement.where(date_column <= f.date_to)
    claims = list(await ctx.db.scalars(statement))
    if f.aging_buckets:
        claims = [c for c in claims if aging(c.service_date, today)[1] in f.aging_buckets]
    return claims


def business_days(lo: date, hi: date) -> int:
    days = 0
    current = lo
    while current <= hi:
        days += current.weekday() < 5
        current += timedelta(days=1)
    return max(days, 1)


# ---- 1. AR claims statement ----------------------------------------------------------------------------

STATEMENT_COLUMNS = [
    Column(key="claim", label="Claim"),
    Column(key="practice", label="Practice"),
    Column(key="patient", label="Patient"),
    Column(key="subscriber_id", label="Subscriber ID"),
    Column(key="payer", label="Payer"),
    Column(key="service_date", label="Service date", kind="date"),
    Column(key="billed", label="Billed", kind="money"),
    Column(key="allowed", label="Allowed", kind="money"),
    Column(key="recovered", label="Recovered", kind="money"),
    Column(key="patient_resp", label="Patient resp.", kind="money"),
    Column(key="unrecovered", label="Unrecovered", kind="money"),
    Column(key="claim_status", label="Claim status"),
    Column(key="work_state", label="Work status"),
    Column(key="assigned_to", label="Assigned to"),
    Column(key="followup", label="Follow-up", kind="date"),
    Column(key="aging_days", label="Aging (days)", kind="int"),
]


def _amount(value: Any) -> Decimal | None:
    return money(value) if value is not None else None


async def statement(ctx: Ctx, f: Filters, today: date, targets: Targets) -> Result:
    claims = await scoped_claims(ctx, f, today, date_column=Claim.service_date)
    practices = await practice_names(ctx, {c.practice_id for c in claims})
    names = await people(ctx, {c.assigned_user_id for c in claims if c.assigned_user_id})
    claims.sort(key=lambda c: (practices.get(c.practice_id, ""), c.service_date, c.number))
    rows = []
    for c in claims:
        rows.append(
            {
                "claim": claim_label(c.number),
                "practice": practices.get(c.practice_id, ""),
                "patient": c.patient_name,
                "subscriber_id": c.subscriber_id,
                "payer": c.insurance_carrier,
                "service_date": c.service_date,
                "billed": money(c.billed),
                "allowed": _amount(c.allowed_amount),
                "recovered": _amount(c.recovered_amount),
                "patient_resp": _amount(c.patient_responsibility),
                "unrecovered": money(c.billed) - money(c.recovered_amount),
                "claim_status": c.claim_status or "No status",
                "work_state": WORK_STATE_LABELS[c.work_state],
                "assigned_to": names[c.assigned_user_id][0] if c.assigned_user_id in names else "Unassigned",
                "followup": c.followup_date,
                "aging_days": aging(c.service_date, today)[0],
            }
        )
    result = Result(
        STATEMENT_COLUMNS,
        rows,
        group_by="practice",
        sum_keys=("billed", "allowed", "recovered", "patient_resp", "unrecovered"),
    )
    t = result.totals()
    result.notes = [
        f"{len(rows)} claims in {len(practices)} practice(s).",
        f"Billed {fmt_money(t['billed'])} - recovered {fmt_money(t['recovered'])} "
        f"= unrecovered {fmt_money(t['unrecovered'])}.",
    ]
    return result


# ---- 2. Aging summary --------------------------------------------------------------------------------


async def aging_summary(
    ctx: Ctx,
    f: Filters,
    today: date,
    targets: Targets,
    source: Callable[..., Awaitable[list[Claim]]] = scoped_claims,
) -> Result:
    """`source` gives the claims: the person's scope by default, or a client's practices (client reports)."""
    claims = [c for c in await source(ctx, f, today) if c.work_state != "closed"]
    practices = await practice_names(ctx, {c.practice_id for c in claims})
    groups: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    per_practice: Counter[str] = Counter()
    for c in claims:
        name = practices.get(c.practice_id, "")
        groups[(name, aging(c.service_date, today)[1])].append(c)
        per_practice[name] += 1
    rows = []
    for name in sorted(per_practice):
        for bucket in BUCKET_LABELS:
            items = groups.get((name, bucket), [])
            if not items:
                continue
            billed = sum((money(c.billed) for c in items), Decimal(0))
            recovered = sum((money(c.recovered_amount) for c in items), Decimal(0))
            rows.append(
                {
                    "practice": name,
                    "bucket": bucket,
                    "claims": len(items),
                    "share": percent(len(items), per_practice[name]),
                    "billed": billed,
                    "recovered": recovered,
                    "unrecovered": billed - recovered,
                }
            )
    over_90 = sum(1 for c in claims if aging(c.service_date, today)[0] > 90)
    share_90 = percent(over_90, len(claims)) or 0.0
    result = Result(
        [
            Column(key="practice", label="Practice"),
            Column(key="bucket", label="Aging (days)"),
            Column(key="claims", label="Open claims", kind="int"),
            Column(key="share", label="Share of practice", kind="percent"),
            Column(key="billed", label="Billed", kind="money"),
            Column(key="recovered", label="Recovered", kind="money"),
            Column(key="unrecovered", label="Unrecovered", kind="money"),
        ],
        rows,
        group_by="practice",
        sum_keys=("claims", "billed", "recovered", "unrecovered"),
        extra_totals={"share": 100.0 if claims else None},
    )
    result.notes = [
        f"Open claims (not closed), aged from the service date as of {today:%d %b %Y}.",
        f"{over_90} of {len(claims)} open claims are over 90 days ({share_90}%); "
        f"target: at most {targets.aging_over_90_pct}%.",
    ]
    return result


# ---- 3. Recovery summary -------------------------------------------------------------------------------


async def recovery(
    ctx: Ctx,
    f: Filters,
    today: date,
    targets: Targets,
    source: Callable[..., Awaitable[list[Claim]]] = scoped_claims,
) -> Result:
    dated = f.date_from is not None or f.date_to is not None
    claims = await source(ctx, f, today, date_column=Claim.payment_posted_date if dated else None)
    claims = [c for c in claims if c.recovered_amount is not None or c.allowed_amount is not None]
    practices = await practice_names(ctx, {c.practice_id for c in claims})
    groups: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for c in claims:
        groups[(practices.get(c.practice_id, ""), c.insurance_carrier)].append(c)
    rows = []
    for (name, payer), items in sorted(groups.items()):
        billed = sum((money(c.billed) for c in items), Decimal(0))
        recovered = sum((money(c.recovered_amount) for c in items), Decimal(0))
        rows.append(
            {
                "practice": name,
                "payer": payer,
                "claims": len(items),
                "billed": billed,
                "allowed": sum((money(c.allowed_amount) for c in items), Decimal(0)),
                "recovered": recovered,
                "patient_resp": sum((money(c.patient_responsibility) for c in items), Decimal(0)),
                "rate": percent(recovered, billed),
            }
        )
    result = Result(
        [
            Column(key="practice", label="Practice"),
            Column(key="payer", label="Payer"),
            Column(key="claims", label="Claims", kind="int"),
            Column(key="billed", label="Billed", kind="money"),
            Column(key="allowed", label="Allowed", kind="money"),
            Column(key="recovered", label="Recovered", kind="money"),
            Column(key="patient_resp", label="Patient resp.", kind="money"),
            Column(key="rate", label="Recovered of billed", kind="percent"),
        ],
        rows,
        group_by="practice",
        sum_keys=("claims", "billed", "allowed", "recovered", "patient_resp"),
    )
    t = result.totals()
    result.extra_totals = {"rate": percent(t["recovered"], t["billed"])}
    basis = "payment posted date in the period" if dated else "any recorded payment"
    result.notes = [f"Claims with an allowed or recovered amount ({basis})."]
    return result


# ---- 4. Follow-ups due and overdue -------------------------------------------------------------------


async def followups(ctx: Ctx, f: Filters, today: date, targets: Targets) -> Result:
    claims = await scoped_claims(ctx, f, today)
    upto = f.date_to or today
    claims = [
        c
        for c in claims
        if c.work_state != "closed"
        and c.followup_date is not None
        and c.followup_date <= upto
        and (f.date_from is None or c.followup_date >= f.date_from)
    ]
    practices = await practice_names(ctx, {c.practice_id for c in claims})
    names = await people(ctx, {c.assigned_user_id for c in claims if c.assigned_user_id})
    claims.sort(key=lambda c: (c.followup_date, c.number))
    rows = [
        {
            "claim": claim_label(c.number),
            "practice": practices.get(c.practice_id, ""),
            "patient": c.patient_name,
            "payer": c.insurance_carrier,
            "followup": c.followup_date,
            "days_overdue": max((today - c.followup_date).days, 0),
            "claim_status": c.claim_status or "No status",
            "priority": c.priority.title(),
            "assigned_to": names[c.assigned_user_id][0] if c.assigned_user_id in names else "Unassigned",
            "billed": money(c.billed),
        }
        for c in claims
    ]
    overdue = sum(1 for r in rows if r["days_overdue"] > 0)
    result = Result(
        [
            Column(key="claim", label="Claim"),
            Column(key="practice", label="Practice"),
            Column(key="patient", label="Patient"),
            Column(key="payer", label="Payer"),
            Column(key="followup", label="Follow-up", kind="date"),
            Column(key="days_overdue", label="Days overdue", kind="int"),
            Column(key="claim_status", label="Claim status"),
            Column(key="priority", label="Priority"),
            Column(key="assigned_to", label="Assigned to"),
            Column(key="billed", label="Billed", kind="money"),
        ],
        rows,
        sum_keys=("billed",),
    )
    result.notes = [
        f"{len(rows)} follow-ups due by {upto:%d %b %Y}: {overdue} overdue, {len(rows) - overdue} due."
    ]
    return result


# ---- 5. Team productivity (staff-level) -------------------------------------------------------------

WORK_ACTIONS = {"claim.updated", "claim.note_added", "claim.eob_attached", "claim.completion_requested"}
LIFECYCLE_ACTIONS = {"claim.completion_requested", "claim.returned", "claim.closed"}


async def productivity(ctx: Ctx, f: Filters, today: date, targets: Targets) -> Result:
    lo, hi = day_bounds(f, 30, today)
    first_day = f.date_from or today - timedelta(days=29)
    last_day = f.date_to or today
    practices = ctx.access.practices_with("reports.staff")
    if f.practice_ids:
        practices = set(f.practice_ids) if practices is None else practices & set(f.practice_ids)

    events_q = select(AuditEvent).where(
        AuditEvent.entity_type == "claim", AuditEvent.action.in_(WORK_ACTIONS | LIFECYCLE_ACTIONS)
    )
    if lo:
        events_q = events_q.where(AuditEvent.occurred_at >= lo)
    if hi:
        events_q = events_q.where(AuditEvent.occurred_at <= hi)
    if practices is not None:
        events_q = events_q.where(AuditEvent.practice_id.in_(practices))
    events = list(await ctx.db.scalars(events_q.order_by(AuditEvent.occurred_at, AuditEvent.id)))

    worked: dict[uuid.UUID, set[str]] = defaultdict(set)
    updates: Counter[uuid.UUID] = Counter()
    notes: Counter[uuid.UUID] = Counter()
    completions: Counter[uuid.UUID] = Counter()
    first_pass: Counter[uuid.UUID] = Counter()  # claims approved without ever being returned
    corrected: Counter[uuid.UUID] = Counter()  # claims returned at least once (counted once per claim)
    returned: Counter[uuid.UUID] = Counter()  # every return
    requester: dict[str, uuid.UUID] = {}
    sent_back: set[str] = set()
    closed_claims: set[str] = set()
    for e in events:
        actor = e.actor_user_id
        if actor and e.action in WORK_ACTIONS:
            worked[actor].add(e.entity_id)
        if actor and e.action == "claim.updated":
            updates[actor] += 1
        if actor and e.action == "claim.note_added":
            notes[actor] += 1
        if e.action == "claim.completion_requested" and actor:
            completions[actor] += 1
            requester[e.entity_id] = actor
        elif e.action == "claim.returned" and e.entity_id in requester:
            if (e.before or {}).get("work_state") == "pending_completion":
                person = requester[e.entity_id]
                returned[person] += 1
                if e.entity_id not in sent_back:
                    corrected[person] += 1
                    sent_back.add(e.entity_id)
        elif e.action == "claim.closed":
            closed_claims.add(e.entity_id)
            if (e.after or {}).get("approved_completion") and e.entity_id in requester:
                if e.entity_id not in sent_back:
                    first_pass[requester[e.entity_id]] += 1
            sent_back.discard(e.entity_id)  # a reopened claim starts a new cycle
            requester.pop(e.entity_id, None)

    open_claims = [
        c
        for c in await scoped_claims(ctx, Filters(practice_ids=f.practice_ids), today)
        if c.work_state != "closed"
        and c.assigned_user_id
        and (practices is None or c.practice_id in practices)
    ]
    open_now = Counter(c.assigned_user_id for c in open_claims)
    overdue_now = Counter(
        c.assigned_user_id for c in open_claims if c.followup_date and c.followup_date < today
    )
    closed_rows = (
        list(
            await ctx.db.scalars(
                select(Claim).where(cast(Claim.id, Text).in_(closed_claims), Claim.work_state == "closed")
            )
        )
        if closed_claims
        else []
    )
    closed_by_person: Counter[uuid.UUID] = Counter()
    recovered_by_person: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for c in closed_rows:
        if c.assigned_user_id:
            closed_by_person[c.assigned_user_id] += 1
            recovered_by_person[c.assigned_user_id] += money(c.recovered_amount)

    everyone = set(worked) | set(open_now) | set(completions)
    if f.team_id:
        everyone &= await team_member_ids(ctx, f.team_id)
    if f.assigned_user_id:
        everyone &= {f.assigned_user_id}
    names = await people(ctx, everyone)
    days = business_days(first_day, last_day)
    rows = []
    for person in sorted(everyone, key=lambda p: names.get(p, ("", ""))[0]):
        name, role = names.get(person, ("Unknown", ""))
        reviewed = first_pass[person] + corrected[person]
        quality = percent(first_pass[person], reviewed)
        per_day = round(len(worked[person]) / days, 1)
        flags = []
        if worked[person] and per_day < targets.claims_worked_per_day:
            flags.append(f"below {targets.claims_worked_per_day}/day")
        if quality is not None and quality < targets.first_pass_quality_pct:
            flags.append(f"quality below {targets.first_pass_quality_pct}%")
        if overdue_now[person] > targets.overdue_followups_per_person:
            flags.append(f"over {targets.overdue_followups_per_person} overdue")
        rows.append(
            {
                "person": name,
                "role": role,
                "open_now": open_now[person],
                "overdue_now": overdue_now[person],
                "worked": len(worked[person]),
                "per_day": per_day,
                "updates": updates[person],
                "notes": notes[person],
                "completions": completions[person],
                "first_pass": quality,
                "returned": returned[person],
                "closed": closed_by_person[person],
                "recovered": recovered_by_person[person],
                "flags": ", ".join(flags),
            }
        )
    result = Result(
        [
            Column(key="person", label="Person"),
            Column(key="role", label="Role"),
            Column(key="open_now", label="Open now", kind="int"),
            Column(key="overdue_now", label="Overdue now", kind="int"),
            Column(key="worked", label="Claims worked", kind="int"),
            Column(key="per_day", label="Per working day", kind="int"),
            Column(key="updates", label="Updates", kind="int"),
            Column(key="notes", label="Notes", kind="int"),
            Column(key="completions", label="Marked complete", kind="int"),
            Column(key="first_pass", label="First-pass rate", kind="percent"),
            Column(key="returned", label="Returned", kind="int"),
            Column(key="closed", label="Closed", kind="int"),
            Column(key="recovered", label="Recovered on closed", kind="money"),
            Column(key="flags", label="Against targets"),
        ],
        rows,
        sum_keys=(
            "open_now",
            "overdue_now",
            "worked",
            "updates",
            "notes",
            "completions",
            "returned",
            "closed",
            "recovered",
        ),
    )
    result.notes = [
        f"Activity from {first_day:%d %b %Y} to {last_day:%d %b %Y} ({days} working days). "
        "Claims worked = distinct claims a person updated, noted, attached an EOB to or marked complete.",
        "First-pass rate = claims approved without ever being returned, of all claims reviewed. "
        f"Targets: {targets.claims_worked_per_day} claims worked per day, "
        f"{targets.first_pass_quality_pct}% first-pass, "
        f"at most {targets.overdue_followups_per_person} overdue.",
    ]
    return result


# ---- 6. Uploads and data quality ---------------------------------------------------------------------


async def uploads(ctx: Ctx, f: Filters, today: date, targets: Targets) -> Result:
    lo, hi = day_bounds(f, None, today)
    statement = visible_uploads(select(Upload), ctx)
    if f.practice_ids:
        statement = statement.where(Upload.practice_id.in_(f.practice_ids))
    if f.upload_id:
        statement = statement.where(Upload.id == f.upload_id)
    if lo:
        statement = statement.where(Upload.created_at >= lo)
    if hi:
        statement = statement.where(Upload.created_at <= hi)
    items = list(await ctx.db.scalars(statement.order_by(Upload.number)))
    practices = await practice_names(ctx, {u.practice_id for u in items})
    names = await people(ctx, {p for u in items for p in (u.uploaded_by, u.decided_by) if p})
    rows = []
    differ = 0
    for u in items:
        if u.new_rows + u.duplicate_rows + u.changed_rows + u.repeat_rows == 0 and u.created_claims:
            accounted = (
                u.created_claims + u.duplicate_rows + u.error_rows
            )  # uploads from before import approval
        else:
            accounted = u.new_rows + u.duplicate_rows + u.changed_rows + u.repeat_rows + u.error_rows
        balanced = accounted == u.total_rows or u.status == "failed"
        check = "Balanced" if balanced else f"Differs by {u.total_rows - accounted}"
        differ += not balanced
        rows.append(
            {
                "upload": upload_label(u.number),
                "practice": practices.get(u.practice_id, ""),
                "file": u.file_name,
                "uploaded_by": names.get(u.uploaded_by, ("", ""))[0],
                "uploaded_at": u.created_at,
                "status": UPLOAD_STATUS_LABELS.get(u.status, u.status),
                "rows": u.total_rows,
                "new": u.new_rows,
                "duplicate": u.duplicate_rows,
                "changed": u.changed_rows + u.repeat_rows,
                "errors": u.error_rows,
                "created": u.created_claims,
                "updated": u.updated_claims,
                "approved_by": names.get(u.decided_by, ("", ""))[0]
                if u.status in ("committed", "reversed")
                else "",
                "check": check,
            }
        )
    result = Result(
        [
            Column(key="upload", label="Upload"),
            Column(key="practice", label="Practice"),
            Column(key="file", label="File"),
            Column(key="uploaded_by", label="Uploaded by"),
            Column(key="uploaded_at", label="Uploaded", kind="datetime"),
            Column(key="status", label="Status"),
            Column(key="rows", label="Rows", kind="int"),
            Column(key="new", label="New", kind="int"),
            Column(key="duplicate", label="Already in system", kind="int"),
            Column(key="changed", label="Changed or repeated", kind="int"),
            Column(key="errors", label="Errors", kind="int"),
            Column(key="created", label="Claims created", kind="int"),
            Column(key="updated", label="Claims updated", kind="int"),
            Column(key="approved_by", label="Approved by"),
            Column(key="check", label="Reconciliation"),
        ],
        rows,
        sum_keys=("rows", "new", "duplicate", "changed", "errors", "created", "updated"),
    )
    result.notes = [
        "Reconciliation: rows in the file = new + already in system + changed or repeated + errors.",
        f"{len(rows) - differ} of {len(rows)} uploads balance." if rows else "No uploads in the period.",
    ]
    return result


# ---- 7. Claim activity ledger ------------------------------------------------------------------------


def _show(key: str, value: Any, names: dict[uuid.UUID, tuple[str, str]]) -> str:
    if value is None or value == "":
        return "empty"
    if key == "assigned_user_id":
        try:
            return names.get(uuid.UUID(str(value)), ("another person", ""))[0]
        except ValueError:
            return "another person"
    if key == "work_state":
        return WORK_STATE_LABELS.get(str(value), str(value))
    return str(value)


def _describe(event: AuditEvent, names: dict[uuid.UUID, tuple[str, str]]) -> str:
    before, after = event.before or {}, event.after or {}
    parts = []
    for key in sorted(set(before) | set(after)):
        if key in LEDGER_HIDDEN:
            continue
        label = FIELD_LABELS.get(key, key.replace("_", " "))
        if key in before:
            parts.append(
                f"{label}: {_show(key, before.get(key), names)} -> {_show(key, after.get(key), names)}"
            )
        else:
            parts.append(f"{label}: {_show(key, after.get(key), names)}")
    return "; ".join(parts)


async def ledger(ctx: Ctx, f: Filters, today: date, targets: Targets) -> Result:
    lo, hi = day_bounds(f, 30, today)
    visible = await scoped_claims(ctx, Filters(**f.model_dump(exclude={"date_from", "date_to"})), today)
    by_id = {str(c.id): c for c in visible}
    rows: list[dict[str, Any]] = []
    truncated = False
    if by_id:
        statement = select(AuditEvent).where(
            AuditEvent.entity_type == "claim", AuditEvent.entity_id.in_(list(by_id))
        )
        if lo:
            statement = statement.where(AuditEvent.occurred_at >= lo)
        if hi:
            statement = statement.where(AuditEvent.occurred_at <= hi)
        events = list(
            await ctx.db.scalars(
                statement.order_by(AuditEvent.occurred_at, AuditEvent.id).limit(LEDGER_LIMIT + 1)
            )
        )
        truncated = len(events) > LEDGER_LIMIT
        events = events[:LEDGER_LIMIT]
        people_ids = {e.actor_user_id for e in events if e.actor_user_id}
        for e in events:
            for side in (e.before or {}, e.after or {}):
                value = side.get("assigned_user_id")
                if value:
                    try:
                        people_ids.add(uuid.UUID(str(value)))
                    except ValueError:
                        pass
        names = await people(ctx, people_ids)
        practices = await practice_names(ctx, {c.practice_id for c in visible})
        for e in events:
            claim = by_id[e.entity_id]
            rows.append(
                {
                    "time": e.occurred_at,
                    "claim": claim_label(claim.number),
                    "practice": practices.get(claim.practice_id, ""),
                    "action": ACTION_LABELS.get(e.action, e.action),
                    "by": names.get(e.actor_user_id, ("System", ""))[0] if e.actor_user_id else "System",
                    "details": _describe(e, names),
                }
            )
    result = Result(
        [
            Column(key="time", label="When", kind="datetime"),
            Column(key="claim", label="Claim"),
            Column(key="practice", label="Practice"),
            Column(key="action", label="What happened"),
            Column(key="by", label="By"),
            Column(key="details", label="Details"),
        ],
        rows,
    )
    result.notes = [
        f"{len(rows)} events, oldest first. Note text is not included; it stays on the claim screen."
        + (f" Only the first {LEDGER_LIMIT} events are included; narrow the filters." if truncated else "")
    ]
    return result


CLAIM_FILTERS = (
    "practice_ids",
    "payer",
    "claim_statuses",
    "work_states",
    "assigned_user_id",
    "team_id",
    "upload_id",
    "aging_buckets",
    "priorities",
)
CATALOGUE: dict[str, Report] = {
    r.key: r
    for r in (
        Report(
            "statement",
            "AR claims statement",
            "Every claim with its amounts, status, assignee, follow-up and aging; subtotals per practice.",
            "Service date",
            ("date_from", "date_to", *CLAIM_FILTERS),
            True,
            False,
            statement,
        ),
        Report(
            "aging",
            "Aging summary",
            "Open claims per practice and aging bucket, with billed, recovered and unrecovered amounts.",
            "As of today",
            CLAIM_FILTERS,
            False,
            False,
            aging_summary,
        ),
        Report(
            "recovery",
            "Recovery summary",
            "Billed, allowed, recovered and patient responsibility per practice and payer, "
            "with the recovery rate.",
            "Payment posted date",
            ("date_from", "date_to", *CLAIM_FILTERS),
            False,
            False,
            recovery,
        ),
        Report(
            "followups",
            "Follow-ups due and overdue",
            "Open claims with a follow-up date up to the end date (today if none), oldest first.",
            "Follow-up date",
            ("date_from", "date_to", *CLAIM_FILTERS),
            True,
            False,
            followups,
        ),
        Report(
            "productivity",
            "Team productivity",
            "Per person: open and overdue work, claims worked, completions, first-pass rate, returns, "
            "closures and recovered amounts, against the targets.",
            "Activity date (default: last 30 days)",
            ("date_from", "date_to", "practice_ids", "assigned_user_id", "team_id"),
            False,
            True,
            productivity,
        ),
        Report(
            "uploads",
            "Uploads and data quality",
            "Every upload with its row counts, outcome, approver and a reconciliation check.",
            "Upload date",
            ("date_from", "date_to", "practice_ids", "upload_id"),
            False,
            False,
            uploads,
        ),
        Report(
            "ledger",
            "Claim activity ledger",
            "Every recorded event on the claims in scope: who did what, when, with old and new values.",
            "Event date (default: last 30 days)",
            ("date_from", "date_to", *CLAIM_FILTERS),
            False,
            False,
            ledger,
        ),
    )
}
