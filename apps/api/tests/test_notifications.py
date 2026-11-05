"""Who is notified about what (brief, section 8), against a real database with the synthetic sheets."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.clock import business_today
from tests.auth_helpers import app_uses_test_database, browser_for, sign_in_as
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import preview, upload_and_commit

pytestmark = requires_database

FIXTURES = Path(__file__).parent / "fixtures"
WEEK_1 = FIXTURES / "Sample_Practice_AR-HBS_10-22-2026_sheet.xlsx"
WEEK_2 = FIXTURES / "Sample_Practice_AR-HBS_10-29-2026_sheet.xlsx"
ADMIN, MANAGEMENT, LEAD = "admin@example.com", "management@example.com", "lead@example.com"
ASSOC, ASSOC_2 = "assoc@example.com", "assoc2@example.com"


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def user_id(email: str) -> str:
    return str(one(f"SELECT id FROM ar.users WHERE email = '{email}'"))


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{ADMIN}', 'Admin', 'system_admin'),
                     ('{MANAGEMENT}', 'Management', 'management'),
                     ('{LEAD}', 'Lead', 'ar_lead'),
                     ('{ASSOC}', 'Associate One', 'ar_associate'),
                     ('{ASSOC_2}', 'Associate Two', 'ar_associate')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Practice One')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p WHERE u.email IN ('{LEAD}', '{ASSOC}', '{ASSOC_2}')
        """,
    ):
        run_sql(statement, commit=True)
    give_role(LEAD, "claim_importer")  # Practice Managers / AR Leads who upload also hold Claim Importer
    with app_uses_test_database():
        yield


def inbox(browser: TestClient) -> list[dict]:
    return browser.get("/api/notifications", params={"limit": "200"}).json()["items"]


def kinds(browser: TestClient) -> list[str]:
    return [n["kind"] for n in inbox(browser)]


def practice() -> str:
    return str(one("SELECT id FROM ar.practices"))


def test_every_committed_upload_reaches_management_and_the_uploader_hears_the_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead, admin = browser_for(monkeypatch, LEAD), browser_for(monkeypatch, ADMIN)
    upload_and_commit(lead, admin, practice(), WEEK_1.name, WEEK_1.read_bytes())

    assert kinds(browser_for(monkeypatch, MANAGEMENT)) == ["upload.completed"]
    assert "upload.awaiting_approval" in kinds(admin)  # the approver was asked
    assert kinds(lead) == ["upload.committed"]
    [note] = inbox(browser_for(monkeypatch, MANAGEMENT))
    assert note["title"] == "UPL-000001 committed for Practice One" and "87 new claims" in note["body"]


def test_upload_problems_reach_the_uploader_and_approvers_hear_what_needs_deciding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead, admin = browser_for(monkeypatch, LEAD), browser_for(monkeypatch, ADMIN)
    preview(
        lead,
        practice(),
        "bad.csv",
        b"Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\nA,someday,1,Aetna,5\n",
    )
    shown = preview(lead, practice(), WEEK_2.name, WEEK_2.read_bytes())
    lead.post(f"/api/uploads/{shown['id']}/submit")

    assert kinds(lead)[0] == "upload.errors"
    waiting = next(n for n in inbox(admin) if n["title"].startswith("UPL-000003"))
    assert waiting["kind"] == "upload.awaiting_approval" and "1 need a decision" in waiting["body"]
    assert "upload.awaiting_approval" not in kinds(browser_for(monkeypatch, ASSOC))


def test_bulk_assignment_sends_one_notification_per_person(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    ids = [
        c["id"] for c in lead.get("/api/claims", params={"view": "unassigned", "limit": "3"}).json()["claims"]
    ]
    lead.post("/api/claims/bulk-assign", json={"claim_ids": ids, "assigned_user_id": user_id(ASSOC)})

    [note] = inbox(browser_for(monkeypatch, ASSOC))
    assert note["title"] == "3 claims were assigned to you by Lead" and note["link"] == "/claims?view=mine"
    assert (
        inbox(browser_for(monkeypatch, MANAGEMENT))[0]["title"] == "Lead assigned 3 claims to Associate One"
    )
    assert "claim.assigned" not in kinds(lead)


def test_handing_a_claim_over_tells_the_new_owner_and_reassigning_tells_the_old_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    associate = browser_for(monkeypatch, ASSOC)
    [first, second, _] = associate.get("/api/claims", params={"view": "mine"}).json()["claims"]
    associate.patch(f"/api/claims/{first['id']}", json={"assigned_user_id": user_id(ASSOC_2)})
    browser_for(monkeypatch, LEAD).patch(
        f"/api/claims/{second['id']}", json={"assigned_user_id": user_id(ASSOC_2)}
    )

    titles = [n["title"] for n in inbox(browser_for(monkeypatch, ASSOC_2))]
    assert f"{first['number']} was assigned to you by Associate One" in titles
    assert f"{second['number']} was assigned to you by Lead" in titles
    assert inbox(associate)[0]["title"] == f"{second['number']} was reassigned to Associate Two"
    assert not any(
        "by Associate One" in n["title"] for n in inbox(associate)
    )  # not told about their own action


def test_a_colleagues_note_notifies_the_assignee(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = browser_for(monkeypatch, ASSOC_2)
    claim = worker.get("/api/claims", params={"view": "mine"}).json()["claims"][0]
    browser_for(monkeypatch, LEAD).post(
        f"/api/claims/{claim['id']}/notes", json={"body": "Please call the payer."}
    )

    assert inbox(worker)[0]["title"] == f"Lead added a note on {claim['number']}"


def test_follow_up_reminders_are_created_once(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = browser_for(monkeypatch, ASSOC_2)
    due, late = worker.get("/api/claims", params={"view": "mine"}).json()["claims"][:2]
    today = business_today()
    worker.patch(f"/api/claims/{due['id']}", json={"followup_date": str(today)})
    worker.patch(f"/api/claims/{late['id']}", json={"followup_date": str(today - timedelta(days=3))})

    first = [n["title"] for n in inbox(worker)]
    second = [n["title"] for n in inbox(worker)]

    assert f"{due['number']} follow-up is due today" in first
    assert f"{late['number']} follow-up is overdue" in first
    assert first == second


def test_marking_read(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = browser_for(monkeypatch, ASSOC_2)
    unread = worker.get("/api/notifications/unread-count").json()["unread"]
    newest = inbox(worker)[0]

    assert worker.post(f"/api/notifications/{newest['id']}/read").status_code == 204
    assert worker.get("/api/notifications/unread-count").json()["unread"] == unread - 1
    assert browser_for(monkeypatch, ASSOC).post(f"/api/notifications/{newest['id']}/read").status_code == 404
    worker.post("/api/notifications/read-all")
    assert worker.get("/api/notifications/unread-count").json()["unread"] == 0


def test_management_hears_about_users_permissions_and_refused_sign_ins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    admin.post(
        "/api/users", json={"email": "new@example.com", "full_name": "New Person", "role_key": "ar_associate"}
    )
    admin.put("/api/roles/auditor/permissions", json={"permissions": ["dashboard.view", "claims.view"]})
    sign_in_as(monkeypatch, "stranger@example.com")

    titles = [n["title"] for n in inbox(browser_for(monkeypatch, MANAGEMENT))]
    assert "Admin added New Person as AR Associate" in titles
    assert "Admin changed the Reporting Analyst / Auditor permissions" in titles
    assert "Sign-in refused for stranger@example.com" in titles
    assert not any("added New Person" in n["title"] for n in inbox(admin))


def test_no_notification_mentions_a_patient() -> None:
    texts = run_sql("SELECT title || ' ' || coalesce(body, '') FROM ar.notifications")
    assert texts and not any("Sample Patient" in t for (t,) in texts)
