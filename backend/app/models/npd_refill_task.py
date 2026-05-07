"""
NpdRefillTask — задача пополнения пула самозанятых с прогрессом.

Pack 28 Часть 2 (07.05.2026): нужна для отслеживания прогресса refill'ов:
- Ленивый refill при пустом регионе (зовётся из inn-suggest)
- Глобальный refill (кнопка "Обновить весь пул" или GitHub Actions cron)

Жизненный цикл:
  1. Endpoint создаёт запись со status='pending'
  2. BackgroundTask стартует → status='running', обновляет progress_*
  3. По окончании → status='done' (с result_inn если ленивый refill) или 'failed'

Frontend поллит GET /admin/npd-pool/tasks/{id} раз в 3 секунды.

ПОЛЯ result_inn / result_region_code заполняются ТОЛЬКО для ленивых refill'ов
которые стартанул inn-suggest. После окончания такого task'а endpoint
inn-suggest (фронтовый поллер) забирает один verified кандидат из пула
обычным путём — а result_inn используется как hint что задача успешна.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class NpdRefillTask(SQLModel, table=True):
    """
    Задача пополнения пула.

    kind:
      'lazy_region'   — ленивый refill одного региона из inn-suggest
      'global'        — глобальный refill всех ключевых регионов (кнопка/cron)
      'revalidate'    — только ревалидация существующих verified (часть global)

    status:
      'pending'  — создана, ещё не стартовала
      'running'  — выполняется
      'done'     — успешно завершена
      'failed'   — ошибка (см. error)
      'cancelled'— пока не используется, заложено на будущее
    """

    __tablename__ = "npd_refill_task"

    id: Optional[int] = Field(default=None, primary_key=True)

    kind: str = Field(max_length=24, index=True)
    status: str = Field(default="pending", max_length=16, index=True)

    # Для lazy_region — конкретный регион. Для global — None.
    region_code: Optional[str] = Field(default=None, max_length=2, index=True)

    # Прогресс — обновляется в processе. Для UI прогресс-бара.
    progress_text: Optional[str] = Field(default=None, max_length=255)
    progress_current: int = Field(default=0)
    progress_total: int = Field(default=0)

    # Hint что искать после окончания. Для lazy_region — ИНН первого verified
    # (фронт может его сразу взять), для global — None.
    result_inn: Optional[str] = Field(default=None, max_length=12)
    result_region_code: Optional[str] = Field(default=None, max_length=2)

    # Сводная статистика после окончания (для UI и логов)
    verified_added: int = Field(default=0)
    egrul_rejected: int = Field(default=0)
    npd_rejected: int = Field(default=0)
    revalidated_total: int = Field(default=0)
    revalidated_invalidated: int = Field(default=0)

    error: Optional[str] = Field(default=None, max_length=1024)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)

    # Кто инициировал (manager_id или 'cron'/'github_actions')
    triggered_by: Optional[str] = Field(default=None, max_length=64)
