from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
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
        # Supabase's pooler does the pooling.
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,  # required by Supabase's transaction pooler
            "timeout": 5,  # seconds to wait for a connection before giving up
        },
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession] | None:
    engine = get_engine()
    if engine is None:
        return None
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one database session per request."""
    sessionmaker = get_sessionmaker()
    if sessionmaker is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is not configured.")
    async with sessionmaker() as session:
        yield session
