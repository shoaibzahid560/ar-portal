from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine | None:
    """One engine per process. Returns None when no database is configured."""
    settings = get_settings()
    if not settings.database_url:
        return None
    return create_async_engine(
        settings.database_url,
        # Vercel runs many short-lived function instances, so connections are not pooled here;
        # Supabase's transaction pooler does the pooling.
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,  # required by the transaction pooler
            "timeout": 5,  # seconds to wait for a connection before giving up
        },
    )
