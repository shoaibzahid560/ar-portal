from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] in {"ok", "unavailable", "not_configured"}


def test_routes_live_under_api_prefix() -> None:
    assert client.get("/health").status_code == 404


def test_the_code_expects_the_latest_migration() -> None:
    """SCHEMA_VERSION must be updated with every new migration, or the health check reports a false alarm."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.core.schema_version import SCHEMA_VERSION

    assert ScriptDirectory.from_config(Config("alembic.ini")).get_current_head() == SCHEMA_VERSION
