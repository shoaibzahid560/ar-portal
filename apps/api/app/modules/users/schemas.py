import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import NamedRef, RoleRef

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ExtraRoleOut(BaseModel):
    """An additional role. Without a practice it applies in all of the person's practices."""

    role: RoleRef
    practice: NamedRef | None


class GrantRef(BaseModel):
    """An active additional permission, for display."""

    permission: str
    practice: NamedRef | None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    employee_code: str | None
    phone: str | None
    status: str
    role: RoleRef
    extra_roles: list[ExtraRoleOut] = []
    grants: list[GrantRef] = []
    practices: list[NamedRef]
    teams: list[NamedRef]
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    full_name: str = Field(min_length=1, max_length=120)
    employee_code: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    role_key: str
    practice_ids: list[uuid.UUID] = []
    team_ids: list[uuid.UUID] = []

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL.match(value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name is required")
        return value

    @field_validator("employee_code", "phone")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class UserUpdate(BaseModel):
    """Only the fields that are sent are changed. Status here is active or paused; see /deactivate."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    employee_code: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    role_key: str | None = None
    status: Literal["active", "paused"] | None = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be empty")
        return value

    @field_validator("employee_code", "phone")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class IdList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID]


class RoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_key: str
    practice_id: uuid.UUID | None = None


class RoleAssignments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: list[RoleAssignment] = Field(max_length=20)
