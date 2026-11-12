from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from sqlalchemy.exc import ProgrammingError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.refusals import record_refusal
from app.core.schema_version import UPDATE_MESSAGE
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.claims.router import router as claims_router
from app.modules.clients.router import portal as client_portal_router
from app.modules.clients.router import router as clients_router
from app.modules.grants.router import router as grants_router
from app.modules.health.router import router as health_router
from app.modules.lists.router import router as lists_router
from app.modules.notifications.router import router as notifications_router
from app.modules.practices.router import router as practices_router
from app.modules.reports.router import router as reports_router
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
app.include_router(notifications_router, prefix="/api")
app.include_router(grants_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(client_portal_router, prefix="/api")


@app.exception_handler(StarletteHTTPException)
async def http_errors(request: Request, exc: StarletteHTTPException):  # type: ignore[no-untyped-def]
    """Every refused action (403) is written to the audit log; the response itself is unchanged."""
    if exc.status_code == 403:
        await record_refusal(request, str(exc.detail))
    return await http_exception_handler(request, exc)


@app.exception_handler(ProgrammingError)
async def database_behind(request: Request, exc: ProgrammingError):  # type: ignore[no-untyped-def]
    """A missing table or column almost always means the database wasn't updated after new code arrived."""
    message = str(exc.orig) if exc.orig else str(exc)
    if "does not exist" in message:
        return JSONResponse(status_code=503, content={"detail": UPDATE_MESSAGE})
    raise exc
