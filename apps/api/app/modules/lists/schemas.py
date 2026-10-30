from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ListKey = Literal["claim_status", "pay_status", "check_status", "action_taken"]


class OptionOut(BaseModel):
    id: int
    value: str
    active: bool


class ListsResponse(BaseModel):
    claim_status: list[OptionOut]
    pay_status: list[OptionOut]
    check_status: list[OptionOut]
    action_taken: list[OptionOut]


class OptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=80)

    @field_validator("value")
    @classmethod
    def strip(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Enter a value")
        return value


class OptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool
