from sqlalchemy import text

from app.core.db import get_engine
from app.core.schema_version import SCHEMA_VERSION
from app.modules.health.schemas import DatabaseStatus


async def check_database() -> tuple[DatabaseStatus, str | None]:
    """Connects, and compares the database's migration version with the one this code expects.
    A health check reports problems; it never raises."""
    try:
        engine = get_engine()
        if engine is None:
            return "not_configured", None
        async with engine.connect() as connection:
            version = (await connection.execute(text("SELECT version_num FROM ar.alembic_version"))).scalar()
    except Exception:  # noqa: BLE001
        return "unavailable", None
    return ("ok" if version == SCHEMA_VERSION else "needs_update"), version
