import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import NamedRef

GrantState = Literal["pending", "active", "expired", "rejected", "revoked"]


class GrantOut(BaseModel):
    id: int
    person: NamedRef
    permission: str
    permission_description: str
    elevated: bool
    practice: NamedRef | None
    reason: str
    state: GrantState
    requested_by: NamedRef
    approved_by: NamedRef | None
    created_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None
    review_due_at: datetime | None
    review_overdue: bool
    ended_at: datetime | None
    ended_by: NamedRef | None
    end_reason: str | None
    can_approve: bool


class GrantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    permission: str = Field(max_length=60)
    practice_id: uuid.UUID | None = None
    reason: str = Field(min_length=5, max_length=500)
    expires_on: date | None = None

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Give a reason of at least a few words")
        return value


class GrantDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class GrantablePermission(BaseModel):
    key: str
    module: str
    description: str
    elevated: bool
