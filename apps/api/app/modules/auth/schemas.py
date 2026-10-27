import uuid

from pydantic import BaseModel

from app.core.schemas import NamedRef, RoleRef


class MeUser(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    employee_code: str | None
    phone: str | None


class MeResponse(BaseModel):
    """Everything the web app needs to draw the shell for the signed-in person."""

    user: MeUser
    role: RoleRef
    permissions: list[str]
    practices: list[NamedRef]
    teams: list[NamedRef]
