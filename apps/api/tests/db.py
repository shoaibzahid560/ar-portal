"""
Helpers for database tests. They run only when TEST_DATABASE_URL points at a throwaway database,
because they drop and recreate every table. Never point it at a database with real data.
"""

import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings

RAW_URL = os.environ.get("TEST_DATABASE_URL", "")
requires_database = pytest.mark.skipif(not RAW_URL, reason="Set TEST_DATABASE_URL to run database tests")


def url() -> str:
    normalized = Settings(database_url=RAW_URL).database_url
    assert normalized
    return normalized


def alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = url()
    return config


def migrate_fresh() -> None:
    config = alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(url(), poolclass=NullPool, connect_args={"statement_cache_size": 0})
    return async_sessionmaker(engine, expire_on_commit=False)


def run_sql(sql: str, *, commit: bool = False) -> list[tuple]:
    async def go() -> list[tuple]:
        engine = create_async_engine(url(), poolclass=NullPool, connect_args={"statement_cache_size": 0})
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text(sql))
                rows = [tuple(row) for row in result] if result.returns_rows else []
                if commit:
                    await connection.commit()
                return rows
        finally:
            await engine.dispose()

    return asyncio.run(go())
