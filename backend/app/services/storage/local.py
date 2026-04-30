"""Local filesystem storage — для разработки и опционально для production без R2."""

from pathlib import Path
from typing import Optional

from .base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _full_path(self, key: str) -> Path:
        # Защита от path traversal: запрещаем .. и абсолютные пути
        key = key.replace("\\", "/")
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError(f"Invalid storage key: {key}")
        return self.root / key

    def save(self, key: str, content: bytes, content_type: Optional[str] = None) -> str:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return key

    def read(self, key: str) -> bytes:
        path = self._full_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Not found: {key}")
        with open(path, "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        path = self._full_path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._full_path(key).exists()

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        # Для local возвращаем относительный путь к API endpoint
        # (нужно будет добавить endpoint /api/storage/{key} если используется)
        return f"/api/storage/{key}"
