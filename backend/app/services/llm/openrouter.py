"""
OpenRouter LLM client — OpenAI-compatible API.

Документация: https://openrouter.ai/docs

Использует Chat Completions API (как OpenAI), просто другой base_url
и другой формат для vision (multipart content array).
"""

import base64
import logging
from typing import Optional

import httpx

from .base import LLMClient

log = logging.getLogger(__name__)


class OpenRouterClient(LLMClient):
    """Клиент для OpenRouter (https://openrouter.ai)."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        default_model: str = "anthropic/claude-sonnet-4-5",
        default_vision_model: Optional[str] = None,
        timeout: float = 60.0,
        site_url: Optional[str] = None,
        site_name: Optional[str] = None,
    ):
        self.api_key = api_key
        self.default_model = default_model
        self.default_vision_model = default_vision_model or default_model
        self.timeout = timeout
        # OpenRouter рекомендует передавать identification headers
        self.site_url = site_url or "https://visa-kit.vercel.app"
        self.site_name = site_name or "Visa Kit"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.site_name,
        }

    async def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        payload = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

        return data["choices"][0]["message"]["content"]

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
        # OpenRouter требует data URL для inline изображений
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{image_media_type};base64,{b64}"

        payload = {
            "model": model or self.default_vision_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

        return data["choices"][0]["message"]["content"]
