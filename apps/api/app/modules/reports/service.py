"""
Running reports, generating files, and the report dashboards (brief sections 6 and 10).

- Permissions are checked when a report is run or a file generated, and again when it is downloaded.
- Every file is logged with its filters, scope, requester, row count and every download; Management and
  the other oversight holders are notified of each one.
- Files expire after the retention period in the report targets, and only the requester can download them.
"""

import re
import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core import audit
from app.core.clock import aging, business_today
from app.core.context import Ctx
from app.core.schemas import NamedRef
from app.core.storage import get_storage
from app.modules.claims import repository as claims_repo
from app.modules.claims.models import Claim
from app.modules.notifications import service as notify
from app.modules.practices.models import Practice, Team
from app.modules.reports.catalogue import (
    BUCKET_LABELS,
    CATALOGUE,
    Report,
    Result,
    money,
    people,
    scoped_claims,
)
from app.modules.reports.models import AppSetting, ReportExport
from app.modules.reports.render import Meta, to_csv, to_pdf, to_xlsx
from app.modules.reports.schemas import (
    Alert,
    Bar,
    CatalogueItem,
    ExportOut,
    Filters,
    Overview,
    ReportRun,
    Targets,
)
from app.modules.uploads.models import Upload
from app.modules.uploads.schemas import upload_label
from app.modules.users.models import User

PREVIEW_ROWS = 500
MEDIA = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}
DEFAULT_TARGETS = Targets(
    claims_worked_per_day=25,
    first_pass_quality_pct=90,
    overdue_followups_per_person=10,
    aging_over_90_pct=20,
    export_retention_days=7,
)


def export_label(number: int) -> str:
    return f"EXP-{number:06d}"


# ---- Targets (management decision #7) -----------------------------------------------------------------


async def get_targets(ctx: Ctx) -> Targets:
    row = await ctx.db.get(AppSetting, "report_targets")
    if row is None:
        return DEFAULT_TARGETS
    return Targets(**{**DEFAULT_TARGETS.model_dump(), **row.value})


async def set_targets(ctx: Ctx, targets: Targets) -> Targets:
    before = (await get_targets(ctx)).model_dump()
    row = await ctx.db.get(AppSetting, "report_targets")
    if row is None:
        row = AppSetting(key="report_targets", value={})
        ctx.db.add(row)
    row.value, row.updated_by, row.updated_at = targets.model_dump(), ctx.user.id, datetime.now(UTC)
    changed = {k: v for k, v in targets.model_dump().items() if before[k] != v}
    if changed:
        audit.record(
            ctx.db,
            action="settings.changed",
            entity_type="setting",
            entity_id="report_targets",
            actor_user_id=ctx.user.id,
            before={k: before[k] for k in changed},
            after=changed,
        )
    await ctx.db.commit()
    return targets


# ---- Catalogue and permissions --------------------------------------------------------------------------


def _report(ctx: Ctx, key: str) -> Report:
    report = CATALOGUE.get(key)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    if report.staff and not ctx.can("reports.staff"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: reports.staff")
    return report


def catalogue(ctx: Ctx) -> list[CatalogueItem]:
    return [
        CatalogueItem(
            key=r.key,
            title=r.title,
            description=r.description,
            date_basis=r.date_basis,
            filters=list(r.filters),
            contains_phi=r.contains_phi,
            staff=r.staff,
        )
        for r in CATALOGUE.values()
        if not r.staff or ctx.can("reports.staff")
    ]


# ---- Labels for the parameters printed on every report ---------------------------------------------------


async def filter_labels(ctx: Ctx, f: Filters) -> list[str]:
    labels = []
    if f.practice_ids:
        names = (await ctx.db.execute(select(Practice.name).where(Practice.id.in_(f.practice_ids)))).scalars()
        labels.append("Practices: " + ", ".join(sorted(names)))
    if f.payer:
        labels.append(f"Payer contains: {f.payer}")
    if f.claim_statuses:
        labels.append("Claim status: " + ", ".join(f.claim_statuses))
    if f.work_states:
        states = {"open": "Open", "pending_completion": "Awaiting completion", "closed": "Closed"}
        labels.append("Work status: " + ", ".join(states[s] for s in f.work_states))
    if f.assigned_user_id:
        person = await ctx.db.get(User, f.assigned_user_id)
        labels.append(f"Person: {person.full_name if person else 'unknown'}")
    if f.team_id:
        team = await ctx.db.get(Team, f.team_id)
        labels.append(f"Team: {team.name if team else 'unknown'}")
    if f.upload_id:
        upload = await ctx.db.get(Upload, f.upload_id)
        labels.append(f"Upload: {upload_label(upload.number) if upload else 'unknown'}")
    if f.aging_buckets:
        labels.append("Aging: " + ", ".join(f.aging_buckets))
    if f.priorities:
        labels.append("Priority: " + ", ".join(p.title() for p in f.priorities))
    return labels


def period_label(report: Report, f: Filters, today: date) -> str:
    if report.key == "aging":
        return f"As of {today:%d %b %Y}"
    start, end = f.date_from, f.date_to
    if start is None and end is None:
        if report.key in ("productivity", "ledger"):
            start, end = today - timedelta(days=29), today
        elif report.key == "followups":
            return f"Follow-ups due up to {today:%d %b %Y}"
        else:
            return "All dates"
    basis = report.date_basis.split(" (")[0]
    first = f"{start:%d %b %Y}" if start else "the beginning"
    last = f"{end:%d %b %Y}" if end else "today"
    return f"{basis}: {first} to {last}"


async def scope_label(ctx: Ctx, f: Filters) -> list[str]:
    if ctx.access.all_practices and not f.practice_ids:
        return ["All practices"]
    ids = set(ctx.access.reachable_practice_ids)
    if ctx.access.all_practices:
        ids = set(f.practice_ids)
    elif f.practice_ids:
        ids &= set(f.practice_ids)
    if not ids:
        return ["No practices"]
    return sorted((await ctx.db.execute(select(Practice.name).where(Practice.id.in_(ids)))).scalars())


async def _build(ctx: Ctx, report: Report, f: Filters) -> tuple[Result, date]:
    if f.date_from and f.date_to and f.date_from > f.date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The start date is after the end date.")
    today = business_today()
    return await report.build(ctx, f, today, await get_targets(ctx)), today


# ---- Run on screen ------------------------------------------------------------------------------------


async def run(ctx: Ctx, key: str, f: Filters) -> ReportRun:
    report = _report(ctx, key)
    result, today = await _build(ctx, report, f)
    labels = await filter_labels(ctx, f)
    audit.record(
        ctx.db,
        action="report.viewed",
        entity_type="report",
        entity_id=report.key,
        actor_user_id=ctx.user.id,
        after={"report": report.title, "filters": labels, "rows": len(result.rows)},
    )
    await ctx.db.commit()
    return ReportRun(
        key=report.key,
        title=report.title,
        period=period_label(report, f, today),
        filters_label=labels,
        scope=await scope_label(ctx, f),
        generated_at=datetime.now(UTC),
        columns=result.columns,
        rows=result.rows[:PREVIEW_ROWS],
        row_count=len(result.rows),
        shown=min(len(result.rows), PREVIEW_ROWS),
        totals=result.totals(),
        notes=result.notes,
        contains_phi=report.contains_phi,
    )


# ---- Export files -----------------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def _title(export: ReportExport) -> str:
    if export.report_key in CATALOGUE:
        return CATALOGUE[export.report_key].title
    if export.report_key.startswith("client."):
        from app.modules.clients.service import CLIENT_REPORTS

        name = CLIENT_REPORTS.get(export.report_key.removeprefix("client."), export.report_key)
        return f"{name} (client: {export.filters.get('client', '')})"
    return export.report_key


async def _out(ctx: Ctx, exports: list[ReportExport]) -> list[ExportOut]:
    names = await people(ctx, {e.requested_by for e in exports})
    now = datetime.now(UTC)
    may_download = ctx.can("reports.export")
    return [
        ExportOut(
            id=e.id,
            number=export_label(e.number),
            report_key=e.report_key,
            report_title=_title(e),
            format=e.format,  # type: ignore[arg-type]
            file_name=e.file_name,
            file_size=e.file_size,
            row_count=e.row_count,
            filters_label=list(e.filters.get("labels", [])),
            scope=list(e.scope),
            contains_phi=e.contains_phi,
            requested_by=NamedRef(id=e.requested_by, name=names.get(e.requested_by, ("", ""))[0]),
            created_at=e.created_at,
            expires_at=e.expires_at,
            expired=e.expires_at <= now or not e.storage_key,
            download_count=e.download_count,
            last_downloaded_at=e.last_downloaded_at,
            can_download=may_download
            and e.requested_by == ctx.user.id
            and e.expires_at > now
            and bool(e.storage_key),
        )
        for e in exports
    ]


async def _remove_expired(ctx: Ctx) -> None:
    """Expired files are deleted from storage (the log entry stays)."""
    storage = get_storage()
    expired = await ctx.db.scalars(
        select(ReportExport).where(
            ReportExport.expires_at <= datetime.now(UTC), ReportExport.storage_key != ""
        )
    )
    for export in expired:
        storage.delete(export.storage_key)
        export.storage_key = ""


async def export(ctx: Ctx, key: str, file_format: str, f: Filters) -> ExportOut:
    if not ctx.can("reports.export"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: reports.export")
    report = _report(ctx, key)
    result, today = await _build(ctx, report, f)
    labels = await filter_labels(ctx, f)
    scope = await scope_label(ctx, f)
    targets = await get_targets(ctx)
    now = datetime.now(UTC)

    record = ReportExport(
        report_key=report.key,
        format=file_format,
        filters={"labels": labels, "values": f.model_dump(mode="json", exclude_defaults=True)},
        scope=scope,
        row_count=len(result.rows),
        file_name="",
        storage_key="",
        contains_phi=report.contains_phi,
        requested_by=ctx.user.id,
        expires_at=now + timedelta(days=targets.export_retention_days),
    )
    ctx.db.add(record)
    await ctx.db.flush()
    reference = export_label(record.number)
    meta = Meta(
        title=report.title,
        period=period_label(report, f, today),
        filters=labels,
        scope=scope,
        generated_at=now,
        generated_by=ctx.user.full_name,
        reference=reference,
        contains_phi=report.contains_phi,
    )
    if file_format == "csv":
        data = to_csv(result)
    elif file_format == "xlsx":
        data = to_xlsx(result, meta)
    else:
        data = to_pdf(result, meta)
    record.file_name = f"{_slug(report.title)}_{today.isoformat()}_{reference}.{file_format}"
    record.storage_key = f"exports/{record.id}/{record.file_name}"
    record.file_size = len(data)
    get_storage().save(record.storage_key, data)
    await _remove_expired(ctx)

    audit.record(
        ctx.db,
        action="report.exported",
        entity_type="report_export",
        entity_id=record.id,
        actor_user_id=ctx.user.id,
        after={
            "export": reference,
            "report": report.title,
            "format": file_format.upper(),
            "filters": labels,
            "scope": scope,
            "rows": len(result.rows),
            "contains_phi": report.contains_phi,
        },
    )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="report.exported",
        title=f"{ctx.user.full_name} exported {report.title} "
        f"({file_format.upper()}, {len(result.rows)} rows)",
        body="; ".join(labels) or None,
        link="/reports?view=exports",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(record)
    return (await _out(ctx, [record]))[0]


async def list_exports(ctx: Ctx, everyone: bool) -> list[ExportOut]:
    statement = select(ReportExport)
    if not (everyone and ctx.can("notifications.oversight")):
        statement = statement.where(ReportExport.requested_by == ctx.user.id)
    rows = list(await ctx.db.scalars(statement.order_by(ReportExport.number.desc()).limit(200)))
    return await _out(ctx, rows)


async def download(ctx: Ctx, export_id: uuid.UUID) -> tuple[ReportExport, bytes]:
    """Checked again at download: the requester only, still allowed, not expired. Every download is logged."""
    record = await ctx.db.get(ReportExport, export_id)
    if record is None or record.requested_by != ctx.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found.")
    if not ctx.can("reports.export"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: reports.export")
    report = CATALOGUE.get(record.report_key)
    if report and report.staff and not ctx.can("reports.staff"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: reports.staff")
    if record.expires_at <= datetime.now(UTC) or not record.storage_key:
        raise HTTPException(status.HTTP_410_GONE, "This export has expired. Generate the report again.")
    data = get_storage().read(record.storage_key)
    record.download_count += 1
    record.last_downloaded_at = datetime.now(UTC)
    audit.record(
        ctx.db,
        action="report.downloaded",
        entity_type="report_export",
        entity_id=record.id,
        actor_user_id=ctx.user.id,
        after={
            "export": export_label(record.number),
            "format": record.format.upper(),
            "rows": record.row_count,
        },
    )
    await ctx.db.commit()
    return record, data


async def people_in_scope(ctx: Ctx) -> list[NamedRef]:
    """People assigned to claims this person can see: the choices for the Person filter."""
    statement = select(Claim.assigned_user_id).where(Claim.assigned_user_id.is_not(None)).distinct()
    ids = set(await ctx.db.scalars(claims_repo.visible(statement, ctx)))
    names = await people(ctx, ids)
    return sorted((NamedRef(id=i, name=n) for i, (n, _) in names.items()), key=lambda r: r.name)


# ---- The AR performance dashboard -------------------------------------------------------------------


def _paid_on(claim: Claim) -> date | None:
    return claim.payment_posted_date or claim.cashed_date


async def overview(ctx: Ctx, practice_ids: list[uuid.UUID]) -> Overview:
    today = business_today()
    targets = await get_targets(ctx)
    claims = await scoped_claims(ctx, Filters(practice_ids=practice_ids), today)
    open_ = [c for c in claims if c.work_state != "closed"]
    month_start = today.replace(day=1)

    buckets: Counter[str] = Counter()
    bucket_amount: dict[str, Decimal] = defaultdict(Decimal)
    for c in open_:
        label = aging(c.service_date, today)[1]
        buckets[label] += 1
        bucket_amount[label] += money(c.billed) - money(c.recovered_amount)
    statuses: Counter[str] = Counter(c.claim_status or "No status" for c in open_)
    seen = {c.practice_id for c in claims}
    names = (
        dict((await ctx.db.execute(select(Practice.id, Practice.name).where(Practice.id.in_(seen)))).all())
        if seen
        else {}
    )
    by_practice_count: Counter[str] = Counter(names.get(c.practice_id, "") for c in open_)
    by_practice_amount: dict[str, Decimal] = defaultdict(Decimal)
    for c in open_:
        by_practice_amount[names.get(c.practice_id, "")] += money(c.billed) - money(c.recovered_amount)

    months = []
    cursor = month_start
    for _ in range(6):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    recovered_month: dict[date, Decimal] = defaultdict(Decimal)
    paid_count: Counter[date] = Counter()
    for c in claims:
        paid = _paid_on(c)
        if paid and c.recovered_amount is not None:
            recovered_month[paid.replace(day=1)] += money(c.recovered_amount)
            paid_count[paid.replace(day=1)] += 1

    over_90 = sum(1 for c in open_ if aging(c.service_date, today)[0] > 90)
    over_90_pct = round(over_90 / len(open_) * 100, 1) if open_ else 0.0
    overdue = sum(1 for c in open_ if c.followup_date and c.followup_date < today)
    awaiting = sum(1 for c in open_ if c.work_state == "pending_completion")

    workload: list[Bar] | None = None
    alerts: list[Alert] = []
    if ctx.can("reports.staff"):
        staff_practices = ctx.access.practices_with("reports.staff")
        mine = [
            c
            for c in open_
            if c.assigned_user_id and (staff_practices is None or c.practice_id in staff_practices)
        ]
        open_by: Counter = Counter(c.assigned_user_id for c in mine)
        overdue_by: Counter = Counter(
            c.assigned_user_id for c in mine if c.followup_date and c.followup_date < today
        )
        who = await people(ctx, set(open_by))
        workload = [
            Bar(label=who.get(p, ("Unknown", ""))[0], count=n, secondary=overdue_by[p])
            for p, n in open_by.most_common(15)
        ]
        limit = targets.overdue_followups_per_person
        heavy = sorted(who.get(p, ("Unknown", ""))[0] for p, n in overdue_by.items() if n > limit)
        if heavy:
            more = "…" if len(heavy) > 5 else ""
            alerts.append(
                Alert(
                    tone="warn",
                    text=f"{len(heavy)} person(s) have more than {limit} overdue follow-ups: "
                    f"{', '.join(heavy[:5])}{more}",
                    link="/reports?view=productivity",
                )
            )
    if over_90_pct > targets.aging_over_90_pct:
        alerts.append(
            Alert(
                tone="danger",
                text=f"{over_90_pct}% of open claims are over 90 days old "
                f"(target: at most {targets.aging_over_90_pct}%).",
                link="/reports?view=run&report=aging",
            )
        )
    if overdue:
        alerts.append(
            Alert(tone="warn", text=f"{overdue} follow-up(s) are overdue.", link="/followups?view=overdue")
        )
    if awaiting and ctx.can("claims.close"):
        alerts.append(
            Alert(
                tone="info",
                text=f"{awaiting} claim(s) are waiting for completion review.",
                link="/claims?view=awaiting-completion",
            )
        )

    closed_this_month = sum(
        1
        for c in claims
        if c.work_state == "closed" and c.state_changed_at and c.state_changed_at.date() >= month_start
    )
    return Overview(
        open_claims=len(open_),
        open_billed=sum((money(c.billed) for c in open_), Decimal(0)),
        open_unrecovered=sum((money(c.billed) - money(c.recovered_amount) for c in open_), Decimal(0)),
        recovered_total=sum((money(c.recovered_amount) for c in claims), Decimal(0)),
        recovered_this_month=recovered_month.get(month_start, Decimal(0)),
        due_today=sum(1 for c in open_ if c.followup_date == today),
        overdue=overdue,
        awaiting_completion=awaiting,
        closed_this_month=closed_this_month,
        over_90_pct=over_90_pct,
        aging=[Bar(label=b, count=buckets[b], amount=bucket_amount[b]) for b in BUCKET_LABELS],
        by_status=[Bar(label=s, count=n) for s, n in statuses.most_common(12)],
        by_practice=[
            Bar(label=p, count=n, amount=by_practice_amount[p]) for p, n in by_practice_count.most_common(20)
        ],
        recovered_by_month=[
            Bar(label=m.strftime("%b %Y"), count=paid_count[m], amount=recovered_month[m]) for m in months
        ],
        workload=workload,
        alerts=alerts,
        targets=targets,
    )
