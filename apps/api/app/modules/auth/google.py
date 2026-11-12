"""Google sign-in (OpenID Connect, authorization code flow with PKCE)."""

import asyncio
import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from app.core.config import get_settings
from app.core.security import pkce_challenge

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a password
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleSignInError(Exception):
    """Google did not confirm the sign-in. The message is safe to log; it never contains tokens."""


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    email_verified: bool
    hosted_domain: str | None
    name: str


def authorization_url(state: str, code_verifier: str, *, company: bool = True) -> str:
    """`company=False` is the client sign-in: no company-domain hint, so client staff can pick their own
    Google account. Who may get in is still decided in auth.service.sign_in."""
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    if settings.company_domain and company:
        # Only a hint to Google's account chooser; the domain is checked again in identity_from_claims.
        params["hd"] = settings.company_domain
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, code_verifier: str) -> GoogleIdentity:
    """Trades the one-time code for the user's identity, talking to Google directly over HTTPS."""
    settings = get_settings()
    body = urlencode(
        {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }
    ).encode()

    def post() -> dict[str, Any]:
        request = urllib.request.Request(
            TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - fixed https URL
            return json.loads(response.read())

    try:
        payload = await asyncio.to_thread(post)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise GoogleSignInError("Google did not accept the sign-in code") from error

    id_token = payload.get("id_token")
    if not isinstance(id_token, str):
        raise GoogleSignInError("Google's response had no ID token")
    return identity_from_claims(decode_id_token(id_token))


def decode_id_token(id_token: str) -> dict[str, Any]:
    """
    Reads the ID token's claims. Its signature is not checked because the token came straight from
    Google's token endpoint over HTTPS, authenticated with our client secret, which is how Google's
    OpenID Connect documentation says such tokens may be trusted. The claims are still validated.
    """
    try:
        payload_part = id_token.split(".")[1]
        padded = payload_part + "=" * (-len(payload_part) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError) as error:
        raise GoogleSignInError("Google's ID token could not be read") from error
    if not isinstance(claims, dict):
        raise GoogleSignInError("Google's ID token could not be read")
    return claims


def identity_from_claims(claims: dict[str, Any], now: float | None = None) -> GoogleIdentity:
    settings = get_settings()
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleSignInError("ID token was not issued by Google")
    if claims.get("aud") != settings.google_client_id:
        raise GoogleSignInError("ID token was issued for a different application")
    if float(claims.get("exp", 0)) < (now if now is not None else time.time()):
        raise GoogleSignInError("ID token has expired")
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise GoogleSignInError("ID token has no email address")
    hosted_domain = claims.get("hd")
    return GoogleIdentity(
        email=email.strip().lower(),
        email_verified=claims.get("email_verified") is True,
        hosted_domain=hosted_domain.lower() if isinstance(hosted_domain, str) else None,
        name=str(claims.get("name", "")),
    )
