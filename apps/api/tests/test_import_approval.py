"""Import preview and approval (specification, section 6): mapping, discard, reverse, late duplicates."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import preview, upload_and_commit

pytestmark = requires_database

OWNER, LEAD, APPROVER = "owner@example.com", "lead@example.com", "approver@example.com"
HEADER = "Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\n"


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def pid(name: str) -> str:
    return str(one(f"SELECT id FROM ar.practices WHERE name = '{name}'"))


def sheet(*lines: str) -> bytes:
    return (HEADER + "\n".join(lines) + "\n").encode()


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{OWNER}', 'Owner', 'system_admin'),
                     ('{LEAD}', 'Lead', 'ar_lead'),
                     ('{APPROVER}', 'Approver', 'org_admin')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name, import_code) "
        "VALUES ('Irie Dental', 'IRIE'), ('Lakeview Smiles', NULL)",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p WHERE u.email = '{LEAD}'
        """,
    ):
        run_sql(statement, commit=True)
    give_role(LEAD, "claim_importer")
    with app_uses_test_database():
        yield


@pytest.fixture
def people(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, TestClient, TestClient]:
    return browser_for(monkeypatch, LEAD), browser_for(monkeypatch, APPROVER), browser_for(monkeypatch, OWNER)


def test_the_file_name_is_checked_against_the_practice(people: tuple) -> None:
    lead, _, _ = people
    data = sheet("Mapping Patient,10-01-26,1,Aetna,10")

    wrong = preview(lead, pid("Irie Dental"), "Lakeview_Smiles_AR_10-22.csv", data)
    unclear = preview(lead, pid("Irie Dental"), "ar-sheet.csv", data)
    right = preview(lead, pid("Irie Dental"), "IRIE_AR_10-22-2026.csv", data + b"\n")

    assert wrong["status_code"] == 400 and "Lakeview Smiles" in wrong["detail"]
    assert unclear["status"] == "preview" and "doesn't mention Irie Dental" in unclear["mapping_warning"]
    assert right["mapping_warning"] is None
    for shown in (unclear, right):
        lead.post(f"/api/uploads/{shown['id']}/discard")


def test_a_discarded_preview_creates_nothing_and_keeps_no_patient_details(people: tuple) -> None:
    lead, _, _ = people
    data = sheet("Discard Patient,10-02-26,2,Aetna,20")
    shown = preview(lead, pid("Irie Dental"), "IRIE_discard.csv", data)

    discarded = lead.post(f"/api/uploads/{shown['id']}/discard").json()

    assert discarded["status"] == "discarded"
    assert one("SELECT count(*) FROM ar.claims") == 0
    assert all(r["values"] is None for r in lead.get(f"/api/uploads/{shown['id']}/rows").json())
    again = preview(lead, pid("Irie Dental"), "IRIE_discard.csv", data)  # the same file may be uploaded again
    assert again["status"] == "preview"
    lead.post(f"/api/uploads/{again['id']}/discard")


def test_a_line_committed_by_another_batch_since_the_preview_is_not_created_twice(people: tuple) -> None:
    lead, approver, _ = people
    line = "Race Patient,10-03-26,3,Aetna,30"
    first = preview(lead, pid("Irie Dental"), "IRIE_first.csv", sheet(line))
    second = preview(
        lead, pid("Irie Dental"), "IRIE_second.csv", sheet(line, "Other Patient,10-04-26,4,Aetna,40")
    )
    for shown in (first, second):
        lead.post(f"/api/uploads/{shown['id']}/submit")

    approver.post(f"/api/uploads/{first['id']}/commit")
    later = approver.post(f"/api/uploads/{second['id']}/commit").json()

    assert (later["created_claims"], later["skipped_rows"]) == (1, 1)
    assert one("SELECT count(*) FROM ar.claims WHERE patient_name = 'Race Patient'") == 1


def test_reversing_withdraws_created_claims_and_restores_updated_ones(people: tuple) -> None:
    lead, approver, owner = people
    existing = owner.get("/api/claims", params={"q": "Race Patient"}).json()["claims"][0]
    batch = upload_and_commit(
        lead,
        approver,
        pid("Irie Dental"),
        "IRIE_reverse.csv",
        sheet("Reverse Patient,10-05-26,5,Aetna,50", "Race Patient,10-03-26,3,Aetna,35"),
        decision="update",
    )
    assert (batch["created_claims"], batch["updated_claims"]) == (1, 1)
    assert owner.get(f"/api/claims/{existing['id']}").json()["billed"] == "35.00"

    no_reason = approver.post(f"/api/uploads/{batch['id']}/reverse", json={"reason": ""})
    not_allowed = lead.post(f"/api/uploads/{batch['id']}/reverse", json={"reason": "Wrong file uploaded"})
    reversed_ = approver.post(f"/api/uploads/{batch['id']}/reverse", json={"reason": "Wrong file uploaded"})

    assert no_reason.status_code == 400
    assert not_allowed.status_code == 403  # Practice Managers don't reverse batches by default
    assert reversed_.json()["status"] == "reversed"
    assert owner.get(f"/api/claims/{existing['id']}").json()["billed"] == "30.00"  # restored
    assert owner.get("/api/claims", params={"q": "Reverse Patient"}).json()["total"] == 0  # withdrawn
    withdrawn_id = one("SELECT id FROM ar.claims WHERE patient_name = 'Reverse Patient'")
    assert owner.get(f"/api/claims/{withdrawn_id}").json()["withdrawn"] is True
    redo = preview(lead, pid("Irie Dental"), "IRIE_redo.csv", sheet("Reverse Patient,10-05-26,5,Aetna,50"))
    assert redo["new_rows"] == 1  # the line is free to be uploaded again
    lead.post(f"/api/uploads/{redo['id']}/discard")


def test_a_batch_whose_claims_have_been_worked_cannot_be_reversed(people: tuple) -> None:
    lead, approver, owner = people
    batch = upload_and_commit(
        lead, approver, pid("Irie Dental"), "IRIE_worked.csv", sheet("Worked Patient,10-06-26,6,Aetna,60")
    )
    claim_id = one("SELECT id FROM ar.claims WHERE patient_name = 'Worked Patient'")
    owner.patch(f"/api/claims/{claim_id}", json={"followup_date": "2026-12-01"})

    attempt = approver.post(f"/api/uploads/{batch['id']}/reverse", json={"reason": "Trying to undo"})

    assert attempt.status_code == 409 and "CLM-" in attempt.json()["detail"]
