import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import NamedRef

Money = Annotated[Decimal, Field(ge=0, le=Decimal("9999999.99"), max_digits=12, decimal_places=2)]

ClaimView = Literal["all", "mine", "unassigned", "due-today", "tomorrow", "overdue", "needs-review", "merged"]


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
