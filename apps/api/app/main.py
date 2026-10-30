from fastapi import FastAPI

from app.core.config import get_settings
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.claims.router import router as claims_router
from app.modules.health.router import router as health_router
from app.modules.lists.router import router as lists_router
from app.modules.practices.router import router as practices_router
from app.modules.roles.router import router as roles_router
from app.modules.uploads.router import router as uploads_router
from app.modules.users.router import router as users_router

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
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(practices_router, prefix="/api")
app.include_router(roles_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(claims_router, prefix="/api")
app.include_router(lists_router, prefix="/api")
