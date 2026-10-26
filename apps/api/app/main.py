from fastapi import FastAPI

from app.core.config import get_settings
from app.modules.health.router import router as health_router

settings = get_settings()

app = FastAPI(
    title="AR Operations Portal API",
    version=settings.app_version,
    # Interactive docs at /api/docs everywhere except production.
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

# Every route lives under /api, matching the Next.js rewrite of /api/* to this app.
app.include_router(health_router, prefix="/api")
