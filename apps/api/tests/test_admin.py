"""Users, practices, teams, the role matrix and the audit log, against a real database."""

from collections.abc import Iterator

import pytest

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import migrate_fresh, requires_database, run_sql

pytestmark = requires_database

ADMIN = "admin@example.com"
MANAGEMENT = "management@example.com"
MANAGER = "manager@example.com"
AUDITOR = "auditor@example.com"
ASSOC_A = "assoc.a@example.com"
ASSOC_B = "assoc.b@example.com"


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def user_id(email: str) -> str:
    return str(one(f"SELECT id FROM ar.users WHERE email = '{email}'"))


def practice_id(name: str) -> str:
    return str(one(f"SELECT id FROM ar.practices WHERE name = '{name}'"))


def audit_count(action: str) -> int:
    return int(one(f"SELECT count(*) FROM ar.audit_events WHERE action = '{action}'"))


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    """Two practices. The manager and associate A work in Practice A; associate B in Practice B."""
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{ADMIN}', 'Admin', 'system_admin'),
                     ('{MANAGEMENT}', 'Management', 'management'),
                     ('{MANAGER}', 'Manager', 'ar_manager'),
                     ('{AUDITOR}', 'Auditor', 'auditor'),
                     ('{ASSOC_A}', 'Associate A', 'ar_associate'),
                     ('{ASSOC_B}', 'Associate B', 'ar_associate'))
             AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Practice A'), ('Practice B')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p
        WHERE (u.email IN ('{MANAGER}', '{ASSOC_A}') AND p.name = 'Practice A')
           OR (u.email = '{ASSOC_B}' AND p.name = 'Practice B')
        """,
        """
        INSERT INTO ar.teams (name, practice_id)
        SELECT 'Team ' || right(name, 1), id FROM ar.practices WHERE name IN ('Practice A', 'Practice B')
        """,
    ):
        run_sql(statement, commit=True)
    with app_uses_test_database():
        yield


def set_role_permissions(monkeypatch: pytest.MonkeyPatch, role: str, permissions: list[str]) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    response = admin.put(f"/api/roles/{role}/permissions", json={"permissions": permissions})
    assert response.status_code == 200, response.text


# ---- Users -------------------------------------------------------------------------------------


def test_admin_creates_a_user_and_one_audit_event_is_written(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    before = audit_count("user.created")

    response = admin.post(
        "/api/users",
        json={
            "email": "  New.Person@Example.com ",
            "full_name": "New Person",
            "role_key": "ar_associate",
            "practice_ids": [practice_id("Practice A")],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new.person@example.com"
    assert body["role"]["key"] == "ar_associate"
    assert [p["name"] for p in body["practices"]] == ["Practice A"]
    assert audit_count("user.created") == before + 1


def test_duplicate_email_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)

    response = admin.post(
        "/api/users", json={"email": ASSOC_A, "full_name": "Dup", "role_key": "ar_associate"}
    )

    assert response.status_code == 409


def test_associate_cannot_reach_user_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    associate = browser_for(monkeypatch, ASSOC_A)

    assert associate.get("/api/users").status_code == 403
    assert associate.post("/api/users", json={}).status_code == 403
    assert associate.get("/api/audit-events").status_code == 403


def test_manager_sees_only_people_in_their_practices_and_teams(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = browser_for(monkeypatch, MANAGER)

    emails = {u["email"] for u in manager.get("/api/users").json()}

    assert ASSOC_A in emails and MANAGER in emails
    assert ASSOC_B not in emails and ADMIN not in emails
    assert manager.get(f"/api/users/{user_id(ASSOC_B)}").status_code == 404


def test_manager_cannot_assign_outside_their_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    set_role_permissions(
        monkeypatch, "ar_manager", ["dashboard.view", "users.view", "users.manage", "practices.view"]
    )
    try:
        manager = browser_for(monkeypatch, MANAGER)
        target = user_id(ASSOC_A)

        outside = manager.put(f"/api/users/{target}/practices", json={"ids": [practice_id("Practice B")]})
        inside = manager.put(f"/api/users/{target}/practices", json={"ids": [practice_id("Practice A")]})

        assert outside.status_code == 403
        assert inside.status_code == 200
    finally:
        set_role_permissions(monkeypatch, "ar_manager", ["dashboard.view", "users.view", "practices.view"])


def test_deactivation_signs_the_person_out_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    created = admin.post(
        "/api/users", json={"email": "leaver@example.com", "full_name": "Leaver", "role_key": "ar_associate"}
    ).json()
    leaver = browser_for(monkeypatch, "leaver@example.com")
    assert leaver.get("/api/auth/me").status_code == 200

    response = admin.post(f"/api/users/{created['id']}/deactivate")

    assert response.json()["status"] == "deactivated"
    assert leaver.get("/api/auth/me").status_code == 401
    assert admin.patch(f"/api/users/{created['id']}", json={"status": "active"}).status_code == 400


def test_admins_cannot_lock_themselves_out(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    me = user_id(ADMIN)

    assert admin.post(f"/api/users/{me}/deactivate").status_code == 400
    assert admin.patch(f"/api/users/{me}", json={"role_key": "ar_associate"}).status_code == 400
    assert admin.patch(f"/api/users/{me}", json={"full_name": "Admin Renamed"}).status_code == 200


def test_last_system_administrator_cannot_be_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    set_role_permissions(monkeypatch, "management", ["dashboard.view", "users.view", "users.manage"])
    try:
        management = browser_for(monkeypatch, MANAGEMENT)
        response = management.post(f"/api/users/{user_id(ADMIN)}/deactivate")
        assert response.status_code == 400
        assert "last active System Administrator" in response.json()["detail"]
    finally:
        set_role_permissions(
            monkeypatch, "management", ["dashboard.view", "users.view", "practices.view", "audit.view"]
        )


# ---- Roles ---------------------------------------------------------------------------------------


def test_role_change_takes_effect_on_the_next_request(monkeypatch: pytest.MonkeyPatch) -> None:
    associate = browser_for(monkeypatch, ASSOC_A)
    assert associate.get("/api/users").status_code == 403

    set_role_permissions(monkeypatch, "ar_associate", ["dashboard.view", "users.view"])
    try:
        assert associate.get("/api/users").status_code == 200
    finally:
        set_role_permissions(monkeypatch, "ar_associate", ["dashboard.view"])
    assert audit_count("role.permissions_changed") >= 2


def test_system_administrator_keeps_the_permissions_that_prevent_lockout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = browser_for(monkeypatch, ADMIN)

    removed = admin.put("/api/roles/system_admin/permissions", json={"permissions": ["dashboard.view"]})
    unknown = admin.put("/api/roles/ar_lead/permissions", json={"permissions": ["claims.delete_everything"]})

    assert removed.status_code == 400
    assert unknown.status_code == 400


# ---- Practices and teams ---------------------------------------------------------------------------


def test_practices_are_created_audited_and_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    created = admin.post("/api/practices", json={"name": "Practice C"})
    assert created.status_code == 201
    assert admin.post("/api/practices", json={"name": "practice c"}).status_code == 409

    paused = admin.patch(f"/api/practices/{created.json()['id']}", json={"status": "paused"})
    assert paused.json()["status"] == "paused"
    assert audit_count("practice.created") == 1 and audit_count("practice.updated") == 1

    manager = browser_for(monkeypatch, MANAGER)
    assert [p["name"] for p in manager.get("/api/practices").json()] == ["Practice A"]
    assert {t["name"] for t in manager.get("/api/teams").json()} == {"Team A"}


def test_teams_need_an_active_manager_and_a_unique_name(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    practice = practice_id("Practice B")

    ok = admin.post(
        "/api/teams",
        json={"name": "Night shift", "practice_id": practice, "manager_user_id": user_id(MANAGER)},
    )
    duplicate = admin.post("/api/teams", json={"name": "night shift", "practice_id": practice})
    bad_manager = admin.post(
        "/api/teams", json={"name": "Other", "manager_user_id": user_id("leaver@example.com")}
    )

    assert ok.status_code == 201 and ok.json()["manager_name"] == "Manager"
    assert duplicate.status_code == 409
    assert bad_manager.status_code == 400


# ---- Audit log -------------------------------------------------------------------------------------


def test_audit_log_filters_and_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)

    user_events = admin.get("/api/audit-events", params={"action": "user."}).json()["events"]
    first_page = admin.get("/api/audit-events", params={"limit": 2}).json()
    second_page = admin.get(
        "/api/audit-events", params={"limit": 2, "before_id": first_page["next_before_id"]}
    ).json()

    assert user_events and all(e["action"].startswith("user.") for e in user_events)
    assert len(first_page["events"]) == 2 and first_page["next_before_id"] is not None
    assert second_page["events"][0]["id"] < first_page["events"][-1]["id"]
    assert user_events[0]["actor"]["email"]


def test_auditor_can_read_the_audit_log(monkeypatch: pytest.MonkeyPatch) -> None:
    assert browser_for(monkeypatch, AUDITOR).get("/api/audit-events").status_code == 200
