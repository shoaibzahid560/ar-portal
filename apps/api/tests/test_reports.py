"""Reports and exports (M6), against a real database: scope, totals, files, logging and download checks."""

import io
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from tests.auth_helpers import app_uses_test_database, browser_for
from tests.db import give_role, migrate_fresh, requires_database, run_sql
from tests.upload_helpers import upload_and_commit

pytestmark = requires_database

OWNER, APPROVER, MGMT = "owner@example.com", "approver@example.com", "mgmt@example.com"
OPS, LEAD, ASSOC = "ops@example.com", "lead@example.com", "assoc@example.com"
AUDITOR_B, TEAM_LEAD = "auditorb@example.com", "teamlead@example.com"
HEADER = "Patient,Service Date,Subscriber ID,Insurance Carrier,Billed\n"
SHEET_A = (
    HEADER + "\n".join(f"Report Patient {i},09-{i:02d}-26,{500 + i},Delta Dental,{i}00" for i in range(1, 7))
).encode()
SHEET_B = (HEADER + "Other Patient 1,09-01-26,901,Aetna,50\nOther Patient 2,09-02-26,902,Aetna,70\n").encode()


def one(sql: str) -> object:
    [(value,)] = run_sql(sql)
    return value


def uid(email: str) -> str:
    return str(one(f"SELECT id FROM ar.users WHERE email = '{email}'"))


def pid(name: str) -> str:
    return str(one(f"SELECT id FROM ar.practices WHERE name = '{name}'"))


def claim(n: int) -> str:
    return str(one(f"SELECT id FROM ar.claims WHERE patient_name = 'Report Patient {n}'"))


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    for statement in (
        f"""
        INSERT INTO ar.users (email, full_name, role_id)
        SELECT v.email, v.name, r.id
        FROM (VALUES ('{OWNER}', 'Owner', 'system_admin'),
                     ('{APPROVER}', 'Approver', 'org_admin'),
                     ('{MGMT}', 'Mona Management', 'management'),
                     ('{OPS}', 'Hamza Ops', 'ar_manager'),
                     ('{LEAD}', 'Usman Lead', 'ar_lead'),
                     ('{ASSOC}', 'Bilal Associate', 'ar_associate'),
                     ('{AUDITOR_B}', 'Zara Auditor', 'auditor'),
                     ('{TEAM_LEAD}', 'Ayesha Team Lead', 'team_lead')) AS v(email, name, role_key)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        "INSERT INTO ar.practices (name) VALUES ('Practice A'), ('Practice B')",
        f"""
        INSERT INTO ar.user_practices (user_id, practice_id)
        SELECT u.id, p.id FROM ar.users u, ar.practices p
        WHERE (u.email IN ('{OPS}', '{LEAD}', '{ASSOC}', '{TEAM_LEAD}') AND p.name = 'Practice A')
           OR (u.email = '{AUDITOR_B}' AND p.name = 'Practice B')
        """,
    ):
        run_sql(statement, commit=True)
    give_role(LEAD, "claim_importer")
    with app_uses_test_database():
        yield


@pytest.fixture
def b(monkeypatch: pytest.MonkeyPatch) -> dict[str, TestClient]:
    browsers = {
        name: browser_for(monkeypatch, email)
        for name, email in (
            ("owner", OWNER),
            ("approver", APPROVER),
            ("mgmt", MGMT),
            ("ops", OPS),
            ("lead", LEAD),
            ("assoc", ASSOC),
            ("auditor", AUDITOR_B),
            ("team_lead", TEAM_LEAD),
        )
    }
    if one("SELECT count(*) FROM ar.claims") == 0:
        upload_and_commit(
            browsers["lead"], browsers["approver"], pid("Practice A"), "Practice_A.csv", SHEET_A
        )
        upload_and_commit(
            browsers["owner"], browsers["approver"], pid("Practice B"), "Practice_B.csv", SHEET_B
        )
        for n in (1, 2, 3, 4):
            browsers["owner"].patch(f"/api/claims/{claim(n)}", json={"assigned_user_id": uid(ASSOC)})
    return browsers


def run(browser: TestClient, key: str, **filters: object) -> dict:
    response = browser.post(f"/api/reports/{key}/run", json=filters)
    assert response.status_code == 200, response.text
    return response.json()


def test_who_can_see_which_reports(b: dict[str, TestClient]) -> None:
    assert b["assoc"].get("/api/reports/catalogue").status_code == 403
    team_lead = {r["key"] for r in b["team_lead"].get("/api/reports/catalogue").json()}
    management = {r["key"] for r in b["mgmt"].get("/api/reports/catalogue").json()}

    assert "productivity" not in team_lead and "statement" in team_lead
    assert management == {"statement", "aging", "recovery", "followups", "productivity", "uploads", "ledger"}
    assert b["team_lead"].post("/api/reports/productivity/run", json={}).status_code == 403


def test_reports_stay_inside_each_persons_scope(b: dict[str, TestClient]) -> None:
    ops = run(b["ops"], "statement")
    auditor = run(b["auditor"], "statement")
    everyone = run(b["mgmt"], "statement")
    outside = run(b["ops"], "statement", practice_ids=[pid("Practice B")])

    assert ops["row_count"] == 6 and {r["practice"] for r in ops["rows"]} == {"Practice A"}
    assert auditor["row_count"] == 2 and {r["practice"] for r in auditor["rows"]} == {"Practice B"}
    assert everyone["row_count"] == 8 and everyone["scope"] == ["All practices"]
    assert outside["row_count"] == 0  # a filter can only narrow the scope
    assert float(ops["totals"]["billed"]) == 2100.0  # 100 + 200 + ... + 600


def test_statement_totals_and_reconciliation(b: dict[str, TestClient]) -> None:
    b["owner"].patch(
        f"/api/claims/{claim(1)}",
        json={"recovered_amount": "80.00", "allowed_amount": "90.00", "payment_posted_date": "2026-10-01"},
    )

    report = run(b["ops"], "statement", payer="delta")
    recovery = run(b["ops"], "recovery")

    assert float(report["totals"]["recovered"]) == 80.0
    assert float(report["totals"]["unrecovered"]) == 2020.0
    assert any("unrecovered $2,020.00" in note for note in report["notes"])
    assert recovery["row_count"] == 1 and float(recovery["totals"]["recovered"]) == 80.0
    assert recovery["totals"]["rate"] == 80.0


def test_exports_in_three_formats_are_logged_and_notified(b: dict[str, TestClient]) -> None:
    ops = b["ops"]
    files = {}
    for fmt in ("csv", "xlsx", "pdf"):
        made = ops.post("/api/reports/statement/exports", json={"format": fmt, "filters": {"payer": "Delta"}})
        assert made.status_code == 201, made.text
        assert made.json()["contains_phi"] is True and made.json()["number"].startswith("EXP-")
        files[fmt] = ops.get(f"/api/reports/exports/{made.json()['id']}/download")
        assert files[fmt].status_code == 200

    assert files["csv"].text.lstrip("\ufeff").startswith("Claim,Practice,Patient")
    assert files["pdf"].content.startswith(b"%PDF")
    book = load_workbook(io.BytesIO(files["xlsx"].content))
    formulas = [c.value for row in book["Report"].iter_rows() for c in row if isinstance(c.value, str)]
    assert any(v.startswith("=SUBTOTAL(9,") for v in formulas)
    assert "About this report" in book.sheetnames

    events = run_sql("SELECT after FROM ar.audit_events WHERE action = 'report.exported'")
    assert len(events) == 3
    assert all("Report Patient" not in json.dumps(after) for (after,) in events)  # no patient details logged
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'report.downloaded'") == 3
    titles = [n["title"] for n in b["mgmt"].get("/api/notifications").json()["items"]]
    assert any(t.startswith("Hamza Ops exported AR claims statement (PDF") for t in titles)


def test_downloads_are_checked_again(b: dict[str, TestClient]) -> None:
    ops, mgmt, owner = b["ops"], b["mgmt"], b["owner"]
    made = ops.post("/api/reports/aging/exports", json={"format": "csv"}).json()
    url = f"/api/reports/exports/{made['id']}/download"

    assert mgmt.get(url).status_code == 404  # only the person who generated it
    assert any(
        e["id"] == made["id"] for e in mgmt.get("/api/reports/exports", params={"show": "everyone"}).json()
    )

    current = next(r for r in owner.get("/api/roles").json()["roles"] if r["key"] == "ar_manager")[
        "permissions"
    ]
    owner.put(
        "/api/roles/ar_manager/permissions",
        json={"permissions": [p for p in current if p != "reports.export"]},
    )
    try:
        assert ops.get(url).status_code == 403  # permission removed after generating
    finally:
        owner.put("/api/roles/ar_manager/permissions", json={"permissions": current})
    run_sql(
        f"UPDATE ar.report_exports SET expires_at = now() - interval '1 minute' WHERE id = '{made['id']}'",
        commit=True,
    )
    assert ops.get(url).status_code == 410


def test_productivity_counts_work_and_first_pass_quality(b: dict[str, TestClient]) -> None:
    assoc, lead, ops = b["assoc"], b["lead"], b["ops"]
    for n in (2, 3):
        assoc.patch(f"/api/claims/{claim(n)}", json={"claim_status": "Paid"})
        assoc.post(f"/api/claims/{claim(n)}/request-completion", json={})
    lead.post(f"/api/claims/{claim(2)}/return", json={"reason": "Missing amounts"})
    ops.post(f"/api/claims/{claim(3)}/approve-completion", json={})
    assoc.post(f"/api/claims/{claim(2)}/request-completion", json={})
    ops.post(f"/api/claims/{claim(2)}/approve-completion", json={})

    report = run(b["mgmt"], "productivity")
    [bilal] = [r for r in report["rows"] if r["person"] == "Bilal Associate"]

    assert bilal["worked"] == 2 and bilal["completions"] == 3
    assert bilal["returned"] == 1 and bilal["first_pass"] == 50.0  # one approved first time, one returned
    assert bilal["closed"] == 2 and bilal["open_now"] == 2
    assert "quality below 90%" in bilal["flags"]


def test_ledger_and_uploads_reports(b: dict[str, TestClient]) -> None:
    b["assoc"].post(f"/api/claims/{claim(4)}/notes", json={"body": "SECRET call details"})

    ledger = run(b["ops"], "ledger")
    uploads = run(b["mgmt"], "uploads")

    assert any(r["action"] == "Note added" for r in ledger["rows"])
    assert "SECRET" not in json.dumps(ledger)
    assert {r["check"] for r in uploads["rows"]} == {"Balanced"} and uploads["row_count"] == 2


def test_dashboard_and_targets(b: dict[str, TestClient]) -> None:
    management = b["mgmt"].get("/api/reports/overview").json()
    lead = b["lead"].get("/api/reports/overview").json()

    assert management["open_claims"] == 6  # 8 claims, 2 closed
    assert management["workload"] is not None and lead["workload"] is None  # staff data needs reports.staff
    assert sum(bar["count"] for bar in management["aging"]) == 6

    assert (
        b["lead"].put("/api/reports/targets", json={**lead["targets"], "aging_over_90_pct": 5}).status_code
        == 403
    )
    updated = b["owner"].put("/api/reports/targets", json={**lead["targets"], "aging_over_90_pct": 5})
    assert updated.json()["aging_over_90_pct"] == 5
    assert one("SELECT count(*) FROM ar.audit_events WHERE action = 'settings.changed'") == 1
