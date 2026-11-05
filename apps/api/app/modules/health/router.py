from fastapi import APIRouter

from app.core.config import get_settings
from app.core.schema_version import SCHEMA_VERSION
from app.modules.health.schemas import HealthResponse
from app.modules.health.service import check_database

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Public. Used by the web app and by deploy checks to confirm the API is running."""
    settings = get_settings()
    database, schema_version = await check_database()
    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        version=settings.app_version,
        database=database,
        schema_version=schema_version,
        expected_schema_version=SCHEMA_VERSION,
    )
