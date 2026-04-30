"""Factory — выбирает backend на основе settings."""

import logging
from functools import lru_cache

from app.config import settings
from .base import StorageBackend
from .local import LocalStorage

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    """
    Возвращает singleton instance нужного backend.

    settings.storage_backend = "local" → LocalStorage
    settings.storage_backend = "r2"    → R2Storage
    """
    backend = getattr(settings, "storage_backend", "local")

    if backend == "r2":
        from .r2 import R2Storage
        return R2Storage(
            account_id=settings.r2_account_id,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket_name=settings.r2_bucket_name,
        )

    # default: local
    storage_path = getattr(settings, "storage_path", None)
    if storage_path is None:
        from pathlib import Path
        storage_path = Path("storage")
    return LocalStorage(root=storage_path)
