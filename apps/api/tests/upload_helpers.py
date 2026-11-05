"""Helpers for the import flow: preview, decide, submit, approve and commit (by a second person)."""

from fastapi.testclient import TestClient


def preview(browser: TestClient, practice_id: str, name: str, data: bytes) -> dict:
    response = browser.post("/api/uploads", data={"practice_id": practice_id}, files={"file": (name, data)})
    return {"status_code": response.status_code, **response.json()}


def decide_all(reviewer: TestClient, upload_id: str, decision: str = "create") -> None:
    """Decides every line that needs it: "create", "skip", or "update" (to the first matching claim)."""
    for row in reviewer.get(f"/api/uploads/{upload_id}/rows", params={"show": "needs-decision"}).json():
        body: dict = {"decision": decision}
        if decision == "update":
            if row["classification"] == "repeat":
                body = {"decision": "create"}
            else:
                body["target_claim_id"] = row["candidates"][0]["id"]
        response = reviewer.patch(f"/api/uploads/{upload_id}/rows/{row['id']}", json=body)
        assert response.status_code == 200, response.text


def upload_and_commit(
    uploader: TestClient,
    approver: TestClient,
    practice_id: str,
    name: str,
    data: bytes,
    decision: str = "create",
) -> dict:
    """The whole flow. Returns the committed upload (or the failed one, if the file couldn't be used)."""
    result = preview(uploader, practice_id, name, data)
    assert result["status_code"] == 201, result
    if result["status"] != "preview":
        return result
    decide_all(approver, result["id"], decision)
    submitted = uploader.post(f"/api/uploads/{result['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    committed = approver.post(f"/api/uploads/{result['id']}/commit")
    assert committed.status_code == 200, committed.text
    return {"status_code": 201, **committed.json()}
