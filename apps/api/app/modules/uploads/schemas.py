import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import NamedRef


def upload_label(number: int) -> str:
    return f"UPL-{number:06d}"


class UploadOut(BaseModel):
    id: uuid.UUID
    number: str
    practice: NamedRef
    uploaded_by: NamedRef
    file_name: str
    file_size: int
    status: str
    failure_reason: str | None
    mapping_warning: str | None
    total_rows: int
    # Preview: what the file contains, before anything is created
    new_rows: int
    duplicate_rows: int
    changed_rows: int
    repeat_rows: int
    error_rows: int
    undecided_rows: int
    # Outcome: what committing did
    created_claims: int
    updated_claims: int
    skipped_rows: int
    review_rows: int  # uploads from before import approval flagged lines for the Review queue instead
    created_at: datetime
    completed_at: datetime | None
    submitted_by: NamedRef | None
    submitted_at: datetime | None
    decided_by: NamedRef | None
    decided_at: datetime | None
    decision_reason: str | None
    reversed_by: NamedRef | None
    reversed_at: datetime | None
    reverse_reason: str | None


class RowErrorOut(BaseModel):
    row_number: int
    column: str
    message: str


class UploadActions(BaseModel):
    """What the signed-in person may do with this upload right now, and why not, if they can't."""

    can_submit: bool
    can_discard: bool
    can_decide: bool
    can_commit: bool
    can_reject: bool
    can_reverse: bool
    commit_blocked_because: str | None


class UploadDetail(UploadOut):
    errors: list[RowErrorOut]
    actions: UploadActions


class Candidate(BaseModel):
    """An existing claim an uploaded line matches, with its uploaded values for comparison."""

    id: uuid.UUID
    number: str
    values: dict[str, Any]
    claim_status: str | None
    assigned_to: str | None


class UploadRowOut(BaseModel):
    id: int
    row_number: int
    classification: Literal["new", "duplicate", "changed", "repeat"]
    values: dict[str, Any] | None
    candidates: list[Candidate]
    decision: Literal["create", "update", "skip"] | None
    target_claim_id: uuid.UUID | None
    decided_by: str | None
    result_claim: NamedRef | None


class RowDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["create", "update", "skip"]
    target_claim_id: uuid.UUID | None = None


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)
