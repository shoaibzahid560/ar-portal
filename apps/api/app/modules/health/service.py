from sqlalchemy import text

from app.core.db import get_engine
from app.modules.health.schemas import DatabaseStatus


async def check_database() -> DatabaseStatus:
    """Runs `select 1`. A health check reports problems; it never raises."""
    engine = get_engine()
    if engine is None:
        return "not_configured"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        return "unavailable"
    return "ok"
