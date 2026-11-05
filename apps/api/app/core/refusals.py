"""
Refused actions are recorded (specification, section 8: capture the outcome). The refused request's own
transaction is rolled back, so the record is written in a separate, short transaction.
"""

import logging

from fastapi import Request

from app.core import audit
from app.core.db import get_db

log = logging.getLogger(__name__)


async def record_refusal(request: Request, detail: str) -> None:
    actor = getattr(request.state, "user_id", None)
    if actor is None:
        return  # not signed in: that's a 401, handled by the sign-in flow
    provider = request.app.dependency_overrides.get(get_db, get_db)
    sessions = provider()
    try:
        db = await sessions.__anext__()
        audit.record(
            db,
            action="access.refused",
            entity_type="request",
            entity_id=f"{request.method} {request.url.path}"[:200],
            actor_user_id=actor,
            after={"reason": detail[:300]},
        )
        await db.commit()
    except Exception:  # noqa: BLE001 - recording a refusal must never turn it into a server error
        log.exception("Could not record a refused request")
    finally:
        await sessions.aclose()
