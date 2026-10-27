"""Sign-in routes that work without a database: the redirect to Google and the state check."""

from collections.abc import AsyncIterator, Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app

client = TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def no_database() -> Iterator[None]:
    """These paths must answer before touching the database, so a placeholder session is enough."""

    async def placeholder() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_db] = placeholder
    yield
    app.dependency_overrides.pop(get_db, None)


def test_login_redirects_to_google_and_remembers_state() -> None:
    response = client.get("/api/auth/google/login")

    assert response.status_code == 303
    location = urlparse(response.headers["location"])
    assert location.netloc == "accounts.google.com"
    state = parse_qs(location.query)["state"][0]
    cookie = response.cookies.get("ar_oauth")
    assert cookie is not None and cookie.startswith(f"{state}.")
    assert "httponly" in response.headers["set-cookie"].lower()


def test_callback_with_wrong_state_is_refused() -> None:
    fresh = TestClient(app, follow_redirects=False)
    fresh.get("/api/auth/google/login")

    response = fresh.get("/api/auth/google/callback", params={"state": "forged", "code": "abc"})

    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=state"
    assert "ar_session" not in response.cookies


def test_callback_without_login_cookie_is_refused() -> None:
    response = TestClient(app, follow_redirects=False).get(
        "/api/auth/google/callback", params={"state": "x", "code": "abc"}
    )

    assert response.headers["location"] == "/login?error=state"
