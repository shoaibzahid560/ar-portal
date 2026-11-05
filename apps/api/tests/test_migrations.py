"""Checks that migration 0001 builds the schema, seed data and protections correctly."""

import pytest
from alembic import command
from sqlalchemy.exc import DBAPIError

from tests.db import alembic_config, migrate_fresh, requires_database
from tests.db import run_sql as _run

pytestmark = requires_database

EXPECTED_TABLES = {
    "alembic_version",
    "audit_events",
    "claim_notes",
    "claim_prints",
    "claims",
    "notifications",
    "option_list_items",
    "permission_grants",
    "permissions",
    "practices",
    "role_permissions",
    "roles",
    "sessions",
    "team_members",
    "teams",
    "user_roles",
    "upload_errors",
    "upload_rows",
    "uploads",
    "user_practices",
    "users",
}


@pytest.fixture(scope="module", autouse=True)
def fresh_schema() -> None:
    migrate_fresh()


def test_all_tables_live_in_the_ar_schema() -> None:
    rows = _run("SELECT table_name FROM information_schema.tables WHERE table_schema = 'ar'")
    assert {name for (name,) in rows} == EXPECTED_TABLES


def test_the_specifications_roles_are_seeded() -> None:
    rows = _run("SELECT key, name FROM ar.roles")
    assert dict(rows) == {
        "system_admin": "Portal Owner / Super Admin",
        "org_admin": "Organization Admin",
        "ar_manager": "Operations Manager",
        "auditor": "Reporting Analyst / Auditor",
        "ar_lead": "Practice Manager / AR Lead",
        "team_lead": "AR Team Lead",
        "claim_importer": "Claim Importer",
        "ar_associate": "AR Associate",
        "management": "Management (company-wide view)",
    }


def test_default_access_follows_the_specification() -> None:
    def permissions(role: str) -> set[str]:
        rows = _run(
            "SELECT rp.permission_key FROM ar.role_permissions rp JOIN ar.roles r ON r.id = rp.role_id "
            f"WHERE r.key = '{role}'"
        )
        return {key for (key,) in rows}

    every = {key for (key,) in _run("SELECT key FROM ar.permissions")}
    assert permissions("system_admin") == every - {"claims.receive"}  # the owner isn't assigned claims
    assert permissions("ar_associate") == {
        "dashboard.view",
        "claims.view",
        "claims.work",
        "claims.assign",
        "claims.receive",
    }
    assert permissions("claim_importer") == {
        "dashboard.view",
        "practices.view",
        "uploads.view",
        "uploads.create",
    }
    assert "uploads.create" not in permissions("ar_lead")  # uploading belongs to Claim Importer
    assert {"claims.view_team", "claims.assign", "claims.receive"} <= permissions("team_lead")
    assert "roles.manage" not in permissions("org_admin") and "users.manage_owners" not in permissions(
        "org_admin"
    )
    assert not {"claims.work", "claims.assign"} & permissions("auditor")


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
    command.check(alembic_config())


def test_dropdowns_are_seeded_exactly_as_in_the_ar_sheet() -> None:
    rows = _run("SELECT list_key, value FROM ar.option_list_items ORDER BY list_key, sort_order")
    lists: dict[str, list[str]] = {}
    for key, value in rows:
        lists.setdefault(key, []).append(value)

    assert lists["pay_status"] == ["Paid to Patient", "Paid to Practice"]
    assert lists["check_status"] == [
        "Check Deposited",
        "Not issued yet",
        "Reissued Check",
        "Check Not Cashed",
    ]
    assert (
        lists["claim_status"][0] == "Approved to pay" and lists["claim_status"][-1] == "Paid Under Capitation"
    )
    assert len(lists["claim_status"]) == 13 and len(lists["action_taken"]) == 10
    assert lists["action_taken"][-1] == "Writed-off"
