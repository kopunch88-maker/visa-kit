"""
LLM service — универсальный клиент для работы с LLM.

Поддерживает 2 провайдера:
- "openrouter" — через OpenRouter (доступ к Claude/GPT/Gemini одним ключом)
- "anthropic" — напрямую через Anthropic API

Переключение через env-переменную LLM_PROVIDER.

Использование:
    from app.services.llm import get_llm_client

    client = get_llm_client()

    # Текстовый запрос (для рекомендаций)
    response = await client.complete(
        system="You are HR assistant",
        user="Analyze this candidate...",
        model="anthropic/claude-haiku-4-5",
    )

    # Vision запрос (для OCR)
    response = await client.complete_vision(
        system="Extract passport data",
        user="See attached passport scan",
        image_bytes=image_data,
        image_media_type="image/jpeg",
        model="anthropic/claude-sonnet-4-5",
    )
"""

from .base import LLMClient
from .factory import get_llm_client

__all__ = ["LLMClient", "get_llm_client"]
