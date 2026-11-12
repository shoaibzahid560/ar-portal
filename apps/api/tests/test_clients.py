"""Client reporting: client organisations, client accounts, the client catalogue and its safeguards."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import app_uses_test_database, browser_for, sign_in_as
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import upload_and_commit

pytestmark = requires_database

OWNER, ADMIN, LEAD, ASSOC = (
    "owner@example.com",
    "orgadmin@example.com",
    "lead@example.com",
    "assoc@example.com",
)
DR_KHAN, SANA = "drkhan@gmail.com", "sana@smilegroup.pk"
HEADER = "Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\n"


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def pid(name: str) -> str:
    return str(one(f"SELECT id FROM ar.practices WHERE name = '{name}'"))


def client_browser(monkeypatch: pytest.MonkeyPatch, email: str) -> TestClient:
    """Client staff sign in with their own Google accounts: no company domain."""
    browser, location = sign_in_as(monkeypatch, email, domain=None)
    assert location == "/dashboard", f"{email} could not sign in: {location}"
    return browser


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{OWNER}', 'Owner', 'system_admin'),
                     ('{ADMIN}', 'Omar Admin', 'org_admin'),
                     ('{LEAD}', 'Usman Lead', 'ar_lead'),
                     ('{ASSOC}', 'Bilal Associate', 'ar_associate')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Smile A'), ('Smile B'), ('Other Practice')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p WHERE u.email IN ('{LEAD}', '{ASSOC}')
        """,
    ):
        run_sql(statement, commit=True)
    give_role(LEAD, "claim_importer")
    with app_uses_test_database():
        yield


@pytest.fixture
def team(monkeypatch: pytest.MonkeyPatch) -> dict[str, TestClient]:
    browsers = {
        n: browser_for(monkeypatch, e) for n, e in (("owner", OWNER), ("admin", ADMIN), ("lead", LEAD))
    }
    if one("SELECT count(*) FROM ar.claims") == 0:
        for practice, rows in (
            ("Smile A", "Alice Smith,09-01-26,101,Delta Dental,100\nAli Raza,09-02-26,102,Aetna,200"),
            ("Smile B", "Bina Shah,09-03-26,103,Delta Dental,300"),
            ("Other Practice", "Omar Khan,09-04-26,104,MetLife,400"),
        ):
            data = (HEADER + rows + "\n").encode()
            upload_and_commit(
                browsers["lead"], browsers["admin"], pid(practice), f"{practice.replace(' ', '_')}.csv", data
            )
    return browsers


def make_org(team: dict[str, TestClient]) -> dict:
    existing = [o for o in team["admin"].get("/api/clients").json() if o["name"] == "Smile Group"]
    if existing:
        return existing[0]
    made = team["admin"].post(
        "/api/clients",
        json={
            "name": "Smile Group",
            "practice_ids": [pid("Smile A"), pid("Smile B")],
            "reports": ["statement", "aging"],
        },
    )
    assert made.status_code == 201, made.text
    org = made.json()
    added = team["admin"].post(
        f"/api/clients/{org['id']}/users",
        json={"email": DR_KHAN, "full_name": "Dr. Khan", "role_key": "client_admin"},
    )
    assert added.status_code == 201, added.text
    return org


def test_the_portal_team_sets_up_a_client(
    team: dict[str, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_org(team)

    assert {p["name"] for p in org["practices"]} == {"Smile A", "Smile B"}
    assert org["patient_detail"] is False and org["users_delegated"] is False
    assert browser_for(monkeypatch, ASSOC).get("/api/clients").status_code == 403
    [khan] = team["admin"].get(f"/api/clients/{org['id']}/users").json()
    assert khan["role"]["name"] == "Client Reporting Admin" and len(khan["practices"]) == 2
    assert DR_KHAN not in {u["email"] for u in team["owner"].get("/api/users").json()}  # not an internal user


def test_client_staff_sign_in_with_their_own_google_accounts(
    team: dict[str, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    make_org(team)
    run_sql(
        "INSERT INTO ar.users (email, full_name, role_id) "
        "SELECT 'stranger@gmail.com', 'S', id FROM ar.roles WHERE key = 'ar_associate'",
        commit=True,
    )

    _, client = sign_in_as(monkeypatch, DR_KHAN, domain=None)
    _, internal_on_gmail = sign_in_as(monkeypatch, "stranger@gmail.com", domain=None)
    _, unknown = sign_in_as(monkeypatch, "nobody@gmail.com", domain=None)

    assert client == "/dashboard"
    assert internal_on_gmail != "/dashboard" and unknown != "/dashboard"


def test_clients_see_only_their_practices_and_approved_reports(
    team: dict[str, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    make_org(team)
    khan = client_browser(monkeypatch, DR_KHAN)

    context = khan.get("/api/client-portal/context").json()
    catalogue = [r["key"] for r in khan.get("/api/client-portal/catalogue").json()]
    report = khan.post("/api/client-portal/reports/statement/run", json={}).json()
    outside = khan.post(
        "/api/client-portal/reports/statement/run", json={"practice_ids": [pid("Other Practice")]}
    ).json()

    assert context["organisation"]["name"] == "Smile Group" and context["can_manage_users"] is False
    assert catalogue == ["statement", "aging"]
    assert khan.post("/api/client-portal/reports/recovery/run", json={}).status_code == 404  # not approved
    assert report["row_count"] == 3 and {r["practice"] for r in report["rows"]} == {"Smile A", "Smile B"}
    assert outside["row_count"] == 0
    keys = {c["key"] for c in report["columns"]}
    assert not keys & {"patient", "subscriber_id", "assigned_to", "work_state", "followup"}
    assert "Alice" not in str(report)
    for internal in ("/api/claims", "/api/reports/catalogue", "/api/users", "/api/uploads", "/api/clients"):
        assert khan.get(internal).status_code == 403, internal


def test_patient_detail_is_off_until_the_portal_team_switches_it_on(
    team: dict[str, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_org(team)
    changed = team["admin"].patch(f"/api/clients/{org['id']}", json={"patient_detail": True})
    khan = client_browser(monkeypatch, DR_KHAN)

    report = khan.post("/api/client-portal/reports/statement/run", json={}).json()

    assert changed.json()["patient_detail"] is True
    assert {"patient", "subscriber_id"} <= {c["key"] for c in report["columns"]} and report[
        "contains_phi"
    ] is True
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'client.changed'") == 1
    titles = [n["title"] for n in team["owner"].get("/api/notifications").json()["items"]]
    assert any("patient names in reports" in t for t in titles)
    team["admin"].patch(f"/api/clients/{org['id']}", json={"patient_detail": False})


def test_client_files_are_logged_and_only_the_requester_downloads_them(
    team: dict[str, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    make_org(team)
    khan = client_browser(monkeypatch, DR_KHAN)

    made = khan.post("/api/client-portal/reports/aging/exports", json={"format": "pdf"})
    file = khan.get(f"/api/client-portal/exports/{made.json()['id']}/download")

    assert made.status_code == 201 and file.content.startswith(b"%PDF")
    assert "Smile_Group" in made.json()["file_name"]
    history = team["owner"].get("/api/reports/exports", params={"show": "everyone"}).json()
    assert any(e["report_title"] == "Aging summary (client: Smile Group)" for e in history)
    assert team["owner"].get(f"/api/reports/exports/{made.json()['id']}/download").status_code == 404
    titles = [n["title"] for n in team["owner"].get("/api/notifications").json()["items"]]
    assert any(t.startswith("Dr. Khan (Smile Group) exported Aging summary (PDF") for t in titles)
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'client_report.downloaded'") == 1


def test_client_admins_manage_users_only_when_delegated(
    team: dict[str, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_org(team)
    khan = client_browser(monkeypatch, DR_KHAN)
    sana = {"email": SANA, "full_name": "Sana", "role_key": "client_user", "practice_ids": [pid("Smile A")]}

    assert khan.post("/api/client-portal/users", json=sana).status_code == 403
    assert "client_users.manage" not in khan.get("/api/auth/me").json()["permissions"]  # the menu hides Users
    team["admin"].patch(f"/api/clients/{org['id']}", json={"users_delegated": True})
    assert "client_users.manage" in khan.get("/api/auth/me").json()["permissions"]
    other_admin = khan.post("/api/client-portal/users", json={**sana, "role_key": "client_admin"})
    wrong_practice = khan.post(
        "/api/client-portal/users", json={**sana, "practice_ids": [pid("Other Practice")]}
    )
    added = khan.post("/api/client-portal/users", json=sana)

    assert other_admin.status_code == 403 and wrong_practice.status_code == 400 and added.status_code == 201
    sana_browser = client_browser(monkeypatch, SANA)
    rows = sana_browser.post("/api/client-portal/reports/statement/run", json={}).json()["rows"]
    assert {r["practice"] for r in rows} == {"Smile A"}  # only her assigned practice
    gone = khan.post(f"/api/client-portal/users/{added.json()['id']}/deactivate")
    assert gone.json()["status"] == "deactivated"
    assert sana_browser.get("/api/client-portal/context").status_code == 401  # signed out at once


def test_client_and_internal_roles_never_mix(team: dict[str, TestClient]) -> None:
    make_org(team)
    owner = team["owner"]
    khan_id = str(one(f"SELECT id FROM ar.users WHERE email = '{DR_KHAN}'"))
    assoc_id = str(one(f"SELECT id FROM ar.users WHERE email = '{ASSOC}'"))

    to_client = owner.patch(f"/api/users/{assoc_id}", json={"role_key": "client_user"})
    grant = owner.post(
        "/api/grants", json={"user_id": khan_id, "permission": "claims.work", "reason": "Should never work"}
    )
    internal_edit = owner.patch(f"/api/users/{khan_id}", json={"role_key": "ar_associate"})

    assert to_client.status_code == 400
    assert grant.status_code == 400
    assert internal_edit.status_code == 404  # client accounts aren't reachable from the internal Users screen
