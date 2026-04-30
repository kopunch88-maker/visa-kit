"""
Anthropic Direct LLM client — через официальный anthropic Python SDK.

Используется когда LLM_PROVIDER=anthropic.
"""

import logging
from typing import Optional

from anthropic import AsyncAnthropic

from .base import LLMClient

log = logging.getLogger(__name__)


class AnthropicDirectClient(LLMClient):
    """Клиент для Anthropic API напрямую."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-5-20251201",
        default_vision_model: Optional[str] = None,
    ):
        self.client = AsyncAnthropic(api_key=api_key)
        self.default_model = default_model
        self.default_vision_model = default_vision_model or default_model

    async def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        response = await self.client.messages.create(
            model=model or self.default_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

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
        import base64
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        response = await self.client.messages.create(
            model=model or self.default_vision_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": image_media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": user},
                    ],
                }
            ],
        )
        return response.content[0].text
