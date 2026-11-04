"""Bulk assignment and the review queue, against a real database, using the synthetic sample sheets."""

import csv
import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import migrate_fresh, requires_database, run_sql

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
    with app_uses_test_database():
        yield


def upload(browser: TestClient, name: str, data: bytes) -> dict:
    response = browser.post(
        "/api/uploads", data={"practice_id": practice_id("Practice One")}, files={"file": (name, data)}
    )
    assert response.status_code == 201, response.text
    return response.json()


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
    upload(lead, WEEK_1.name, WEEK_1.read_bytes())
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


# ---- Review queue -----------------------------------------------------------------------------------------


def test_same_claim_updates_the_earlier_claim_and_folds_the_line_in(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    upload(lead, WEEK_2.name, WEEK_2.read_bytes())
    [line_id] = claim_ids(lead, 5, view="needs-review")
    line = lead.get(f"/api/claims/{line_id}").json()
    assert line["can_review"] is True

    candidates = lead.get(f"/api/claims/{line_id}/matches").json()
    assert candidates and all(c["id"] != line_id for c in candidates)
    earlier = next(c for c in candidates if c["insurance_carrier"] == line["insurance_carrier"])
    assert earlier["billed"] != line["billed"]

    kept = lead.post(f"/api/claims/{line_id}/resolve", json={"decision": "same", "target_id": earlier["id"]})

    assert kept.status_code == 200, kept.text
    assert kept.json()["id"] == earlier["id"] and kept.json()["billed"] == line["billed"]
    counts = lead.get("/api/claims/counts").json()
    assert counts["needs-review"] == 0 and counts["merged"] == 1 and counts["all"] == 97
    merged = lead.get(f"/api/claims/{line_id}").json()
    assert merged["merged_into"]["id"] == earlier["id"] and merged["can_work"] is False
    assert lead.patch(f"/api/claims/{line_id}", json={"claim_status": "Paid"}).status_code == 400
    actions = {e["action"] for e in lead.get(f"/api/claims/{earlier['id']}/history").json()}
    assert "claim.updated_from_upload" in actions

    # The changed line appears again in a later sheet: it's recognised and skipped.
    again = upload(lead, "week3.csv", line_csv([line]))
    assert again["duplicate_rows"] == 1 and again["created_claims"] == 0


def test_separate_claim_keeps_both(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    existing = lead.get(f"/api/claims/{claim_ids(lead, 1, view='unassigned')[0]}").json()
    upload(lead, "second-line.csv", line_csv([{**existing, "billed": "999.99"}]))
    [line_id] = claim_ids(lead, 5, view="needs-review")

    result = lead.post(f"/api/claims/{line_id}/resolve", json={"decision": "separate"})

    assert result.json()["needs_review"] is False
    assert lead.get("/api/claims/counts").json()["needs-review"] == 0
    assert lead.get(f"/api/claims/{line_id}").status_code == 200


def test_a_line_with_work_on_it_cannot_be_folded_in(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    existing = lead.get(f"/api/claims/{claim_ids(lead, 1, view='unassigned')[0]}").json()
    upload(lead, "third-line.csv", line_csv([{**existing, "billed": "888.88"}]))
    [line_id] = claim_ids(lead, 5, view="needs-review")
    lead.patch(f"/api/claims/{line_id}", json={"assigned_user_id": user_id(ASSOC)})

    result = lead.post(
        f"/api/claims/{line_id}/resolve", json={"decision": "same", "target_id": existing["id"]}
    )

    assert result.status_code == 400 and "work recorded" in result.json()["detail"]


def test_only_reviewers_can_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = browser_for(monkeypatch, LEAD)
    [line_id] = claim_ids(lead, 5, view="needs-review")

    for email in (ASSOC, MANAGEMENT):
        browser = browser_for(monkeypatch, email)
        assert browser.post(f"/api/claims/{line_id}/resolve", json={"decision": "separate"}).status_code in (
            403,
            404,
        )
        assert browser.patch(f"/api/claims/{line_id}", json={"needs_review": False}).status_code in (403, 404)
