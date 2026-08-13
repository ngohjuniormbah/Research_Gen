"""Storage abstraction. Local filesystem in dev; the interface leaves room for an
S3/MinIO backend without touching callers."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import Settings


class StorageBackend(ABC):
    @abstractmethod
    async def put(self, data: bytes, *, filename: str) -> str:
        """Store bytes and return an opaque storage key."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Fetch bytes for a previously stored key."""

    @abstractmethod
    async def delete(self, key: str) -> None: ...


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys are relative; guard against traversal.
        p = (self._base / key).resolve()
        if not str(p).startswith(str(self._base.resolve())):
            raise ValueError("invalid storage key")
        return p

    async def put(self, data: bytes, *, filename: str) -> str:
        safe = Path(filename).name or "upload"
        key = f"{uuid.uuid4().hex}_{safe}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


def build_storage(settings: Settings) -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalStorage(settings.storage_local_dir)
    raise ValueError(f"unsupported storage backend: {settings.storage_backend}")
