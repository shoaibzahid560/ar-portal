import logging

from sqlalchemy import text

from app.core.db import get_engine
from app.core.schema_version import SCHEMA_VERSION
from app.modules.health.schemas import DatabaseStatus

logger = logging.getLogger(__name__)


async def check_database() -> tuple[DatabaseStatus, str | None]:
    """Connects, and compares the database's migration version with the one this code expects.
    A health check reports problems; it never raises. The reason for a failure goes to the server log
    (Vercel: Logs), never to the public response."""
    try:
        engine = get_engine()
        if engine is None:
            return "not_configured", None
        async with engine.connect() as connection:
            version = (await connection.execute(text("SELECT version_num FROM ar.alembic_version"))).scalar()
    except Exception as error:  # noqa: BLE001
        logger.warning("Database check failed: %s: %s", type(error).__name__, str(error).splitlines()[0])
        return "unavailable", None
    return ("ok" if version == SCHEMA_VERSION else "needs_update"), version
