"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """
    Единый интерфейс для всех хранилищ.

    `key` — это путь файла относительно корня хранилища (например "uploads/123.jpg").
    """

    @abstractmethod
    def save(self, key: str, content: bytes, content_type: Optional[str] = None) -> str:
        """Сохранить файл. Возвращает key (или public URL для R2)."""
        ...

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Прочитать файл. Кидает FileNotFoundError если нет."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Удалить файл. Не кидает ошибок если файла нет."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Проверить существование."""
        ...

    @abstractmethod
    def get_upload_url(
        self,
        key: str,
        content_type: str | None = None,
        expires_in: int = 600,
    ) -> str:
        """
        Pack 32.0: вернуть presigned PUT URL для прямой загрузки файла в storage.

        Браузер шлёт PUT с телом файла напрямую (минуя FastAPI/Railway).
        - Для R2: presigned URL через generate_presigned_url("put_object", ...)
        - Для local: NotImplementedError (не используется в проде)
        """
        ...

    @abstractmethod
    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Получить URL для скачивания.

        Для local — возвращает /api/storage/<key> (через FastAPI endpoint).
        Для R2 — возвращает signed URL.
        """
        ...
