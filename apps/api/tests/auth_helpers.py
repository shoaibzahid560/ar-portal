"""Shared helpers for tests that need signed-in people. Google's answer is simulated."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.modules.auth import google
from app.modules.auth.google import GoogleIdentity
from tests.db import sessionmaker


@contextmanager
def app_uses_test_database() -> Iterator[None]:
    test_sessions = sessionmaker()

    async def test_db() -> AsyncIterator:
        async with test_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def sign_in_as(
    monkeypatch: pytest.MonkeyPatch, email: str, *, domain: str | None = "example.com", verified: bool = True
) -> tuple[TestClient, str]:
    """Runs the real login and callback routes. Returns the browser and where it was sent."""

    async def fake_exchange(code: str, code_verifier: str) -> GoogleIdentity:
        return GoogleIdentity(email=email, email_verified=verified, hosted_domain=domain, name="Test")

    monkeypatch.setattr(google, "exchange_code", fake_exchange)
    browser = TestClient(app, follow_redirects=False)
    state = browser.get("/api/auth/google/login").cookies["ar_oauth"].split(".")[0]
    response = browser.get("/api/auth/google/callback", params={"state": state, "code": "one-time-code"})
    return browser, response.headers["location"]


def browser_for(monkeypatch: pytest.MonkeyPatch, email: str) -> TestClient:
    browser, location = sign_in_as(monkeypatch, email)
    assert location == "/dashboard", f"{email} could not sign in: {location}"
    return browser
