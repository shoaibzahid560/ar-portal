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


def test_deployed_copies_need_persistent_storage_and_a_real_domain_in_production() -> None:
    with pytest.raises(ValueError, match="STORAGE_BACKEND=supabase"):
        Settings(app_env="staging", allowed_google_domain="*")
    demo = Settings(
        app_env="staging",
        allowed_google_domain="*",
        storage_backend="supabase",
        supabase_url="https://abcd.supabase.co",
        supabase_service_role_key="secret",
    )
    assert demo.company_domain is None  # any verified Google account may try; only registered people get in
    with pytest.raises(ValueError, match="company Google domain"):
        Settings(
            app_env="production",
            allowed_google_domain="*",
            storage_backend="supabase",
            supabase_url="https://abcd.supabase.co",
            supabase_service_role_key="secret",
        )


def test_supabase_storage_calls_the_private_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import storage

    calls = []

    class Reply:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"file-bytes"

    def fake_urlopen(request: object, timeout: int) -> Reply:
        calls.append((request.get_method(), request.full_url, request.get_header("Authorization")))
        return Reply()

    monkeypatch.setattr(storage.urllib.request, "urlopen", fake_urlopen)
    bucket = storage.SupabaseStorage("https://abcd.supabase.co/", "service-key", "ar-portal-files")
    bucket.save("uploads/p1/u1/My Sheet.xlsx", b"data")
    assert bucket.read("uploads/p1/u1/My Sheet.xlsx") == b"file-bytes"
    bucket.delete("exports/e1/report.pdf")

    assert calls[0] == (
        "POST",
        "https://abcd.supabase.co/storage/v1/object/ar-portal-files/uploads/p1/u1/My%20Sheet.xlsx",
        "Bearer service-key",
    )
    assert calls[1][0] == "GET" and calls[2][:2] == (
        "DELETE",
        "https://abcd.supabase.co/storage/v1/object/ar-portal-files",
    )
    with pytest.raises(ValueError):
        bucket.read("../secrets")
