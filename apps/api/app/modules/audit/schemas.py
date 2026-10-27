import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Actor(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class AuditEventOut(BaseModel):
    id: int
    occurred_at: datetime
    actor: Actor | None
    action: str
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class AuditPage(BaseModel):
    events: list[AuditEventOut]
    next_before_id: int | None
