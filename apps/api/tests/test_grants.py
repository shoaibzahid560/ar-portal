"""Additional grants (specification, section 4) and refused-action logging, against a real database."""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import migrate_fresh, requires_database, run_sql

pytestmark = requires_database

ADMIN, ADMIN_2, OWNER = "orgadmin@example.com", "orgadmin2@example.com", "owner@example.com"
WORKER = "worker@example.com"
SHEET = (
    b"Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\n"
    b"Test A,10-01-26,1,Aetna,50\nTest B,someday,2,Aetna,60\n"
)


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def uid(email: str) -> str:
    return str(one(f"SELECT id FROM ar.users WHERE email = '{email}'"))


def pid(name: str) -> str:
    return str(one(f"SELECT id FROM ar.practices WHERE name = '{name}'"))


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{OWNER}', 'Owner', 'system_admin'),
                     ('{ADMIN}', 'Org Admin', 'org_admin'),
                     ('{ADMIN_2}', 'Second Admin', 'org_admin'),
                     ('{WORKER}', 'Worker', 'ar_associate')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Practice A'), ('Practice B')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p WHERE u.email = '{WORKER}' AND p.name = 'Practice A'
        """,
    ):
        run_sql(statement, commit=True)
    with app_uses_test_database():
        yield


def upload(browser: TestClient, practice: str) -> int:
    return browser.post(
        "/api/uploads", data={"practice_id": pid(practice)}, files={"file": (f"{practice}.csv", SHEET)}
    ).status_code


def grant(browser: TestClient, permission: str, practice: str | None = None, **extra: object) -> object:
    body = {
        "user_id": uid(WORKER),
        "permission": permission,
        "practice_id": pid(practice) if practice else None,
        "reason": "Covering uploads while the importer is on leave",
        **extra,
    }
    return browser.post("/api/grants", json=body)


def test_a_standard_grant_works_at_once_in_its_practice_only(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, worker = browser_for(monkeypatch, ADMIN), browser_for(monkeypatch, WORKER)
    assert upload(worker, "Practice A") == 403

    given = grant(admin, "uploads.create", "Practice A")

    assert given.status_code == 201 and given.json()["state"] == "active"
    assert given.json()["approved_by"]["name"] == "Org Admin"
    assert upload(worker, "Practice A") == 201
    assert upload(worker, "Practice B") == 403
    [own] = worker.get("/api/uploads").json()  # sees their own upload's results, not other people's
    assert own["uploaded_by"]["name"] == "Worker"
    titles = [n["title"] for n in worker.get("/api/notifications").json()["items"]]
    assert any(t.startswith("You were given: Upload AR sheets") for t in titles)
    [listed] = [u for u in admin.get("/api/users").json() if u["email"] == WORKER]
    assert listed["grants"][0]["practice"]["name"] == "Practice A"


def test_grants_end_when_they_expire(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, worker = browser_for(monkeypatch, ADMIN), browser_for(monkeypatch, WORKER)
    run_sql("UPDATE ar.permission_grants SET expires_at = now() - interval '1 minute'", commit=True)

    assert upload(worker, "Practice A") == 403
    assert [g["state"] for g in admin.get("/api/grants", params={"show": "ended"}).json()] == ["expired"]


def test_elevated_grants_need_a_second_person(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, admin_2 = browser_for(monkeypatch, ADMIN), browser_for(monkeypatch, ADMIN_2)
    worker = browser_for(monkeypatch, WORKER)
    new_person = {"email": "hire@example.com", "full_name": "New Hire", "role_key": "ar_associate"}

    requested = grant(admin, "users.manage", expires_on=str(date.today() + timedelta(days=30)))
    assert requested.json()["state"] == "pending"
    assert worker.post("/api/users", json=new_person).status_code == 403
    assert admin.post(f"/api/grants/{requested.json()['id']}/approve").status_code == 403  # own request
    assert any(n["kind"] == "grant.requested" for n in admin_2.get("/api/notifications").json()["items"])

    approved = admin_2.post(f"/api/grants/{requested.json()['id']}/approve")

    assert approved.json()["state"] == "active" and approved.json()["review_due_at"]
    assert worker.post("/api/users", json=new_person).status_code == 201


def test_grant_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)

    to_self = admin.post(
        "/api/grants",
        json={"user_id": uid(ADMIN), "permission": "claims.work", "reason": "Just for me please"},
    )
    not_held = grant(admin, "roles.manage")
    scoped_all = grant(admin, "scope.all_practices", "Practice A")
    no_reason = admin.post(
        "/api/grants", json={"user_id": uid(WORKER), "permission": "claims.work", "reason": "x"}
    )

    assert to_self.status_code == 403
    assert not_held.status_code == 403  # Organization Admins don't hold roles.manage
    assert scoped_all.status_code == 400
    assert no_reason.status_code == 422


def test_rejecting_revoking_and_reviewing(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, admin_2 = browser_for(monkeypatch, ADMIN), browser_for(monkeypatch, ADMIN_2)
    worker = browser_for(monkeypatch, WORKER)

    asked = grant(admin, "grants.manage").json()
    rejected = admin_2.post(f"/api/grants/{asked['id']}/reject", json={"reason": "Not needed for this role"})
    assert (
        rejected.json()["state"] == "rejected" and rejected.json()["end_reason"] == "Not needed for this role"
    )

    elevated = next(g for g in admin.get("/api/grants").json() if g["permission"] == "users.manage")
    run_sql(
        "UPDATE ar.permission_grants SET review_due_at = now() - interval '1 day' "
        f"WHERE id = {elevated['id']}",
        commit=True,
    )
    assert [g["id"] for g in admin.get("/api/grants", params={"show": "review"}).json()] == [elevated["id"]]
    assert worker.post(f"/api/grants/{elevated['id']}/review").status_code == 403
    reviewed = admin_2.post(f"/api/grants/{elevated['id']}/review").json()
    assert reviewed["review_overdue"] is False

    revoked = admin.post(f"/api/grants/{elevated['id']}/revoke", json={"reason": "Leave ended"})
    assert revoked.json()["state"] == "revoked" and revoked.json()["ended_by"]["name"] == "Org Admin"
    assert (
        worker.post(
            "/api/users", json={"email": "x@example.com", "full_name": "X", "role_key": "ar_associate"}
        ).status_code
        == 403
    )
    actions = {
        a for (a,) in run_sql("SELECT DISTINCT action FROM ar.audit_events WHERE entity_type = 'grant'")
    }
    assert actions == {
        "grant.given",
        "grant.requested",
        "grant.approved",
        "grant.rejected",
        "grant.reviewed",
        "grant.revoked",
    }


def test_refused_actions_and_error_report_downloads_are_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    worker, owner = browser_for(monkeypatch, WORKER), browser_for(monkeypatch, OWNER)
    assert worker.get("/api/audit-events").status_code == 403

    [refusal] = owner.get("/api/audit-events", params={"action": "access.refused", "limit": "1"}).json()[
        "events"
    ]
    assert refusal["actor"]["name"] == "Worker" and refusal["label"] == "GET /api/audit-events"

    owner.post("/api/uploads", data={"practice_id": pid("Practice B")}, files={"file": ("errs.csv", SHEET)})
    upload_id = owner.get("/api/uploads").json()[0]["id"]
    owner.get(f"/api/uploads/{upload_id}/errors.csv")
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'upload.errors_downloaded'") == 1
