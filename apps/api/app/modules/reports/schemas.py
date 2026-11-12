import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import NamedRef

ColumnKind = Literal["text", "date", "datetime", "money", "int", "percent"]
ExportFormat = Literal["csv", "xlsx", "pdf"]


class Filters(BaseModel):
    """
    Report filters. Every one narrows the person's own scope; none widens it: practice IDs outside their
    scope simply match nothing, because the server applies the scope first.
    """

    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    practice_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    payer: str | None = Field(default=None, max_length=120)
    claim_statuses: list[str] = Field(default_factory=list, max_length=40)
    work_states: list[Literal["open", "pending_completion", "closed"]] = Field(default_factory=list)
    assigned_user_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    upload_id: uuid.UUID | None = None
    aging_buckets: list[str] = Field(default_factory=list, max_length=10)
    priorities: list[Literal["low", "normal", "high", "urgent"]] = Field(default_factory=list)


class Column(BaseModel):
    key: str
    label: str
    kind: ColumnKind = "text"


class ReportRun(BaseModel):
    """A report shown on screen: the first rows, with totals over every row."""

    key: str
    title: str
    period: str
    filters_label: list[str]
    scope: list[str]
    generated_at: datetime
    columns: list[Column]
    rows: list[dict[str, Any]]
    row_count: int
    shown: int
    totals: dict[str, Any]
    notes: list[str]
    contains_phi: bool


class CatalogueItem(BaseModel):
    key: str
    title: str
    description: str
    date_basis: str
    filters: list[str]
    contains_phi: bool
    staff: bool


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ExportFormat
    filters: Filters = Field(default_factory=Filters)


class ExportOut(BaseModel):
    id: uuid.UUID
    number: str
    report_key: str
    report_title: str
    format: ExportFormat
    file_name: str
    file_size: int
    row_count: int
    filters_label: list[str]
    scope: list[str]
    contains_phi: bool
    requested_by: NamedRef
    created_at: datetime
    expires_at: datetime
    expired: bool
    download_count: int
    last_downloaded_at: datetime | None
    can_download: bool


class Targets(BaseModel):
    """Report targets and alert thresholds (management decision #7). Editable in Settings."""

    model_config = ConfigDict(extra="forbid")

    claims_worked_per_day: int = Field(ge=1, le=500)
    first_pass_quality_pct: int = Field(ge=1, le=100)
    overdue_followups_per_person: int = Field(ge=0, le=1000)
    aging_over_90_pct: int = Field(ge=0, le=100)
    export_retention_days: int = Field(ge=1, le=90)


class Bar(BaseModel):
    label: str
    count: int
    amount: Decimal = Decimal(0)
    secondary: int = 0  # e.g. overdue follow-ups, for a person's workload


class Alert(BaseModel):
    tone: Literal["warn", "danger", "info"]
    text: str
    link: str | None = None


class Overview(BaseModel):
    """The AR performance dashboard (brief section 6), within the person's scope."""

    open_claims: int
    open_billed: Decimal
    open_unrecovered: Decimal
    recovered_total: Decimal
    recovered_this_month: Decimal
    due_today: int
    overdue: int
    awaiting_completion: int
    closed_this_month: int
    over_90_pct: float
    aging: list[Bar]
    by_status: list[Bar]
    by_practice: list[Bar]
    recovered_by_month: list[Bar]
    workload: list[Bar] | None
    alerts: list[Alert]
    targets: Targets
