"""
Private file storage for uploaded AR sheets, EOB documents and report files. Files are only ever read back
through the API, after a permission check. Development keeps them in a local folder; deployed copies use a
private Supabase Storage bucket, reached with the service-role key that only the API holds.
"""

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from app.core.config import get_settings


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class SupabaseStorage:
    """A private Supabase Storage bucket, through its REST API (no extra library needed)."""

    def __init__(self, url: str, key: str, bucket: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.key = key
        self.bucket = bucket

    def _call(
        self, method: str, path: str, body: bytes | None = None, content_type: str | None = None
    ) -> bytes:
        headers = {"Authorization": f"Bearer {self.key}", "apikey": self.key}
        if content_type:
            headers["Content-Type"] = content_type
        if method == "POST":
            headers["x-upsert"] = "true"
        request = urllib.request.Request(f"{self.base}/{path}", data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https endpoint
                return response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Supabase Storage {method} failed with status {error.code}") from error

    def _object(self, key: str) -> str:
        if ".." in key.split("/"):
            raise ValueError("Invalid storage key")
        return f"object/{quote(self.bucket)}/{quote(key, safe='/')}"

    def save(self, key: str, data: bytes) -> None:
        self._call("POST", self._object(key), data, "application/octet-stream")

    def read(self, key: str) -> bytes:
        return self._call("GET", self._object(key))

    def delete(self, key: str) -> None:
        body = json.dumps({"prefixes": [key]}).encode()
        self._call("DELETE", f"object/{quote(self.bucket)}", body, "application/json")


def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "supabase":
        return SupabaseStorage(
            settings.supabase_url, settings.supabase_service_role_key, settings.storage_bucket
        )
    return LocalStorage(settings.local_storage_dir)
