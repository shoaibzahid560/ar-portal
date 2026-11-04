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
    # Names for the people referred to in before/after (e.g. who a claim was assigned to), so every
    # role reading a history sees names, not IDs.
    people: dict[str, str] = {}
    # What the record is, in words, and where it lives in the portal (e.g. "CLM-000123", "/claims/...").
    label: str | None = None
    link: str | None = None
    # For "Note added": the note itself, shown only to people who may see that claim.
    note: str | None = None
    # Plain-language lines for changes that are hard to read raw (e.g. which permissions were added).
    summary: list[str] | None = None


class AuditPage(BaseModel):
    events: list[AuditEventOut]
    next_before_id: int | None
