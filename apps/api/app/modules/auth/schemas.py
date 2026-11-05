import uuid

from pydantic import BaseModel

from app.core.schemas import NamedRef, RoleRef


class MeUser(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    employee_code: str | None
    phone: str | None


class MeExtraRole(BaseModel):
    role: RoleRef
    practice: NamedRef | None


class MeResponse(BaseModel):
    """Everything the web app needs to draw the shell for the signed-in person."""

    user: MeUser
    role: RoleRef
    extra_roles: list[MeExtraRole] = []
    permissions: list[str]
    practices: list[NamedRef]
    teams: list[NamedRef]
