"""Bulk assignment, decisions on uploaded lines before commit, and the older review queue."""

import csv
import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import preview, upload_and_commit

pytestmark = requires_database

FIXTURES = Path(__file__).parent / "fixtures"
WEEK_1 = FIXTURES / "Sample_Practice_AR-HBS_10-22-2026_sheet.xlsx"
WEEK_2 = FIXTURES / "Sample_Practice_AR-HBS_10-29-2026_sheet.xlsx"
LEAD, ASSOC, ASSOC_2, OUTSIDER, MANAGEMENT = (
    "lead@example.com",
    "assoc@example.com",
    "assoc2@example.com",
    "outsider@example.com",
    "management@example.com",
)


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def user_id(email: str) -> str:
    return str(one(f"SELECT id FROM ar.users WHERE email = '{email}'"))


def practice_id(name: str) -> str:
    return str(one(f"SELECT id FROM ar.practices WHERE name = '{name}'"))


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{LEAD}', 'Lead', 'ar_lead'),
                     ('approver@example.com', 'Approver', 'org_admin'),
                     ('{ASSOC}', 'Associate One', 'ar_associate'),
                     ('{ASSOC_2}', 'Associate Two', 'ar_associate'),
                     ('{OUTSIDER}', 'Outsider', 'ar_associate'),
                     ('{MANAGEMENT}', 'Management', 'management')) AS v(email, name, role_key)
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


def upload(monkeypatch: pytest.MonkeyPatch, name: str, data: bytes, decision: str = "create") -> dict:
    """The lead uploads; a second person (an Organization Admin) decides open lines and commits."""
    return upload_and_commit(
        browser_for(monkeypatch, LEAD),
        browser_for(monkeypatch, "approver@example.com"),
        practice_id("Practice One"),
        name,
        data,
        decision,
    )


def claim_ids(browser: TestClient, count: int, **params: str) -> list[str]:
    page = browser.get("/api/claims", params={"limit": str(count), **params}).json()
    return [c["id"] for c in page["claims"]]


def line_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Patient", "Service Date", "Subscriber ID", "Insurance Carrier", "Billed"])
    for r in rows:
        writer.writerow(
            [r["patient_name"], r["service_date"], r["subscriber_id"], r["insurance_carrier"], r["billed"]]
        )
    return buffer.getvalue().encode()


# ---- Bulk assignment -------------------------------------------------------------------------------------


def test_lead_assigns_many_claims_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    upload(monkeypatch, WEEK_1.name, WEEK_1.read_bytes())
    ids = claim_ids(lead, 10, view="unassigned")

    result = lead.post("/api/claims/bulk-assign", json={"claim_ids": ids, "assigned_user_id": user_id(ASSOC)})

    assert result.json() == {"updated": 10}
    assert browser_for(monkeypatch, ASSOC).get("/api/claims").json()["total"] == 10
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'claim.assigned'") == 10


def test_bulk_assignment_is_all_or_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    ids = claim_ids(lead, 5, view="unassigned")

    outsider = lead.post(
        "/api/claims/bulk-assign", json={"claim_ids": ids, "assigned_user_id": user_id(OUTSIDER)}
    )
    unknown = lead.post(
        "/api/claims/bulk-assign",
        json={
            "claim_ids": [*ids, "00000000-0000-0000-0000-000000000000"],
            "assigned_user_id": user_id(ASSOC),
        },
    )

    assert outsider.status_code == 400 and unknown.status_code == 404
    assert lead.get("/api/claims/counts").json()["unassigned"] == 77  # nothing changed


def test_assignee_choices_cover_every_selected_practice(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)

    people = lead.get("/api/claims/assignees", params={"practice_id": practice_id("Practice One")}).json()
    elsewhere = lead.get("/api/claims/assignees", params={"practice_id": practice_id("Practice Two")})

    assert {p["name"] for p in people} == {"Lead", "Associate One", "Associate Two"}
    assert elsewhere.status_code == 403


def test_an_associate_can_hand_several_claims_to_a_colleague(monkeypatch: pytest.MonkeyPatch) -> None:
    associate = browser_for(monkeypatch, ASSOC)
    ids = claim_ids(associate, 2, view="mine")

    result = associate.post(
        "/api/claims/bulk-assign", json={"claim_ids": ids, "assigned_user_id": user_id(ASSOC_2)}
    )

    assert result.json() == {"updated": 2}
    assert associate.get("/api/claims").json()["total"] == 8


# ---- Decisions on uploaded lines, before anything is committed --------------------------------------


def test_a_changed_line_updates_the_existing_claim_and_is_recognised_next_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead, approver = browser_for(monkeypatch, LEAD), browser_for(monkeypatch, "approver@example.com")
    shown = preview(lead, practice_id("Practice One"), WEEK_2.name, WEEK_2.read_bytes())
    [line] = approver.get(f"/api/uploads/{shown['id']}/rows", params={"show": "needs-decision"}).json()
    earlier = next(
        c
        for c in line["candidates"]
        if c["values"]["insurance_carrier"] == line["values"]["insurance_carrier"]
    )
    assert earlier["values"]["billed"] != line["values"]["billed"]

    decided = approver.patch(
        f"/api/uploads/{shown['id']}/rows/{line['id']}",
        json={"decision": "update", "target_claim_id": earlier["id"]},
    )
    assert decided.json()["decided_by"] == "Approver"
    lead.post(f"/api/uploads/{shown['id']}/submit")
    committed = approver.post(f"/api/uploads/{shown['id']}/commit").json()

    assert (committed["created_claims"], committed["updated_claims"]) == (10, 1)
    claim = approver.get(f"/api/claims/{earlier['id']}").json()
    assert claim["billed"] == line["values"]["billed"]  # same claim, same ID, new amount
    assert "claim.updated_from_upload" in {
        e["action"] for e in approver.get(f"/api/claims/{earlier['id']}/history").json()
    }
    # The preview's patient values are cleared once the batch is committed.
    assert all(r["values"] is None for r in approver.get(f"/api/uploads/{shown['id']}/rows").json())

    again = preview(lead, practice_id("Practice One"), "week3.csv", line_csv([line["values"]]))
    assert (again["duplicate_rows"], again["changed_rows"], again["new_rows"]) == (1, 0, 0)
    lead.post(f"/api/uploads/{again['id']}/discard")


def test_create_and_skip_decisions(monkeypatch: pytest.MonkeyPatch) -> None:
    lead, approver = browser_for(monkeypatch, LEAD), browser_for(monkeypatch, "approver@example.com")
    first, second = (
        approver.get(f"/api/claims/{i}").json() for i in claim_ids(approver, 2, view="unassigned")
    )
    before = approver.get("/api/claims").json()["total"]
    sheet = line_csv([{**first, "billed": "999.99"}, {**second, "billed": "888.88"}])
    shown = preview(lead, practice_id("Practice One"), "two-lines.csv", sheet)
    create_row, skip_row = approver.get(f"/api/uploads/{shown['id']}/rows").json()

    approver.patch(f"/api/uploads/{shown['id']}/rows/{create_row['id']}", json={"decision": "create"})
    approver.patch(f"/api/uploads/{shown['id']}/rows/{skip_row['id']}", json={"decision": "skip"})
    lead.post(f"/api/uploads/{shown['id']}/submit")
    committed = approver.post(f"/api/uploads/{shown['id']}/commit").json()

    assert (committed["created_claims"], committed["updated_claims"], committed["skipped_rows"]) == (1, 0, 1)
    assert approver.get("/api/claims").json()["total"] == before + 1


def test_commit_needs_every_decision_and_a_second_person(monkeypatch: pytest.MonkeyPatch) -> None:
    lead, approver = browser_for(monkeypatch, LEAD), browser_for(monkeypatch, "approver@example.com")
    existing = approver.get(f"/api/claims/{claim_ids(approver, 1, view='unassigned')[0]}").json()
    shown = preview(
        lead, practice_id("Practice One"), "open.csv", line_csv([{**existing, "billed": "777.77"}])
    )
    lead.post(f"/api/uploads/{shown['id']}/submit")

    undecided = approver.post(f"/api/uploads/{shown['id']}/commit")
    own = lead.post(f"/api/uploads/{shown['id']}/commit")
    detail = approver.get(f"/api/uploads/{shown['id']}").json()

    assert undecided.status_code == 400 and "need a decision" in undecided.json()["detail"]
    assert own.status_code == 403
    assert (
        detail["actions"]["can_commit"] is False
        and "need a decision" in detail["actions"]["commit_blocked_because"]
    )
    rejected = approver.post(f"/api/uploads/{shown['id']}/reject", json={"reason": "Wrong week's sheet"})
    assert (
        rejected.json()["status"] == "rejected" and rejected.json()["decision_reason"] == "Wrong week's sheet"
    )


def test_only_reviewers_decide_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    existing = lead.get(f"/api/claims/{claim_ids(lead, 1, view='unassigned')[0]}").json()
    shown = preview(
        lead, practice_id("Practice One"), "check.csv", line_csv([{**existing, "billed": "666.66"}])
    )
    [row] = lead.get(f"/api/uploads/{shown['id']}/rows").json()

    associate = browser_for(monkeypatch, ASSOC)
    attempt = associate.patch(f"/api/uploads/{shown['id']}/rows/{row['id']}", json={"decision": "skip"})

    assert attempt.status_code in (403, 404)
    lead.post(f"/api/uploads/{shown['id']}/discard")


# ---- The older review queue (lines flagged by uploads made before import approval) -----------------


def test_older_flagged_lines_can_still_be_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Before import approval, a possible change was created as a claim flagged "needs review"."""
    lead = browser_for(monkeypatch, LEAD)
    [(earlier, later)] = run_sql(
        "SELECT min(id::text), max(id::text) FROM ar.claims "
        "WHERE merged_into_id IS NULL AND withdrawn_at IS NULL AND assigned_user_id IS NULL "
        "GROUP BY patient_name, service_date, subscriber_id HAVING count(*) = 2 LIMIT 1"
    )
    run_sql(f"UPDATE ar.claims SET needs_review = true WHERE id = '{later}'", commit=True)

    kept = lead.post(f"/api/claims/{later}/resolve", json={"decision": "same", "target_id": earlier})

    assert kept.status_code == 200, kept.text
    assert lead.get(f"/api/claims/{later}").json()["merged_into"]["id"] == earlier
    for email in (ASSOC, MANAGEMENT):
        assert browser_for(monkeypatch, email).post(
            f"/api/claims/{later}/resolve", json={"decision": "separate"}
        ).status_code in (
            400,
            403,
            404,
        )
