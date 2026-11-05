import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import NamedRef

Money = Annotated[Decimal, Field(ge=0, le=Decimal("9999999.99"), max_digits=12, decimal_places=2)]

ClaimView = Literal[
    "all",
    "mine",
    "unassigned",
    "due-today",
    "tomorrow",
    "overdue",
    "needs-review",
    "merged",
    "awaiting-completion",
    "returned",
    "high-priority",
    "closed",
]
WorkState = Literal["open", "pending_completion", "closed"]
Priority = Literal["low", "normal", "high", "urgent"]


def claim_label(number: int) -> str:
    return f"CLM-{number:06d}"


class PersonRef(BaseModel):
    id: uuid.UUID
    name: str
    role: str | None = None


class ClaimRef(BaseModel):
    id: uuid.UUID
    number: str


class ClaimListItem(BaseModel):
    id: uuid.UUID
    number: str
    practice: NamedRef
    patient_name: str
    service_date: date
    subscriber_id: str
    insurance_carrier: str
    billed: Decimal
    claim_status: str | None
    action_taken: str | None
    followup_date: date | None
    assigned_to: PersonRef | None
    aging_days: int
    aging_bucket: str
    needs_review: bool
    merged_into: ClaimRef | None = None
    work_state: WorkState = "open"
    priority: Priority = "normal"
    returned: bool = False


class ClaimPage(BaseModel):
    claims: list[ClaimListItem]
    total: int


class NoteOut(BaseModel):
    id: int
    body: str
    created_at: datetime
    author: PersonRef


class EobOut(BaseModel):
    file_name: str
    uploaded_at: datetime


class UploadRef(BaseModel):
    id: uuid.UUID
    number: str


class ClaimDetail(ClaimListItem):
    upload: UploadRef
    patient_dob: date | None
    subscriber_name: str | None
    subscriber_dob: date | None
    allowed_amount: Decimal | None
    recovered_amount: Decimal | None
    patient_responsibility: Decimal | None
    pay_status: str | None
    check_status: str | None
    cashed_date: date | None
    payment_posted_date: date | None
    eob: EobOut | None
    review_reason: str | None
    notes: list[NoteOut]
    can_work: bool
    can_assign: bool
    can_review: bool
    withdrawn: bool = False
    # The latest lifecycle step (who, when, why). Every step is also in the claim's history.
    state_reason: str | None = None
    state_changed_by: PersonRef | None = None
    state_changed_at: datetime | None = None
    completion_requested_by: PersonRef | None = None
    can_note: bool = False
    can_request_completion: bool = False
    can_review_completion: bool = False
    can_close: bool = False
    can_reopen: bool = False
    can_prioritize: bool = False
    created_at: datetime
    updated_at: datetime


class ClaimUpdate(BaseModel):
    """The AR sheet's work columns. Only fields that are sent change; send null to clear one."""

    model_config = ConfigDict(extra="forbid")

    claim_status: str | None = None
    pay_status: str | None = None
    check_status: str | None = None
    action_taken: str | None = None
    allowed_amount: Money | None = None
    recovered_amount: Money | None = None
    patient_responsibility: Money | None = None
    cashed_date: date | None = None
    payment_posted_date: date | None = None
    followup_date: date | None = None
    assigned_user_id: uuid.UUID | None = None
    needs_review: Literal[False] | None = None
    priority: Priority | None = None


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write a note first")
        return value


class Assignee(BaseModel):
    id: uuid.UUID
    name: str
    role: str


class StatusCount(BaseModel):
    status: str
    count: int
    billed: Decimal


class ClaimSummary(BaseModel):
    total: int
    unassigned: int
    due_today: int
    overdue: int
    needs_review: int
    billed_total: Decimal
    awaiting_completion: int = 0
    returned: int = 0
    closed: int = 0
    by_status: list[StatusCount]


class BulkAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    assigned_user_id: uuid.UUID | None


class BulkResult(BaseModel):
    updated: int


class Resolve(BaseModel):
    """A reviewer's decision on a line that needs review."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["same", "separate"]
    target_id: uuid.UUID | None = None


class LifecycleNote(BaseModel):
    """A reason or note for a lifecycle step. Required for return, close and reopen."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)


class ContinueFollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)
    followup_date: date


class BulkPriority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    priority: Priority
