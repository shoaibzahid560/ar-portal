import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent


def record(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    practice_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    """
    Adds an audit event to the current transaction. It is written together with the change it
    describes: if either fails, neither is saved. Never record secrets or patient details here.
    """
    db.add(
        AuditEvent(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            actor_user_id=actor_user_id,
            practice_id=practice_id,
            before=before,
            after=after,
            request_id=request_id,
        )
    )
