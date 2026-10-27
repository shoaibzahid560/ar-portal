from functools import lru_cache
from typing import Literal
from urllib.parse import quote, unquote

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_POSTGRES_SCHEMES = {"postgresql", "postgres", "postgresql+asyncpg"}


class Settings(BaseSettings):
    """Settings come from environment variables, or from apps/api/.env during local development."""

    # hide_input_in_errors: a bad DATABASE_URL must never print the password in an error message.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "preview", "staging", "production"] = "local"
    app_version: str = "0.1.0"
    database_url: str | None = None

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

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
