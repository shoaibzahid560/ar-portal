"""
Private file storage for uploaded AR sheets and EOB documents. Files are only ever read back through
the API, after a permission check. Development keeps them in a local folder; deployed environments
use a private Supabase Storage bucket (added in M0 step 7 behind this same interface).
"""

from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...


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


def get_storage() -> Storage:
    return LocalStorage(get_settings().local_storage_dir)
