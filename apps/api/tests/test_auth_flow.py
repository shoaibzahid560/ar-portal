"""Full sign-in, session and permission behaviour against a real database (Google is simulated)."""

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import cli
from app.core.context import Ctx, require
from app.core.db import get_db
from app.main import app
from app.modules.auth import google
from app.modules.auth.google import GoogleIdentity
from tests.db import migrate_fresh, requires_database, run_sql, sessionmaker

pytestmark = requires_database

ADMIN = "admin@example.com"
ASSOCIATE = "associate@example.com"
PAUSED = "paused@example.com"


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    migrate_fresh()
    run_sql(
        f"""
        INSERT INTO ar.users (email, full_name, role_id, status)
        SELECT v.email, v.name, r.id, v.status
        FROM (VALUES ('{ADMIN}', 'Admin Person', 'system_admin', 'active'),
                     ('{ASSOCIATE}', 'Associate Person', 'ar_associate', 'active'),
                     ('{PAUSED}', 'Paused Person', 'ar_associate', 'paused'))
             AS v(email, name, role_key, status)
        JOIN ar.roles r ON r.key = v.role_key
        """,
        commit=True,
    )
    test_sessions = sessionmaker()

    async def test_db() -> AsyncIterator:
        async with test_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    yield
    app.dependency_overrides.pop(get_db, None)


def sign_in_as(
    monkeypatch: pytest.MonkeyPatch, email: str, *, domain: str | None = "example.com", verified: bool = True
) -> tuple[TestClient, str]:
    """Runs the real login and callback routes, with Google's answer simulated."""

    async def fake_exchange(code: str, code_verifier: str) -> GoogleIdentity:
        return GoogleIdentity(email=email, email_verified=verified, hosted_domain=domain, name="Test")

    monkeypatch.setattr(google, "exchange_code", fake_exchange)
    browser = TestClient(app, follow_redirects=False)
    state = browser.get("/api/auth/google/login").cookies["ar_oauth"].split(".")[0]
    response = browser.get("/api/auth/google/callback", params={"state": state, "code": "one-time-code"})
    return browser, response.headers["location"]


def audit_count(action: str, entity_id: str) -> int:
    [(count,)] = run_sql(
        f"SELECT count(*) FROM ar.audit_events WHERE action = '{action}' AND entity_id = '{entity_id}'"
    )
    return count


def test_registered_active_user_gets_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    browser, location = sign_in_as(monkeypatch, ADMIN)

    assert location == "/dashboard"
    me = browser.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["email"] == ADMIN
    assert body["role"]["key"] == "system_admin"
    assert "users.manage" in body["permissions"]


def test_session_token_is_stored_only_as_a_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    browser, _ = sign_in_as(monkeypatch, ADMIN)
    token = browser.cookies["ar_session"]

    assert run_sql(f"SELECT count(*) FROM ar.sessions WHERE token_hash = '{token}'") == [(0,)]


def test_each_sign_in_writes_exactly_one_audit_event(monkeypatch: pytest.MonkeyPatch) -> None:
    [(user_id,)] = run_sql(f"SELECT id::text FROM ar.users WHERE email = '{ASSOCIATE}'")
    before = audit_count("auth.login", user_id)

    sign_in_as(monkeypatch, ASSOCIATE)

    assert audit_count("auth.login", user_id) == before + 1


def test_unregistered_person_is_refused_and_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    browser, location = sign_in_as(monkeypatch, "stranger@example.com")

    assert location == "/login?error=not_registered"
    assert "ar_session" not in browser.cookies
    assert audit_count("auth.login_denied", "stranger@example.com") == 1


def test_paused_user_gets_the_same_answer_as_an_unknown_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _, location = sign_in_as(monkeypatch, PAUSED)

    assert location == "/login?error=not_registered"


@pytest.mark.parametrize(("domain", "verified"), [("gmail.com", True), (None, True), ("example.com", False)])
def test_wrong_domain_or_unverified_email_is_refused(
    monkeypatch: pytest.MonkeyPatch, domain: str | None, verified: bool
) -> None:
    _, location = sign_in_as(monkeypatch, ADMIN, domain=domain, verified=verified)

    assert location == "/login?error=domain"


def test_signed_out_session_stops_working(monkeypatch: pytest.MonkeyPatch) -> None:
    browser, _ = sign_in_as(monkeypatch, ADMIN)
    token = browser.cookies["ar_session"]

    assert browser.post("/api/auth/logout").status_code == 204

    stolen = TestClient(app, cookies={"ar_session": token})
    assert stolen.get("/api/auth/me").status_code == 401


def test_idle_session_expires_after_30_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    browser, _ = sign_in_as(monkeypatch, ASSOCIATE)
    run_sql(
        "UPDATE ar.sessions SET last_seen_at = now() - interval '31 minutes' "
        "WHERE id = (SELECT id FROM ar.sessions ORDER BY created_at DESC LIMIT 1)",
        commit=True,
    )

    assert browser.get("/api/auth/me").status_code == 401


def test_deactivated_user_is_locked_out_on_the_next_request(monkeypatch: pytest.MonkeyPatch) -> None:
    run_sql(
        "INSERT INTO ar.users (email, full_name, role_id) "
        "SELECT 'temp@example.com', 'Temp', id FROM ar.roles WHERE key = 'ar_associate' "
        "ON CONFLICT (email) DO NOTHING",
        commit=True,
    )
    browser, _ = sign_in_as(monkeypatch, "temp@example.com")
    assert browser.get("/api/auth/me").status_code == 200

    run_sql("UPDATE ar.users SET status = 'deactivated' WHERE email = 'temp@example.com'", commit=True)

    assert browser.get("/api/auth/me").status_code == 401


def test_no_cookie_means_401() -> None:
    assert TestClient(app).get("/api/auth/me").status_code == 401


def test_require_gives_403_without_the_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    @app.get("/api/_test/users-manage")
    async def protected(ctx: Ctx = Depends(require("users.manage"))) -> dict:  # noqa: B008
        return {"ok": True}

    try:
        associate, _ = sign_in_as(monkeypatch, ASSOCIATE)
        admin, _ = sign_in_as(monkeypatch, ADMIN)
        assert associate.get("/api/_test/users-manage").status_code == 403
        assert admin.get("/api/_test/users-manage").status_code == 200
    finally:
        app.router.routes.pop()


def test_create_admin_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_sessionmaker", sessionmaker)

    first = asyncio.run(cli.create_admin("New.Admin@Example.com", "New Admin"))
    again = asyncio.run(cli.create_admin("new.admin@example.com", "New Admin"))

    assert first == "Created System Administrator new.admin@example.com."
    assert "Nothing changed" in again
    rows = run_sql(
        "SELECT r.key, u.status FROM ar.users u JOIN ar.roles r ON r.id = u.role_id "
        "WHERE u.email = 'new.admin@example.com'"
    )
    assert rows == [("system_admin", "active")]
    assert run_sql("SELECT count(*) FROM ar.audit_events WHERE request_id = 'cli:create-admin'") == [(1,)]
