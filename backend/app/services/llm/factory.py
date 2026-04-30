"""Factory — возвращает LLM-клиент в зависимости от LLM_PROVIDER."""

import logging
import os
from functools import lru_cache

from .base import LLMClient

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """
    Возвращает singleton LLM-клиент.

    Читает из env:
    - LLM_PROVIDER ("openrouter" / "anthropic", default = "openrouter")
    - OPENROUTER_API_KEY (если openrouter)
    - OPENROUTER_MODEL (default model)
    - LLM_VISION_MODEL (vision model)
    - ANTHROPIC_API_KEY (если anthropic)
    """
    provider = (os.environ.get("LLM_PROVIDER") or "openrouter").lower()

    vision_model = os.environ.get("LLM_VISION_MODEL")

    if provider == "anthropic":
        from .anthropic_direct import AnthropicDirectClient
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set (LLM_PROVIDER=anthropic requires it)"
            )
        default_model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20251201")
        log.info(f"LLM client: Anthropic Direct (default={default_model})")
        return AnthropicDirectClient(
            api_key=api_key,
            default_model=default_model,
            default_vision_model=vision_model or default_model,
        )

    # default: OpenRouter
    from .openrouter import OpenRouterClient
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set (LLM_PROVIDER=openrouter requires it)"
        )
    default_model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
    log.info(f"LLM client: OpenRouter (default={default_model})")
    return OpenRouterClient(
        api_key=api_key,
        default_model=default_model,
        default_vision_model=vision_model or default_model,
    )
