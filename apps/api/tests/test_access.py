"""
The access model from the Roles & Access specification: effective access = role defaults (primary role +
additional roles, per practice), constrained by practice scope. Every check goes through the API, as a
browser (or anyone bypassing it) would.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import upload_and_commit

pytestmark = requires_database

WEEK_1 = Path(__file__).parent / "fixtures" / "Sample_Practice_AR-HBS_10-22-2026_sheet.xlsx"
OWNER, ORG_ADMIN = "owner@example.com", "orgadmin@example.com"
MIXED = "mixed@example.com"  # AR Associate everywhere, Practice Manager / AR Lead + Claim Importer in A
IMPORTER, TEAM_LEAD, AUDITOR = "importer@example.com", "teamlead@example.com", "auditor@example.com"
IN_TEAM, NOT_IN_TEAM, IN_B = "inteam@example.com", "notinteam@example.com", "inb@example.com"


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
                     ('{ORG_ADMIN}', 'Org Admin', 'org_admin'),
                     ('{MIXED}', 'Mixed Person', 'ar_associate'),
                     ('{IMPORTER}', 'Importer', 'claim_importer'),
                     ('{TEAM_LEAD}', 'Team Lead', 'team_lead'),
                     ('{AUDITOR}', 'Auditor A', 'auditor'),
                     ('{IN_TEAM}', 'In Team', 'ar_associate'),
                     ('{NOT_IN_TEAM}', 'Not In Team', 'ar_associate'),
                     ('{IN_B}', 'In B', 'ar_associate')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Practice A'), ('Practice B')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p
        WHERE (u.email IN ('{MIXED}', '{IMPORTER}', '{TEAM_LEAD}', '{AUDITOR}', '{IN_TEAM}', '{NOT_IN_TEAM}')
               AND p.name = 'Practice A')
           OR (u.email IN ('{MIXED}', '{IN_B}') AND p.name = 'Practice B')
        """,
        f"""
        INSERT INTO ar.teams (name, practice_id, manager_user_id)
        SELECT 'Team A', p.id, u.id FROM ar.practices p, ar.users u
        WHERE p.name = 'Practice A' AND u.email = '{TEAM_LEAD}'
        """,
        f"""
        INSERT INTO ar.team_members (team_id, user_id)
        SELECT t.id, u.id FROM ar.teams t, ar.users u WHERE t.name = 'Team A' AND u.email = '{IN_TEAM}'
        """,
    ):
        run_sql(statement, commit=True)
    give_role(MIXED, "ar_lead", "Practice A")
    give_role(MIXED, "claim_importer", "Practice A")
    with app_uses_test_database():
        yield


def upload(browser: TestClient, practice: str, name: str, data: bytes) -> object:
    return browser.post("/api/uploads", data={"practice_id": pid(practice)}, files={"file": (name, data)})


def total(browser: TestClient) -> int:
    return browser.get("/api/claims").json()["total"]


# ---- Claim Importer -----------------------------------------------------------------------------------


def test_claim_importer_uploads_for_its_practice_only_and_does_no_ar_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = browser_for(monkeypatch, IMPORTER)

    owner = browser_for(monkeypatch, OWNER)
    committed = upload_and_commit(importer, owner, pid("Practice A"), WEEK_1.name, WEEK_1.read_bytes())
    assert committed["status"] == "committed"
    small = b"Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\nB Patient,10-01-26,999,Aetna,50\n"
    assert upload(importer, "Practice B", "b.csv", small).status_code == 403
    assert importer.get("/api/claims").status_code == 403
    assert [p["name"] for p in importer.get("/api/practices", params={"can": "uploads.create"}).json()] == [
        "Practice A"
    ]
    org_admin = browser_for(monkeypatch, ORG_ADMIN)
    assert upload_and_commit(owner, org_admin, pid("Practice B"), "b.csv", small)["status"] == "committed"


# ---- Different roles in different practices ------------------------------------------------------------


def test_roles_can_differ_per_practice(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = browser_for(monkeypatch, OWNER)
    [b_claim] = owner.get("/api/claims", params={"practice_id": pid("Practice B")}).json()["claims"]
    other_b = upload_and_commit(
        owner,
        browser_for(monkeypatch, ORG_ADMIN),
        pid("Practice B"),
        "b2.csv",
        b"Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\nB Other,10-02-26,998,Aetna,60\n",
    )
    assert other_b["status"] == "committed"
    owner.patch(f"/api/claims/{b_claim['id']}", json={"assigned_user_id": uid(MIXED)})

    mixed = browser_for(monkeypatch, MIXED)
    claims = mixed.get("/api/claims", params={"limit": "500"}).json()["claims"]
    in_b = [c for c in claims if c["practice"]["name"] == "Practice B"]

    assert (
        len(claims) == 88
    )  # every claim in A (Practice Manager there) + only their own in B (Associate there)
    assert [c["id"] for c in in_b] == [b_claim["id"]]
    me = mixed.get("/api/auth/me").json()
    assert {(r["role"]["key"], r["practice"]["name"]) for r in me["extra_roles"]} == {
        ("ar_lead", "Practice A"),
        ("claim_importer", "Practice A"),
    }
    a_claim = mixed.get("/api/claims", params={"practice_id": pid("Practice A"), "limit": "1"}).json()[
        "claims"
    ][0]
    assert mixed.get(f"/api/claims/{a_claim['id']}").json()["can_assign"] is True
    small = b"Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\nX,10-03-26,1,Aetna,5\n"
    assert upload(mixed, "Practice A", "x.csv", small).status_code == 201
    assert upload(mixed, "Practice B", "x.csv", small).status_code == 403


# ---- AR Team Lead ---------------------------------------------------------------------------------------


def test_team_lead_sees_the_teams_queue_and_unassigned_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = browser_for(monkeypatch, OWNER)
    a = owner.get(
        "/api/claims", params={"practice_id": pid("Practice A"), "view": "unassigned", "limit": "3"}
    )
    first, second, third = [c["id"] for c in a.json()["claims"]]
    owner.post(
        "/api/claims/bulk-assign", json={"claim_ids": [first, second], "assigned_user_id": uid(IN_TEAM)}
    )
    owner.patch(f"/api/claims/{third}", json={"assigned_user_id": uid(NOT_IN_TEAM)})

    lead = browser_for(monkeypatch, TEAM_LEAD)

    assert lead.get(f"/api/claims/{first}").status_code == 200  # a team member's claim
    assert lead.get(f"/api/claims/{third}").status_code == 404  # someone outside the team
    a_total = int(one(f"SELECT count(*) FROM ar.claims WHERE practice_id = '{pid('Practice A')}'"))
    assert total(lead) == a_total - 1
    unassigned = lead.get("/api/claims", params={"view": "unassigned", "limit": "1"}).json()["claims"][0]
    assert (
        lead.patch(f"/api/claims/{unassigned['id']}", json={"assigned_user_id": uid(IN_TEAM)}).status_code
        == 200
    )
    assert lead.patch(f"/api/claims/{first}", json={"assigned_user_id": uid(IN_B)}).status_code == 400


# ---- Reporting Analyst / Auditor ------------------------------------------------------------------------


def test_auditor_reads_its_practices_only_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    auditor = browser_for(monkeypatch, AUDITOR)
    events = auditor.get("/api/audit-events", params={"limit": "200"}).json()["events"]
    some_claim = auditor.get("/api/claims", params={"limit": "1"}).json()["claims"][0]

    assert events and all(e["action"] not in ("auth.login", "user.created") for e in events)
    assert {
        c["practice"]["name"] for c in auditor.get("/api/claims", params={"limit": "500"}).json()["claims"]
    } == {"Practice A"}
    assert auditor.patch(f"/api/claims/{some_claim['id']}", json={"claim_status": "Paid"}).status_code == 403


# ---- Organization Admin and the Portal Owner --------------------------------------------------------------


def test_organization_admin_manages_people_but_not_owner_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ORG_ADMIN)

    created = admin.post(
        "/api/users", json={"email": "new@example.com", "full_name": "New", "role_key": "ar_associate"}
    )
    owner_made = admin.post(
        "/api/users", json={"email": "boss@example.com", "full_name": "Boss", "role_key": "system_admin"}
    )
    matrix = admin.put("/api/roles/auditor/permissions", json={"permissions": ["dashboard.view"]})
    owner_touched = admin.patch(f"/api/users/{uid(OWNER)}", json={"full_name": "Renamed"})

    assert created.status_code == 201
    assert owner_made.status_code == 403
    assert matrix.status_code == 403
    assert owner_touched.status_code == 403


def test_a_role_for_one_practice_applies_there_only(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ORG_ADMIN)
    url = f"/api/users/{uid(IN_B)}/roles"

    owner_role = admin.put(url, json={"roles": [{"role_key": "system_admin"}]})
    team_role = admin.put(url, json={"roles": [{"role_key": "team_lead", "practice_id": pid("Practice A")}]})

    assert owner_role.status_code == 400
    assert team_role.status_code == 200
    body = team_role.json()
    assert {p["name"] for p in body["practices"]} == {"Practice B"}  # membership unchanged
    assert body["extra_roles"][0]["role"]["name"] == "AR Team Lead"
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'user.roles_changed'") == 1
    # As Team Lead in A they see A's unassigned queue; as an Associate in B, still only their own B claims.
    person = browser_for(monkeypatch, IN_B)
    claims = person.get("/api/claims", params={"limit": "500"}).json()["claims"]
    assert any(c["practice"]["name"] == "Practice A" for c in claims)
    assert all(
        c["assigned_to"] and c["assigned_to"]["name"] == "In B"
        for c in claims
        if c["practice"]["name"] == "Practice B"
    )


def test_scoped_managers_give_roles_only_for_their_own_practices(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = browser_for(monkeypatch, OWNER)
    current = next(r for r in owner.get("/api/roles").json()["roles"] if r["key"] == "ar_lead")["permissions"]
    owner.put("/api/roles/ar_lead/permissions", json={"permissions": [*current, "users.manage"]})
    try:
        manager = browser_for(monkeypatch, MIXED)  # Practice Manager in A only
        url = f"/api/users/{uid(NOT_IN_TEAM)}/roles"
        everywhere = manager.put(url, json={"roles": [{"role_key": "team_lead"}]})
        elsewhere = manager.put(
            url, json={"roles": [{"role_key": "team_lead", "practice_id": pid("Practice B")}]}
        )
        here = manager.put(url, json={"roles": [{"role_key": "team_lead", "practice_id": pid("Practice A")}]})
        elevated = manager.put(
            url, json={"roles": [{"role_key": "org_admin", "practice_id": pid("Practice A")}]}
        )
        assert everywhere.status_code == 403
        assert elsewhere.status_code == 403
        assert here.status_code == 200
        assert elevated.status_code == 403
    finally:
        owner.put("/api/roles/ar_lead/permissions", json={"permissions": current})


def test_owner_level_changes_need_a_recent_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = browser_for(monkeypatch, OWNER)
    run_sql(
        f"UPDATE ar.sessions SET created_at = now() - interval '20 minutes' WHERE user_id = '{uid(OWNER)}'",
        commit=True,
    )

    stale = owner.put("/api/roles/auditor/permissions", json={"permissions": ["dashboard.view"]})
    fresh = browser_for(monkeypatch, OWNER).put(
        "/api/roles/auditor/permissions", json={"permissions": ["dashboard.view"]}
    )

    assert stale.status_code == 403 and "sign in again" in stale.json()["detail"]
    assert fresh.status_code == 200
