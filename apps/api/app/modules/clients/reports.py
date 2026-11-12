"""
Client reports (Roles & Access specification, sections 5 and 7): a separate catalogue for client accounts.

- Only reports the portal team approved for the organisation, and only its practices (for a Client
  Reporting User, only the practices assigned to them).
- No internal data: no assignee or staff names, notes, internal queues, priorities or import diagnostics.
- Patient names and subscriber IDs only when the portal team switched patient detail on for the client.
- Every run, file and download is logged; the portal team's oversight holders are told of each file.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, select

from app.core import audit
from app.core.clock import aging, business_today
from app.core.context import Ctx
from app.core.schemas import NamedRef
from app.core.storage import get_storage
from app.modules.claims.models import Claim
from app.modules.claims.schemas import claim_label
from app.modules.clients.models import ClientOrganisation, ClientOrgPractice, ClientOrgReport
from app.modules.clients.service import CLIENT_REPORTS
from app.modules.notifications import service as notify
from app.modules.practices.models import Practice, UserPractice
from app.modules.reports import service as internal
from app.modules.reports.catalogue import Result, aging_summary, fmt_money, money, practice_names, recovery
from app.modules.reports.models import ReportExport
from app.modules.reports.render import Meta, to_csv, to_pdf, to_xlsx
from app.modules.reports.schemas import Column, ExportOut, Filters, ReportRun

DESCRIPTIONS = {
    "statement": "Every claim with its payer, amounts, status and aging; subtotals per practice.",
    "aging": "Open claims per practice and aging bucket, with billed, recovered and unrecovered amounts.",
    "recovery": "Billed, allowed, recovered and patient responsibility per practice and payer.",
}
DATE_BASIS = {"statement": "Service date", "aging": "As of today", "recovery": "Payment posted date"}
PROGRESS = {"open": "Being worked", "pending_completion": "Being worked", "closed": "Resolved"}


class ClientFilters(BaseModel):
    """The filters a client may use. Each only narrows the organisation's own practices."""

    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    practice_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    payer: str | None = Field(default=None, max_length=120)
    claim_statuses: list[str] = Field(default_factory=list, max_length=40)
    aging_buckets: list[str] = Field(default_factory=list, max_length=10)


class ClientExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["csv", "xlsx", "pdf"]
    filters: ClientFilters = Field(default_factory=ClientFilters)


class ClientCatalogueItem(BaseModel):
    key: str
    title: str
    description: str
    date_basis: str
    contains_phi: bool


class ClientContext(BaseModel):
    """What a client account's screens need to know about its organisation."""

    organisation: NamedRef
    practices: list[NamedRef]
    patient_detail: bool
    users_delegated: bool
    can_manage_users: bool


# ---- Who and what --------------------------------------------------------------------------------------


async def _org(ctx: Ctx) -> ClientOrganisation:
    if ctx.user.client_org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Client reports are for client accounts.")
    org = await ctx.db.get(ClientOrganisation, ctx.user.client_org_id)
    if org is None or org.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This client organisation is paused.")
    return org


async def _practices(ctx: Ctx, org: ClientOrganisation) -> set[uuid.UUID]:
    """The organisation's practices that this account is assigned to."""
    owned = select(ClientOrgPractice.practice_id).where(ClientOrgPractice.org_id == org.id)
    return set(
        await ctx.db.scalars(
            select(UserPractice.practice_id).where(
                UserPractice.user_id == ctx.user.id, UserPractice.practice_id.in_(owned)
            )
        )
    )


async def _approved(ctx: Ctx, org: ClientOrganisation) -> list[str]:
    keys = set(
        await ctx.db.scalars(select(ClientOrgReport.report_key).where(ClientOrgReport.org_id == org.id))
    )
    return [k for k in CLIENT_REPORTS if k in keys]


async def _report(ctx: Ctx, org: ClientOrganisation, key: str) -> str:
    if key not in await _approved(ctx, org):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This report isn't available to your organisation.")
    return key


async def context(ctx: Ctx) -> ClientContext:
    org = await _org(ctx)
    ids = await _practices(ctx, org)
    names = await practice_names(ctx, ids)
    return ClientContext(
        organisation=NamedRef(id=org.id, name=org.name),
        practices=sorted((NamedRef(id=i, name=n) for i, n in names.items()), key=lambda p: p.name),
        patient_detail=org.patient_detail,
        users_delegated=org.users_delegated,
        can_manage_users=org.users_delegated and ctx.can("client_users.manage"),
    )


async def catalogue(ctx: Ctx) -> list[ClientCatalogueItem]:
    org = await _org(ctx)
    return [
        ClientCatalogueItem(
            key=k,
            title=CLIENT_REPORTS[k],
            description=DESCRIPTIONS[k],
            date_basis=DATE_BASIS[k],
            contains_phi=k == "statement" and org.patient_detail,
        )
        for k in await _approved(ctx, org)
    ]


# ---- Building -----------------------------------------------------------------------------------------


def _source(practices: set[uuid.UUID]) -> Callable[..., Awaitable[list[Claim]]]:
    """Claims of these practices only, narrowed by the client's filters."""

    async def claims(ctx: Ctx, f: Filters, today: date, *, date_column: Any = None) -> list[Claim]:
        wanted = practices & set(f.practice_ids) if f.practice_ids else practices
        if not wanted:
            return []
        statement: Select = select(Claim).where(
            Claim.practice_id.in_(wanted), Claim.merged_into_id.is_(None), Claim.withdrawn_at.is_(None)
        )
        if f.payer:
            statement = statement.where(Claim.insurance_carrier.ilike(f"%{f.payer.strip()}%"))
        if f.claim_statuses:
            named = [s for s in f.claim_statuses if s != "No status"]
            condition = Claim.claim_status.in_(named)
            if "No status" in f.claim_statuses:
                condition = condition | Claim.claim_status.is_(None)
            statement = statement.where(condition)
        if date_column is not None:
            if f.date_from:
                statement = statement.where(date_column >= f.date_from)
            if f.date_to:
                statement = statement.where(date_column <= f.date_to)
        found = list(await ctx.db.scalars(statement))
        if f.aging_buckets:
            found = [c for c in found if aging(c.service_date, today)[1] in f.aging_buckets]
        return found

    return claims


async def _statement(
    ctx: Ctx, f: Filters, today: date, source: Callable[..., Awaitable[list[Claim]]], detail: bool
) -> Result:
    claims = await source(ctx, f, today, date_column=Claim.service_date)
    practices = await practice_names(ctx, {c.practice_id for c in claims})
    claims.sort(key=lambda c: (practices.get(c.practice_id, ""), c.service_date, c.number))
    columns = [Column(key="claim", label="Claim"), Column(key="practice", label="Practice")]
    if detail:
        columns += [
            Column(key="patient", label="Patient"),
            Column(key="subscriber_id", label="Subscriber ID"),
        ]
    columns += [
        Column(key="payer", label="Payer"),
        Column(key="service_date", label="Service date", kind="date"),
        Column(key="billed", label="Billed", kind="money"),
        Column(key="allowed", label="Allowed", kind="money"),
        Column(key="recovered", label="Recovered", kind="money"),
        Column(key="patient_resp", label="Patient resp.", kind="money"),
        Column(key="unrecovered", label="Unrecovered", kind="money"),
        Column(key="claim_status", label="Claim status"),
        Column(key="progress", label="Progress"),
        Column(key="aging_days", label="Aging (days)", kind="int"),
    ]
    rows = []
    for c in claims:
        row = {
            "claim": claim_label(c.number),
            "practice": practices.get(c.practice_id, ""),
            "payer": c.insurance_carrier,
            "service_date": c.service_date,
            "billed": money(c.billed),
            "allowed": money(c.allowed_amount) if c.allowed_amount is not None else None,
            "recovered": money(c.recovered_amount) if c.recovered_amount is not None else None,
            "patient_resp": money(c.patient_responsibility) if c.patient_responsibility is not None else None,
            "unrecovered": money(c.billed) - money(c.recovered_amount),
            "claim_status": c.claim_status or "No status",
            "progress": PROGRESS[c.work_state],
            "aging_days": aging(c.service_date, today)[0],
        }
        if detail:
            row.update(patient=c.patient_name, subscriber_id=c.subscriber_id)
        rows.append(row)
    result = Result(
        columns,
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
    if not detail:
        result.notes.append("Patient names and subscriber IDs are not included.")
    return result


async def _build(ctx: Ctx, key: str, cf: ClientFilters) -> tuple[ClientOrganisation, Result, date]:
    if cf.date_from and cf.date_to and cf.date_from > cf.date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The start date is after the end date.")
    org = await _org(ctx)
    await _report(ctx, org, key)
    practices = await _practices(ctx, org)
    source = _source(practices)
    f = Filters(**cf.model_dump())
    today = business_today()
    targets = await internal.get_targets(ctx)
    if key == "statement":
        result = await _statement(ctx, f, today, source, org.patient_detail)
    elif key == "aging":
        result = await aging_summary(ctx, f, today, targets, source=source)
    else:
        result = await recovery(ctx, f, today, targets, source=source)
    result.notes = [n for n in result.notes if "target" not in n]  # internal targets stay internal
    return org, result, today


async def _labels(ctx: Ctx, cf: ClientFilters) -> list[str]:
    return await internal.filter_labels(ctx, Filters(**cf.model_dump()))


async def _scope(ctx: Ctx, org: ClientOrganisation, cf: ClientFilters) -> list[str]:
    ids = await _practices(ctx, org)
    if cf.practice_ids:
        ids &= set(cf.practice_ids)
    names = await practice_names(ctx, ids)
    return [org.name, *sorted(names.values())]


def _period(key: str, cf: ClientFilters, today: date) -> str:
    if key == "aging":
        return f"As of {today:%d %b %Y}"
    if cf.date_from is None and cf.date_to is None:
        return "All dates"
    first = f"{cf.date_from:%d %b %Y}" if cf.date_from else "the beginning"
    last = f"{cf.date_to:%d %b %Y}" if cf.date_to else "today"
    return f"{DATE_BASIS[key]}: {first} to {last}"


async def run(ctx: Ctx, key: str, cf: ClientFilters) -> ReportRun:
    org, result, today = await _build(ctx, key, cf)
    labels = await _labels(ctx, cf)
    audit.record(
        ctx.db,
        action="client_report.viewed",
        entity_type="report",
        entity_id=f"client.{key}",
        actor_user_id=ctx.user.id,
        after={
            "client": org.name,
            "report": CLIENT_REPORTS[key],
            "filters": labels,
            "rows": len(result.rows),
        },
    )
    await ctx.db.commit()
    return ReportRun(
        key=key,
        title=CLIENT_REPORTS[key],
        period=_period(key, cf, today),
        filters_label=labels,
        scope=await _scope(ctx, org, cf),
        generated_at=datetime.now(UTC),
        columns=result.columns,
        rows=result.rows[: internal.PREVIEW_ROWS],
        row_count=len(result.rows),
        shown=min(len(result.rows), internal.PREVIEW_ROWS),
        totals=result.totals(),
        notes=result.notes,
        contains_phi=key == "statement" and org.patient_detail,
    )


async def export(ctx: Ctx, key: str, file_format: str, cf: ClientFilters) -> ExportOut:
    if not ctx.can("client_reports.download"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: client_reports.download")
    org, result, today = await _build(ctx, key, cf)
    labels = await _labels(ctx, cf)
    scope = await _scope(ctx, org, cf)
    targets = await internal.get_targets(ctx)
    phi = key == "statement" and org.patient_detail
    now = datetime.now(UTC)
    record = ReportExport(
        report_key=f"client.{key}",
        format=file_format,
        filters={
            "labels": labels,
            "values": cf.model_dump(mode="json", exclude_defaults=True),
            "client": org.name,
        },
        scope=scope,
        row_count=len(result.rows),
        file_name="",
        storage_key="",
        contains_phi=phi,
        requested_by=ctx.user.id,
        expires_at=now + timedelta(days=targets.export_retention_days),
    )
    ctx.db.add(record)
    await ctx.db.flush()
    reference = internal.export_label(record.number)
    meta = Meta(
        title=f"{CLIENT_REPORTS[key]}: {org.name}",
        period=_period(key, cf, today),
        filters=labels,
        scope=scope,
        generated_at=now,
        generated_by=ctx.user.full_name,
        reference=reference,
        contains_phi=phi,
    )
    data = (
        to_csv(result)
        if file_format == "csv"
        else to_xlsx(result, meta)
        if file_format == "xlsx"
        else to_pdf(result, meta)
    )
    stem = f"{internal._slug(org.name)}_{internal._slug(CLIENT_REPORTS[key])}"
    record.file_name = f"{stem}_{today.isoformat()}_{reference}.{file_format}"
    record.storage_key = f"exports/{record.id}/{record.file_name}"
    record.file_size = len(data)
    get_storage().save(record.storage_key, data)
    audit.record(
        ctx.db,
        action="client_report.exported",
        entity_type="report_export",
        entity_id=record.id,
        actor_user_id=ctx.user.id,
        after={
            "export": reference,
            "client": org.name,
            "report": CLIENT_REPORTS[key],
            "format": file_format.upper(),
            "filters": labels,
            "rows": len(result.rows),
            "contains_phi": phi,
        },
    )
    notify.send(
        ctx.db,
        await notify.oversight(ctx.db),
        kind="client_report.exported",
        title=f"{ctx.user.full_name} ({org.name}) exported {CLIENT_REPORTS[key]} "
        f"({file_format.upper()}, {len(result.rows)} rows)",
        link="/reports?view=exports",
        actor=ctx.user.id,
    )
    await ctx.db.commit()
    await ctx.db.refresh(record)
    return await _export_out(ctx, record)


async def _export_out(ctx: Ctx, record: ReportExport) -> ExportOut:
    [out] = await internal._out(ctx, [record])
    out.can_download = (
        ctx.can("client_reports.download")
        and record.expires_at > datetime.now(UTC)
        and bool(record.storage_key)
    )
    return out


async def list_exports(ctx: Ctx) -> list[ExportOut]:
    await _org(ctx)
    rows = list(
        await ctx.db.scalars(
            select(ReportExport)
            .where(ReportExport.requested_by == ctx.user.id)
            .order_by(ReportExport.number.desc())
            .limit(100)
        )
    )
    return [await _export_out(ctx, r) for r in rows]


async def download(ctx: Ctx, export_id: uuid.UUID) -> tuple[ReportExport, bytes]:
    org = await _org(ctx)
    record = await ctx.db.get(ReportExport, export_id)
    if record is None or record.requested_by != ctx.user.id or not record.report_key.startswith("client."):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found.")
    if not ctx.can("client_reports.download"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission required: client_reports.download")
    if record.expires_at <= datetime.now(UTC) or not record.storage_key:
        raise HTTPException(status.HTTP_410_GONE, "This export has expired. Generate the report again.")
    data = get_storage().read(record.storage_key)
    record.download_count += 1
    record.last_downloaded_at = datetime.now(UTC)
    audit.record(
        ctx.db,
        action="client_report.downloaded",
        entity_type="report_export",
        entity_id=record.id,
        actor_user_id=ctx.user.id,
        after={
            "export": internal.export_label(record.number),
            "client": org.name,
            "format": record.format.upper(),
        },
    )
    await ctx.db.commit()
    return record, data


async def org_practice_choices(ctx: Ctx) -> list[NamedRef]:
    """The organisation's practices, for a delegated client admin assigning practices to client users."""
    org = await _org(ctx)
    rows = await ctx.db.execute(
        select(Practice.id, Practice.name)
        .join(ClientOrgPractice, ClientOrgPractice.practice_id == Practice.id)
        .where(ClientOrgPractice.org_id == org.id)
        .order_by(Practice.name)
    )
    return [NamedRef(id=i, name=n) for i, n in rows]
