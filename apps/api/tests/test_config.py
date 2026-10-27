import pytest
from pydantic import ValidationError
from sqlalchemy import make_url

from app.core.config import Settings

HOST = "aws-1-ap-south-1.pooler.supabase.com:5432/postgres"


@pytest.mark.parametrize("scheme", ["postgresql", "postgres", "postgresql+asyncpg"])
def test_database_url_always_uses_asyncpg(scheme: str) -> None:
    settings = Settings(database_url=f"{scheme}://postgres.ref:secret@{HOST}")

    assert settings.database_url == f"postgresql+asyncpg://postgres.ref:secret@{HOST}"


@pytest.mark.parametrize("password", ["p@ss@2026", "[a]b#c/d?e", "with space", "colon:inside", "100%sure"])
def test_password_with_special_characters_is_kept_exactly(password: str) -> None:
    settings = Settings(database_url=f"postgresql://postgres.ref:{password}@{HOST}")

    url = make_url(settings.database_url)
    assert url.username == "postgres.ref"
    assert url.password == password
    assert url.host == "aws-1-ap-south-1.pooler.supabase.com"
    assert url.port == 5432


def test_already_escaped_password_is_not_escaped_twice() -> None:
    settings = Settings(database_url=f"postgresql://postgres.ref:p%40ss@{HOST}")

    assert make_url(settings.database_url).password == "p@ss"


def test_quotes_and_spaces_around_the_value_are_ignored() -> None:
    settings = Settings(database_url=f'  "postgresql://postgres.ref:secret@{HOST}"  ')

    assert settings.database_url == f"postgresql+asyncpg://postgres.ref:secret@{HOST}"


@pytest.mark.parametrize(
    "bad",
    [
        f"DATABASE_URL=postgresql://postgres.ref:secret@{HOST}",
        f"[postgresql://postgres.ref:secret@{HOST}]",
        f"mysql://user:secret@{HOST}",
        "not a url",
    ],
)
def test_malformed_value_gives_clear_error_without_the_password(bad: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(database_url=bad)

    message = str(error.value)
    assert "must be a single line starting with postgresql://" in message
    assert "secret" not in message


def test_empty_database_url_means_no_database() -> None:
    assert Settings(database_url="").database_url is None
