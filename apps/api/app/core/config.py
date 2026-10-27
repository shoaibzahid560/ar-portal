from functools import lru_cache
from typing import Literal
from urllib.parse import quote, unquote

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_POSTGRES_SCHEMES = {"postgresql", "postgres", "postgresql+asyncpg"}


class Settings(BaseSettings):
    """Settings come from environment variables, or from apps/api/.env during local development."""

    # hide_input_in_errors: a bad setting must never print a password or secret in an error message.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "preview", "staging", "production"] = "local"
    app_version: str = "0.1.0"
    database_url: str | None = None

    # The address people open in the browser. Google sends them back to <web_origin>/api/auth/google/callback.
    web_origin: str = "http://localhost:3000"

    # Google sign-in (Google Cloud Console > APIs & Services > Credentials > OAuth client ID).
    google_client_id: str = ""
    google_client_secret: str = ""
    # Company Google Workspace domain, e.g. hiredbillingsupport.com. Required outside local development.
    allowed_google_domain: str = ""

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        """
        Accepts the connection string exactly as Supabase shows it, with the password pasted in as-is.
        Selects the asyncpg driver and escapes special characters in the password (@ : / # [ ] ...).
        """
        if value is None:
            return None
        value = value.strip().strip("\"'").strip()
        if not value:
            return None

        scheme, separator, rest = value.partition("://")
        if not separator or scheme not in _POSTGRES_SCHEMES:
            raise ValueError(
                "DATABASE_URL must be a single line starting with postgresql:// "
                "(Supabase: Connect > Session pooler)"
            )

        # The host comes after the LAST "@", so an "@" inside the password is kept as part of it.
        credentials, at_sign, location = rest.rpartition("@")
        if not at_sign:
            return f"postgresql+asyncpg://{rest}"
        username, colon, password = credentials.partition(":")
        user_part = quote(unquote(username), safe="")
        if colon:
            user_part += ":" + quote(unquote(password), safe="")
        return f"postgresql+asyncpg://{user_part}@{location}"

    @field_validator("web_origin")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("allowed_google_domain")
    @classmethod
    def lowercase_domain(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def require_company_domain_outside_local(self) -> "Settings":
        if self.app_env != "local" and not self.allowed_google_domain:
            raise ValueError("ALLOWED_GOOGLE_DOMAIN must be set outside local development")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.web_origin}/api/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
