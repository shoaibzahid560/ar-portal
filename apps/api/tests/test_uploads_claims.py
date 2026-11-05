"""Uploading AR sheets and working claims, against a real database. Uses the synthetic sample files."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.clock import business_today
from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import preview, upload_and_commit

pytestmark = requires_database

FIXTURES = Path(__file__).parent / "fixtures"
WEEK_1 = FIXTURES / "Sample_Practice_AR-HBS_10-22-2026_sheet.xlsx"
WEEK_2 = FIXTURES / "Sample_Practice_AR-HBS_10-29-2026_sheet.xlsx"

ADMIN, MANAGEMENT, LEAD = "admin@example.com", "management@example.com", "lead@example.com"
APPROVER = "approver@example.com"  # an Organization Admin: approves what the lead uploads
ASSOC, ASSOC_2, OUTSIDER = "assoc@example.com", "assoc2@example.com", "outsider@example.com"


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def practice_id(name: str) -> str:
    return str(one(f"SELECT id FROM ar.practices WHERE name = '{name}'"))


def user_id(email: str) -> str:
    return str(one(f"SELECT id FROM ar.users WHERE email = '{email}'"))


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    """Practice One: lead, two associates. Practice Two: the outsider associate."""
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{ADMIN}', 'Admin', 'system_admin'),
                     ('{APPROVER}', 'Approver', 'org_admin'),
                     ('{MANAGEMENT}', 'Management', 'management'),
                     ('{LEAD}', 'Lead', 'ar_lead'),
                     ('{ASSOC}', 'Associate One', 'ar_associate'),
                     ('{ASSOC_2}', 'Associate Two', 'ar_associate'),
                     ('{OUTSIDER}', 'Outsider', 'ar_associate')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Practice One'), ('Practice Two')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p
        WHERE (u.email IN ('{LEAD}', '{ASSOC}', '{ASSOC_2}') AND p.name = 'Practice One')
           OR (u.email = '{OUTSIDER}' AND p.name = 'Practice Two')
        """,
    ):
        run_sql(statement, commit=True)
    give_role(LEAD, "claim_importer")  # Practice Managers / AR Leads who upload also hold Claim Importer
    with app_uses_test_database():
        yield


def upload(browser: TestClient, practice: str, path: Path, decision: str = "create") -> dict:
    """Uploads, then the approver decides open lines, the uploader submits and the approver commits."""
    return upload_and_commit(
        browser, browser_for_approver(), practice_id(practice), path.name, path.read_bytes(), decision
    )


_approver: list[TestClient] = []


def browser_for_approver() -> TestClient:
    return _approver[0]


@pytest.fixture(autouse=True)
def approver(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _approver[:] = [browser_for(monkeypatch, APPROVER)]
    yield


def first_claim(browser: TestClient, **params: str) -> dict:
    return browser.get("/api/claims", params={"limit": "1", **params}).json()["claims"][0]


# ---- Uploads ----------------------------------------------------------------------------------------


def test_lead_uploads_the_week_one_sheet_and_a_second_person_commits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = browser_for(monkeypatch, LEAD)

    shown = preview(lead, practice_id("Practice One"), WEEK_1.name, WEEK_1.read_bytes())
    assert shown["status"] == "preview" and one("SELECT count(*) FROM ar.claims") == 0  # nothing created yet
    assert (shown["total_rows"], shown["new_rows"], shown["repeat_rows"], shown["error_rows"]) == (
        87,
        86,
        1,
        0,
    )
    lead.post(f"/api/uploads/{shown['id']}/discard")

    result = upload(lead, "Practice One", WEEK_1)

    assert result["status"] == "committed"
    assert result["created_claims"] == 87  # the repeated line was confirmed as a separate claim
    assert result["decided_by"]["name"] == "Approver" and result["submitted_by"]["name"] == "Lead"
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'claim.imported'") == 87


def test_same_file_twice_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    result = preview(
        browser_for(monkeypatch, LEAD), practice_id("Practice One"), WEEK_1.name, WEEK_1.read_bytes()
    )

    assert result["status_code"] == 409
    assert "already uploaded as UPL-" in result["detail"]


def test_next_weeks_sheet_skips_carried_over_lines_and_updates_a_changed_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = browser_for(monkeypatch, LEAD)
    shown = preview(lead, practice_id("Practice One"), WEEK_2.name, WEEK_2.read_bytes())
    assert (shown["total_rows"], shown["duplicate_rows"], shown["changed_rows"], shown["new_rows"]) == (
        82,
        71,
        1,
        10,
    )
    lead.post(f"/api/uploads/{shown['id']}/discard")

    result = upload(lead, "Practice One", WEEK_2, decision="update")

    assert (result["created_claims"], result["updated_claims"], result["skipped_rows"]) == (10, 1, 71)
    assert one("SELECT count(*) FROM ar.claims") == 97


def test_uploads_are_limited_to_the_practices_in_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    data = WEEK_1.read_bytes()
    assert (
        preview(browser_for(monkeypatch, LEAD), practice_id("Practice Two"), WEEK_1.name, data)["status_code"]
        == 403
    )
    assert (
        preview(browser_for(monkeypatch, ASSOC), practice_id("Practice One"), WEEK_1.name, data)[
            "status_code"
        ]
        == 403
    )


def test_row_problems_are_listed_and_the_report_has_no_cell_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sheet = tmp_path / "with-errors.csv"
    sheet.write_text(
        "Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\n"
        "Test Patient A,10-01-26,111,Aetna,100\n"
        "Test Patient B,someday,222,Aetna,100\n"
        "Test Patient C,10-02-26,333,Aetna,lots\n"
    )
    admin = browser_for(monkeypatch, ADMIN)

    result = upload_and_commit(
        admin, browser_for(monkeypatch, APPROVER), practice_id("Practice Two"), sheet.name, sheet.read_bytes()
    )
    report = admin.get(f"/api/uploads/{result['id']}/errors.csv").text

    assert result["status"] == "committed"
    assert (result["total_rows"], result["created_claims"], result["error_rows"]) == (3, 1, 2)
    assert [(e["row_number"], e["column"]) for e in result["errors"]] == [(3, "Service Date"), (4, "Billed")]
    assert "someday" not in report and "lots" not in report and "Test Patient" not in report


def test_unreadable_file_is_recorded_as_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sheet = tmp_path / "broken.xlsx"
    sheet.write_bytes(b"this is not a workbook")

    result = preview(
        browser_for(monkeypatch, ADMIN), practice_id("Practice Two"), sheet.name, sheet.read_bytes()
    )

    assert result["status"] == "failed"
    assert "couldn't be opened" in result["failure_reason"]
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'upload.failed'") == 1


# ---- Who sees which claims ------------------------------------------------------------------------------


def test_associates_see_only_their_own_claims_and_others_see_their_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    associate = browser_for(monkeypatch, ASSOC)
    lead = browser_for(monkeypatch, LEAD)
    management = browser_for(monkeypatch, MANAGEMENT)
    outsider = browser_for(monkeypatch, OUTSIDER)

    assert associate.get("/api/claims").json()["total"] == 0
    assert lead.get("/api/claims").json()["total"] == 97
    assert management.get("/api/claims").json()["total"] == 98  # includes Practice Two's claim
    assert outsider.get("/api/claims").json()["total"] == 0


# ---- Working a claim ----------------------------------------------------------------------------------


def test_lead_assigns_and_the_associate_works_the_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    claim = first_claim(lead)
    options = {a["name"] for a in lead.get(f"/api/claims/{claim['id']}/assignees").json()}
    assert options == {"Lead", "Associate One", "Associate Two"}  # the outsider works elsewhere

    assigned = lead.patch(f"/api/claims/{claim['id']}", json={"assigned_user_id": user_id(ASSOC)})
    assert assigned.status_code == 200 and assigned.json()["assigned_to"]["name"] == "Associate One"

    associate = browser_for(monkeypatch, ASSOC)
    before = one("SELECT count(*) FROM ar.audit_events WHERE action = 'claim.updated'")
    worked = associate.patch(
        f"/api/claims/{claim['id']}",
        json={
            "claim_status": "In- Process",
            "action_taken": "Called Insurance",
            "allowed_amount": "120.50",
            "followup_date": str(business_today() + timedelta(days=7)),
        },
    )

    assert worked.status_code == 200, worked.text
    body = worked.json()
    assert body["claim_status"] == "In- Process" and body["allowed_amount"] == "120.50"
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'claim.updated'") == before + 1


def test_work_fields_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    claim = first_claim(lead)

    assert lead.patch(f"/api/claims/{claim['id']}", json={"claim_status": "Made up"}).status_code == 400
    assert lead.patch(f"/api/claims/{claim['id']}", json={"recovered_amount": "-5"}).status_code == 422
    assert lead.patch(f"/api/claims/{claim['id']}", json={"recovered_amount": "1.234"}).status_code == 422
    assert (
        lead.patch(f"/api/claims/{claim['id']}", json={"billed": "1"}).status_code == 422
    )  # upload data is read-only


def test_claims_cannot_be_assigned_outside_the_practice(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    claim = first_claim(lead, view="unassigned")

    response = lead.patch(f"/api/claims/{claim['id']}", json={"assigned_user_id": user_id(OUTSIDER)})

    assert response.status_code == 400


def test_an_associate_can_hand_a_claim_to_a_colleague(monkeypatch: pytest.MonkeyPatch) -> None:
    associate = browser_for(monkeypatch, ASSOC)
    claim = first_claim(associate, view="mine")

    handed = associate.patch(f"/api/claims/{claim['id']}", json={"assigned_user_id": user_id(ASSOC_2)})

    assert handed.status_code == 200
    assert associate.get(f"/api/claims/{claim['id']}").status_code == 404  # no longer theirs
    assert browser_for(monkeypatch, ASSOC_2).get(f"/api/claims/{claim['id']}").status_code == 200
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'claim.assigned'") == 2


def test_notes_and_eob(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = browser_for(monkeypatch, ASSOC_2)
    claim = first_claim(worker, view="mine")

    noted = worker.post(f"/api/claims/{claim['id']}/notes", json={"body": "Called payer, reference 4821."})
    attached = worker.post(
        f"/api/claims/{claim['id']}/eob", files={"file": ("eob.pdf", b"%PDF-1.4 sample", "application/pdf")}
    )
    wrong_type = worker.post(f"/api/claims/{claim['id']}/eob", files={"file": ("eob.exe", b"MZ", "x")})
    download = worker.get(f"/api/claims/{claim['id']}/eob")

    assert noted.status_code == 201 and noted.json()["notes"][0]["body"] == "Called payer, reference 4821."
    assert attached.json()["eob"]["file_name"] == "eob.pdf"
    assert wrong_type.status_code == 400
    assert download.content == b"%PDF-1.4 sample"
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'claim.eob_downloaded'") == 1
    history = worker.get(f"/api/claims/{claim['id']}/history").json()
    assert {"claim.imported", "claim.assigned", "claim.note_added", "claim.eob_attached"} <= {
        e["action"] for e in history
    }


def test_management_can_view_but_not_work_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    management = browser_for(monkeypatch, MANAGEMENT)
    claim = first_claim(management)

    assert management.get(f"/api/claims/{claim['id']}").json()["can_work"] is False
    assert management.patch(f"/api/claims/{claim['id']}", json={"claim_status": "Paid"}).status_code == 403


def test_view_only_roles_see_who_a_claim_was_assigned_to(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    claim = first_claim(lead, view="unassigned")
    lead.patch(f"/api/claims/{claim['id']}", json={"assigned_user_id": user_id(ASSOC)})

    history = browser_for(monkeypatch, MANAGEMENT).get(f"/api/claims/{claim['id']}/history").json()
    assigned = next(e for e in history if e["action"] == "claim.assigned")

    assert assigned["people"] == {user_id(ASSOC): "Associate One"}
    assert assigned["actor"]["name"] == "Lead"


def test_review_flag_from_older_uploads_can_still_be_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uploads from before import approval flagged lines on the claim itself; those can still be cleared."""
    lead = browser_for(monkeypatch, LEAD)
    run_sql("UPDATE ar.claims SET needs_review = true WHERE number = 5", commit=True)
    flagged = first_claim(lead, view="needs-review")

    cleared = lead.patch(f"/api/claims/{flagged['id']}", json={"needs_review": False})

    assert cleared.json()["needs_review"] is False
    assert lead.get("/api/claims/counts").json()["needs-review"] == 0


# ---- Views, counts, dashboard --------------------------------------------------------------------------


def test_follow_up_views_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    ids = [
        c["id"] for c in lead.get("/api/claims", params={"limit": "3", "view": "unassigned"}).json()["claims"]
    ]
    today = business_today()
    lead.patch(f"/api/claims/{ids[0]}", json={"followup_date": str(today)})
    lead.patch(f"/api/claims/{ids[1]}", json={"followup_date": str(today - timedelta(days=2))})
    lead.patch(f"/api/claims/{ids[2]}", json={"followup_date": str(today + timedelta(days=1))})

    counts = lead.get("/api/claims/counts").json()
    summary = lead.get("/api/claims/summary").json()

    assert counts["due-today"] == 1 and counts["overdue"] == 1 and counts["tomorrow"] == 1
    assert summary["total"] == 97 and summary["due_today"] == 1 and summary["overdue"] == 1
    assert sum(s["count"] for s in summary["by_status"]) == 97


# ---- Dropdown lists ------------------------------------------------------------------------------------


def test_dropdowns_match_the_sheet_and_can_be_edited(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = browser_for(monkeypatch, ADMIN)
    lists = admin.get("/api/lists").json()
    assert [o["value"] for o in lists["pay_status"]] == ["Paid to Patient", "Paid to Practice"]
    assert (
        len(lists["claim_status"]) == 13
        and len(lists["action_taken"]) == 10
        and len(lists["check_status"]) == 4
    )

    added = admin.post("/api/lists/claim_status", json={"value": "Appeal filed"})
    assert added.status_code == 201 and added.json()["claim_status"][-1]["value"] == "Appeal filed"

    paid = next(o for o in lists["claim_status"] if o["value"] == "Paid")
    admin.patch(f"/api/lists/items/{paid['id']}", json={"active": False})
    claim = first_claim(admin)
    assert admin.patch(f"/api/claims/{claim['id']}", json={"claim_status": "Paid"}).status_code == 400
    admin.patch(f"/api/lists/items/{paid['id']}", json={"active": True})

    lead = browser_for(monkeypatch, LEAD)
    assert lead.post("/api/lists/claim_status", json={"value": "Nope"}).status_code == 403


def test_audit_log_shows_note_text_to_those_who_may_see_the_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    management = browser_for(monkeypatch, MANAGEMENT)
    [event] = management.get("/api/audit-events", params={"action": "claim.note_added"}).json()["events"]

    assert event["note"] == "Called payer, reference 4821."
    assert event["label"].startswith("CLM-") and event["link"].startswith("/claims/")

    run_sql(
        "INSERT INTO ar.users (email, full_name, role_id) "
        "SELECT 'auditor2@example.com', 'Scoped Auditor', id FROM ar.roles WHERE key = 'auditor'",
        commit=True,
    )
    run_sql(
        "INSERT INTO ar.user_practices (user_id, practice_id) "
        "SELECT u.id, p.id FROM ar.users u, ar.practices p "
        "WHERE u.email = 'auditor2@example.com' AND p.name = 'Practice Two'",
        commit=True,
    )
    auditor = browser_for(monkeypatch, "auditor2@example.com")
    # An auditor limited to Practice Two sees only Practice Two's events: not this note, and not
    # organisation-wide events such as other people's sign-ins.
    assert auditor.get("/api/audit-events", params={"action": "claim.note_added"}).json()["events"] == []
    assert auditor.get("/api/audit-events", params={"action": "auth."}).json()["events"] == []
