"""Abstract base for LLM clients (OpenRouter / Anthropic Direct)."""

from abc import ABC, abstractmethod
from typing import Optional


class LLMClient(ABC):
    """
    Единый интерфейс для всех LLM-клиентов.

    Все методы async — потому что под капотом сетевой запрос.
    """

    @abstractmethod
    async def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """
        Текстовый запрос к LLM.
        Возвращает строку с ответом.
        """
        ...

    @abstractmethod
    async def complete_vision(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        image_media_type: str,
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        """
        Vision-запрос к LLM (с приложенным изображением).

        image_media_type: "image/jpeg", "image/png", "image/webp"

        Возвращает строку с ответом.
        """
        ...
