"""
Storage abstraction — единый интерфейс для local FS и Cloudflare R2.

Backend выбирается через settings.storage_backend ("local" или "r2").

Использование:
    from app.services.storage import get_storage

    storage = get_storage()
    storage.save("uploads/passport_123.jpg", file_bytes)
    url = storage.get_url("uploads/passport_123.jpg")
    data = storage.read("uploads/passport_123.jpg")
"""

from .base import StorageBackend
from .factory import get_storage

__all__ = ["StorageBackend", "get_storage"]
