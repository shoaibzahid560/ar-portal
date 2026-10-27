"""Runs migrations against DATABASE_URL, using the same async driver as the API."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.orm import SCHEMA
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    # Tests pass their own database; everything else uses DATABASE_URL from .env.
    url = config.attributes.get("database_url") or get_settings().database_url
    if not url:
        raise SystemExit("DATABASE_URL is not set. Add it to apps/api/.env (see .env.example).")
    return url


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Only look at the `ar` schema; Supabase's own schemas are none of our business."""
    if type_ == "schema":
        return name == SCHEMA
    return True


def configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(
        database_url(),
        poolclass=pool.NullPool,
        connect_args={"statement_cache_size": 0},
    )
    async with engine.connect() as connection:
        # The version table lives in the `ar` schema, so the schema must exist first.
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        await connection.commit()
        await connection.run_sync(configure)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) mode is not used in this project.")
asyncio.run(run_migrations_online())
