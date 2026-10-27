"""
Database tests. They run only when TEST_DATABASE_URL points at a throwaway database,
because they drop and recreate every table. Never point it at a database with real data.
"""

import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings

RAW_URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not RAW_URL, reason="Set TEST_DATABASE_URL to run database tests")

EXPECTED_TABLES = {
    "alembic_version",
    "audit_events",
    "permissions",
    "practices",
    "role_permissions",
    "roles",
    "sessions",
    "team_members",
    "teams",
    "user_practices",
    "users",
}


def _url() -> str:
    url = Settings(database_url=RAW_URL).database_url
    assert url
    return url


def _alembic() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = _url()
    return config


def _run(sql: str, *, commit: bool = False) -> list[tuple]:
    async def go() -> list[tuple]:
        engine = create_async_engine(_url(), poolclass=NullPool, connect_args={"statement_cache_size": 0})
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


@pytest.fixture(scope="module", autouse=True)
def fresh_schema() -> None:
    config = _alembic()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_all_tables_live_in_the_ar_schema() -> None:
    rows = _run("SELECT table_name FROM information_schema.tables WHERE table_schema = 'ar'")
    assert {name for (name,) in rows} == EXPECTED_TABLES


def test_six_roles_are_seeded() -> None:
    rows = _run("SELECT key FROM ar.roles")
    assert {key for (key,) in rows} == {
        "system_admin",
        "management",
        "ar_manager",
        "ar_lead",
        "ar_associate",
        "auditor",
    }


def test_system_admin_has_every_permission_and_associates_cannot_manage_users() -> None:
    [(total,)] = _run("SELECT count(*) FROM ar.permissions")
    [(admin,)] = _run(
        "SELECT count(*) FROM ar.role_permissions rp JOIN ar.roles r ON r.id = rp.role_id "
        "WHERE r.key = 'system_admin'"
    )
    associate = _run(
        "SELECT rp.permission_key FROM ar.role_permissions rp JOIN ar.roles r ON r.id = rp.role_id "
        "WHERE r.key = 'ar_associate'"
    )
    assert admin == total
    assert {key for (key,) in associate} == {"dashboard.view"}


def test_audit_events_are_append_only() -> None:
    _run(
        "INSERT INTO ar.audit_events (action, entity_type, entity_id) VALUES ('test.inserted', 'test', '1')",
        commit=True,
    )
    for statement in (
        "UPDATE ar.audit_events SET action = 'changed'",
        "DELETE FROM ar.audit_events",
        "TRUNCATE ar.audit_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            _run(statement, commit=True)
    [(count,)] = _run("SELECT count(*) FROM ar.audit_events WHERE action = 'test.inserted'")
    assert count == 1


def test_row_level_security_is_on_for_every_table() -> None:
    rows = _run(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'ar' AND c.relkind = 'r' AND NOT c.relrowsecurity"
    )
    assert {name for (name,) in rows} <= {"alembic_version"}


def test_emails_must_be_lowercase() -> None:
    with pytest.raises(DBAPIError, match="ck_users_email_lowercase"):
        _run(
            "INSERT INTO ar.users (email, full_name, role_id) "
            "SELECT 'Someone@Example.com', 'Someone', id FROM ar.roles WHERE key = 'ar_associate'"
        )


def test_models_match_the_migrations() -> None:
    command.check(_alembic())
