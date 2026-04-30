"""
App configuration — все настройки через ENV переменные.

В разработке — берёт из .env файла в backend/
В production (Railway) — из переменных окружения проекта.

Pack 11: добавлены настройки для R2 и production.
"""

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === Database ===
    # Local dev: sqlite:///./dev.db
    # Production: postgresql://user:pass@host:5432/dbname
    database_url: str = "sqlite:///./dev.db"

    # === Frontend URL (для CORS и magic-link) ===
    frontend_url: str = "http://localhost:3000"

    # === JWT secret ===
    # КРИТИЧНО: в production обязательно сгенерировать новый secret
    # python -c "import secrets; print(secrets.token_urlsafe(64))"
    jwt_secret: str = "dev-secret-change-in-production-please"
    secret_key: str = "dev-secret-change-in-production-please"  # alias

    # === Storage backend ===
    storage_backend: Literal["local", "r2"] = "local"
    storage_path: Path = Path("storage")

    # === Cloudflare R2 (если storage_backend = "r2") ===
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket_name: Optional[str] = None

    # === Anthropic API ===
    anthropic_api_key: Optional[str] = None

    # === Templates path (Pack 11: можно переопределить через ENV) ===
    # По умолчанию ищет в visa_kit/templates/ (на уровень выше backend/)
    templates_path: Optional[Path] = None

    @property
    def is_production(self) -> bool:
        return self.database_url.startswith("postgresql://") or self.database_url.startswith("postgres://")


settings = Settings()
