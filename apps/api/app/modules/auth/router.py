from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.context import SESSION_COOKIE, CurrentCtx
from app.core.db import DbSession
from app.core.schemas import NamedRef, RoleRef
from app.core.security import new_token
from app.modules.auth import google, repository, service
from app.modules.auth.schemas import MeResponse, MeUser

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_COOKIE = "ar_oauth"
OAUTH_COOKIE_MAX_AGE = 600  # seconds the person has to finish choosing their Google account


def _login_error(reason: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?error={reason}", status_code=303)
    response.delete_cookie(OAUTH_COOKIE, path="/api/auth")
    return response


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    """Public. Sends the browser to Google's account chooser."""
    settings = get_settings()
    state, verifier = new_token(), new_token()
    response = RedirectResponse(google.authorization_url(state, verifier), status_code=303)
    response.set_cookie(
        OAUTH_COOKIE,
        f"{state}.{verifier}",
        max_age=OAUTH_COOKIE_MAX_AGE,
        path="/api/auth",
        httponly=True,
        secure=not settings.is_local,
        samesite="lax",
    )
    return response


@router.get("/google/callback")
async def google_callback(request: Request, db: DbSession) -> RedirectResponse:
    """Public. Google sends the browser back here; a session starts if the person is allowed in."""
    settings = get_settings()
    stored_state, _, verifier = request.cookies.get(OAUTH_COOKIE, "").partition(".")
    code = request.query_params.get("code")
    if not stored_state or not verifier or request.query_params.get("state") != stored_state:
        return _login_error("state")
    if not code:
        return _login_error("google")

    try:
        identity = await google.exchange_code(code, verifier)
    except google.GoogleSignInError:
        return _login_error("google")

    token, denial = await service.sign_in(
        db,
        identity,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    if token is None:
        return _login_error(str(denial))

    response = RedirectResponse("/dashboard", status_code=303)
    response.delete_cookie(OAUTH_COOKIE, path="/api/auth")
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(service.ABSOLUTE_LIFETIME.total_seconds()),
        path="/",
        httponly=True,
        secure=not settings.is_local,
        samesite="lax",
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, db: DbSession) -> Response:
    """Ends the current session. Safe to call when already signed out."""
    token = request.cookies.get(SESSION_COOKIE)
    active = await service.resume(db, token) if token else None
    if active is not None:
        await service.sign_out(db, active)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=MeResponse)
async def me(ctx: CurrentCtx) -> MeResponse:
    """The signed-in person, their role and permissions, and the practices and teams they can see."""
    practices = await repository.get_user_practices(ctx.db, ctx.user.id)
    teams = await repository.get_user_teams(ctx.db, ctx.user.id)
    return MeResponse(
        user=MeUser.model_validate(ctx.user, from_attributes=True),
        role=RoleRef(key=ctx.role.key, name=ctx.role.name),
        permissions=sorted(ctx.permissions),
        practices=[NamedRef(id=p.id, name=p.name) for p in practices],
        teams=[NamedRef(id=t.id, name=t.name) for t in teams],
    )
