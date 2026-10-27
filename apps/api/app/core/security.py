import base64
import hashlib
import secrets


def new_token() -> str:
    """A long random value for cookies and OAuth state. 256 bits of randomness."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only the hash of a session token is stored, so a database leak does not leak sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
