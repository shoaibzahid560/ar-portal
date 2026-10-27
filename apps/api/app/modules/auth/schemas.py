import uuid

from pydantic import BaseModel


class MeUser(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    employee_code: str | None
    phone: str | None


class MeRole(BaseModel):
    key: str
    name: str


class NamedRef(BaseModel):
    id: uuid.UUID
    name: str


class MeResponse(BaseModel):
    """Everything the web app needs to draw the shell for the signed-in person."""

    user: MeUser
    role: MeRole
    permissions: list[str]
    practices: list[NamedRef]
    teams: list[NamedRef]
