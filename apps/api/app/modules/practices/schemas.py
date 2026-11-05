import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Name is required")
    return value


class PracticeOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    notes: str
    import_code: str | None = None
    user_count: int
    team_count: int
    created_at: datetime


class PracticeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=2000)
    import_code: str | None = Field(default=None, max_length=60)

    _name = field_validator("name")(_strip_required)


class PracticeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["active", "paused"] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    import_code: str | None = Field(default=None, max_length=60)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return None if value is None else _strip_required(value)


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    practice_id: uuid.UUID | None
    practice_name: str | None
    manager_user_id: uuid.UUID | None
    manager_name: str | None
    member_count: int
    created_at: datetime


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    practice_id: uuid.UUID | None = None
    manager_user_id: uuid.UUID | None = None

    _name = field_validator("name")(_strip_required)


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    practice_id: uuid.UUID | None = None
    manager_user_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return None if value is None else _strip_required(value)
