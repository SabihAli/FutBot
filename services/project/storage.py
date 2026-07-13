import io
import os
from typing import Protocol

from services.project.config import settings

_store: dict[str, bytes] = {}


class StorageBackend(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...


class MemoryStorage:
    def put(self, key: str, data: bytes, content_type: str) -> None:
        _store[key] = data


class MinioStorage:
    def __init__(self) -> None:
        from minio import Minio

        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not self._client.bucket_exists(settings.minio_bucket):
            self._client.make_bucket(settings.minio_bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            settings.minio_bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if os.getenv("STORAGE_BACKEND") == "memory":
        return MemoryStorage()
    if _backend is None:
        _backend = MinioStorage()
    return _backend


def reset_storage_for_tests() -> None:
    global _backend
    _store.clear()
    _backend = None
    os.environ["STORAGE_BACKEND"] = "memory"
