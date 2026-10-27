"""Small response shapes shared by several modules."""

import uuid

from pydantic import BaseModel


class NamedRef(BaseModel):
    id: uuid.UUID
    name: str


class RoleRef(BaseModel):
    key: str
    name: str
