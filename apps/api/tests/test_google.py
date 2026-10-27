import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.security import pkce_challenge
from app.modules.auth.google import (
    GoogleSignInError,
    authorization_url,
    decode_id_token,
    identity_from_claims,
)

CLIENT_ID = "test-client-id.apps.googleusercontent.com"


def _claims(**overrides: object) -> dict:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "exp": time.time() + 300,
        "email": "Person@Example.com",
        "email_verified": True,
        "hd": "example.com",
        "name": "Test Person",
    }
    claims.update(overrides)
    return claims


def _token(claims: dict) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


def test_authorization_url_asks_google_for_the_right_things() -> None:
    query = parse_qs(urlparse(authorization_url("state123", "verifier456")).query)

    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["http://localhost:3000/api/auth/google/callback"]
    assert query["scope"] == ["openid email profile"]
    assert query["state"] == ["state123"]
    assert query["code_challenge"] == [pkce_challenge("verifier456")]
    assert query["code_challenge_method"] == ["S256"]
    assert query["hd"] == ["example.com"]


def test_valid_claims_give_a_lowercased_identity() -> None:
    identity = identity_from_claims(decode_id_token(_token(_claims())))

    assert identity.email == "person@example.com"
    assert identity.email_verified is True
    assert identity.hosted_domain == "example.com"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example"},
        {"aud": "someone-elses-client-id"},
        {"exp": time.time() - 10},
        {"email": ""},
    ],
)
def test_untrustworthy_claims_are_rejected(overrides: dict) -> None:
    with pytest.raises(GoogleSignInError):
        identity_from_claims(_claims(**overrides))


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(GoogleSignInError):
        decode_id_token("not-a-token")
