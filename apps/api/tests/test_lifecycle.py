"""Claim lifecycle (Phase D): mark complete, approve, return, continue, close, reopen, priority."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import upload_and_commit

pytestmark = requires_database

ADMIN, APPROVER, LEAD = "admin@example.com", "approver@example.com", "lead@example.com"
MANAGER, ASSOC = "manager@example.com", "assoc@example.com"
SHEET = (
    "Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\n"
    + "\n".join(f"Life Patient {i},10-0{i}-26,{100 + i},Aetna,{i}0" for i in range(1, 8))
    + "\n"
).encode()


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def uid(email: str) -> str:
    return str(one(f"SELECT id FROM ar.users WHERE email = '{email}'"))


def claim_id(n: int) -> str:
    return str(one(f"SELECT id FROM ar.claims WHERE patient_name = 'Life Patient {n}'"))


def kinds(browser: TestClient) -> list[str]:
    return [n["kind"] for n in browser.get("/api/notifications", params={"limit": "100"}).json()["items"]]


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{ADMIN}', 'Admin', 'system_admin'),
                     ('{APPROVER}', 'Approver', 'org_admin'),
                     ('{LEAD}', 'Lead', 'ar_lead'),
                     ('{MANAGER}', 'Manager', 'ar_manager'),
                     ('{ASSOC}', 'Associate', 'ar_associate')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Life Practice')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p WHERE u.email IN ('{LEAD}', '{MANAGER}', '{ASSOC}')
        """,
    ):
        run_sql(statement, commit=True)
    give_role(LEAD, "claim_importer")
    with app_uses_test_database():
        yield


@pytest.fixture
def people(monkeypatch: pytest.MonkeyPatch) -> dict[str, TestClient]:
    browsers = {
        who: browser_for(monkeypatch, email)
        for who, email in (
            ("admin", ADMIN),
            ("approver", APPROVER),
            ("lead", LEAD),
            ("manager", MANAGER),
            ("assoc", ASSOC),
        )
    }
    if one("SELECT count(*) FROM ar.claims") == 0:
        practice = str(one("SELECT id FROM ar.practices"))
        upload_and_commit(browsers["lead"], browsers["approver"], practice, "Life_Practice_AR.csv", SHEET)
        for n in (1, 2, 3, 4):
            browsers["admin"].patch(f"/api/claims/{claim_id(n)}", json={"assigned_user_id": uid(ASSOC)})
    return browsers


def test_marking_complete_locks_the_claim_and_asks_reviewers(people: dict[str, TestClient]) -> None:
    assoc, lead = people["assoc"], people["lead"]

    marked = assoc.post(f"/api/claims/{claim_id(1)}/request-completion", json={"reason": "Paid in full"})
    edit = assoc.patch(f"/api/claims/{claim_id(1)}", json={"followup_date": "2026-12-01"})
    note = assoc.post(f"/api/claims/{claim_id(1)}/notes", json={"body": "EOB attached earlier."})

    assert marked.json()["work_state"] == "pending_completion"
    assert marked.json()["completion_requested_by"]["name"] == "Associate"
    assert edit.status_code == 400 and "waiting for completion review" in edit.json()["detail"]
    assert note.status_code == 201  # comments are still welcome while it waits
    assert "claim.completion_requested" in kinds(lead) and "claim.completion_requested" in kinds(
        people["manager"]
    )
    assert lead.get("/api/claims", params={"view": "awaiting-completion"}).json()["total"] == 1


def test_a_reviewer_returns_it_for_correction_with_a_reason(people: dict[str, TestClient]) -> None:
    assoc, lead = people["assoc"], people["lead"]

    no_reason = lead.post(f"/api/claims/{claim_id(1)}/return", json={})
    returned = lead.post(f"/api/claims/{claim_id(1)}/return", json={"reason": "Recovered amount missing"})

    assert no_reason.status_code == 400
    body = returned.json()
    assert body["work_state"] == "open" and body["returned"] is True
    assert body["state_reason"] == "Recovered amount missing" and body["state_changed_by"]["name"] == "Lead"
    assert "claim.returned" in kinds(assoc)
    assert assoc.get("/api/claims", params={"view": "returned"}).json()["total"] == 1
    again = assoc.post(f"/api/claims/{claim_id(1)}/request-completion", json={})
    assert again.json()["returned"] is False


def test_approving_completion_needs_a_second_person(people: dict[str, TestClient]) -> None:
    lead, manager = people["lead"], people["manager"]
    lead.patch(f"/api/claims/{claim_id(5)}", json={"assigned_user_id": uid(LEAD)})
    lead.post(f"/api/claims/{claim_id(5)}/request-completion", json={})

    own = lead.post(f"/api/claims/{claim_id(5)}/approve-completion", json={})
    approved = manager.post(f"/api/claims/{claim_id(5)}/approve-completion", json={"reason": "Checked"})

    assert own.status_code == 403
    assert approved.json()["work_state"] == "closed"
    assert lead.get(f"/api/claims/{claim_id(5)}").json()["can_reopen"] is True
    assert claim_id(5) not in {c["id"] for c in lead.get("/api/claims").json()["claims"]}
    assert [c["id"] for c in lead.get("/api/claims", params={"view": "closed"}).json()["claims"]] == [
        claim_id(5)
    ]
    summary = lead.get("/api/claims/summary").json()
    assert summary["closed"] == 1 and summary["total"] == 6 and summary["awaiting_completion"] == 1
    assert lead.patch(f"/api/claims/{claim_id(5)}", json={"claim_status": "Paid"}).status_code == 400
    assert lead.post(f"/api/claims/{claim_id(5)}/notes", json={"body": "late note"}).status_code == 400


def test_continue_follow_up_sends_it_back_with_a_new_date(people: dict[str, TestClient]) -> None:
    continued = people["lead"].post(
        f"/api/claims/{claim_id(1)}/continue",
        json={"reason": "Payer asked for records", "followup_date": "2026-12-15"},
    )

    assert continued.json()["work_state"] == "open" and continued.json()["followup_date"] == "2026-12-15"
    assert "claim.continued" in kinds(people["assoc"])


def test_reviewers_close_directly_and_reopen_with_a_reason(people: dict[str, TestClient]) -> None:
    assoc, lead = people["assoc"], people["lead"]

    assert assoc.post(f"/api/claims/{claim_id(2)}/close", json={"reason": "Paid"}).status_code == 403
    assert lead.post(f"/api/claims/{claim_id(2)}/close", json={}).status_code == 400
    closed = lead.post(f"/api/claims/{claim_id(2)}/close", json={"reason": "Found paid on the payer portal"})
    assert closed.json()["work_state"] == "closed"
    assert lead.post(f"/api/claims/{claim_id(2)}/reopen", json={}).status_code == 400
    reopened = lead.post(f"/api/claims/{claim_id(2)}/reopen", json={"reason": "Payment was reversed"})

    assert reopened.json()["work_state"] == "open"
    actions = [e["action"] for e in lead.get(f"/api/claims/{claim_id(2)}/history").json()]
    assert {"claim.closed", "claim.reopened"} <= set(actions)
    assert "claim.reopened" in kinds(assoc)


def test_priority_is_set_by_managers_and_sorts_first(people: dict[str, TestClient]) -> None:
    assoc, lead = people["assoc"], people["lead"]

    refused = assoc.patch(f"/api/claims/{claim_id(3)}", json={"priority": "urgent"})
    set_ = lead.patch(f"/api/claims/{claim_id(3)}", json={"priority": "urgent"})
    bulk = lead.post(
        "/api/claims/bulk-priority", json={"claim_ids": [claim_id(6), claim_id(7)], "priority": "high"}
    )

    assert refused.status_code == 403
    assert set_.json()["priority"] == "urgent"
    assert bulk.json() == {"updated": 2}
    first, second, third = lead.get("/api/claims", params={"limit": "3"}).json()["claims"]
    assert (first["id"], {second["id"], third["id"]}) == (claim_id(3), {claim_id(6), claim_id(7)})
    assert lead.get("/api/claims", params={"view": "high-priority"}).json()["total"] == 3
    assert any(
        n["title"].endswith("is now Urgent priority") for n in assoc.get("/api/notifications").json()["items"]
    )


def test_closed_and_in_review_claims_cannot_be_bulk_assigned(people: dict[str, TestClient]) -> None:
    lead = people["lead"]
    lead.post(f"/api/claims/{claim_id(4)}/close", json={"reason": "Written off"})

    attempt = lead.post(
        "/api/claims/bulk-assign",
        json={"claim_ids": [claim_id(4), claim_id(6)], "assigned_user_id": uid(ASSOC)},
    )

    assert attempt.status_code == 400 and "Only open claims" in attempt.json()["detail"]
