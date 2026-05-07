"""
NpdCandidate — пул чистых самозанятых, верифицированных через rmsp-pp + EGRUL + NPD.

Pack 28 (07.05.2026): отдельная таблица для НОВОЙ архитектуры выдачи ИНН.

ИСТОРИЯ — почему отдельная таблица, а не SelfEmployedRegistry:

  - SelfEmployedRegistry заполнялась из открытого дампа SNRIP ФНС
    (https://www.nalog.gov.ru/opendata/7707329152-snrip/).
    Pack 28-разведка (07.05.2026) показала что в этом дампе содержатся
    ТОЛЬКО ИП. Их ИНН гуглятся → засветка фамилии → провал легенды.

  - НОВЫЙ источник: rmsp-pp.nalog.ru (Реестр МСП-получателей поддержки)
    с фильтром sk=SZ. Содержит чистых физиков-самозанятых.

  - Но даже после фильтра sk=SZ часть ИНН (40-75% в Москве) уже
    открыли ИП ПОСЛЕ получения поддержки. Их нужно отсеивать через
    EGRUL и npd.nalog.ru.

  - Чтобы не ломать существующий код и оставить Юкселя (заявка 2026-0003)
    нетронутым → Pack 28 пишет в новую таблицу. SelfEmployedRegistry
    остаётся для legacy.

ЖИЗНЕННЫЙ ЦИКЛ КАНДИДАТА:
  1. CLI/cron вызывает npd_pool.refill_pool_for_region(region_code)
  2. Скрипт идёт в rmsp-pp.nalog.ru, набирает 50-100 кандидатов
  3. Для каждого: EGRUL-проверка (отсев ИП), затем NPD-проверка статуса
  4. Чистые попадают сюда со статусом 'verified' и реальной registration_date
  5. inn-suggest endpoint выдаёт verified-кандидата → ставит status='allocated'
     (бронь на 30 минут пока менеджер думает)
  6. inn-accept подтверждает → status='used', used_by_applicant_id

СТАТУСЫ:
  pending             — только что вытащен из rmsp-pp, ещё не верифицирован
  rejected_ip         — найден в EGRUL (открыл ИП) — НЕ выдаём
  rejected_inactive   — на сегодня status=False по NPD (снят с учёта) — НЕ выдаём
  rejected_other      — другая ошибка верификации (для аудита)
  verified            — прошёл все проверки, готов к выдаче
  allocated           — выбран для applicant'а, бронь до allocated_until
  used                — выдан, applicant.inn = candidate.inn

Дата registration_date — РЕАЛЬНАЯ дата постановки на учёт по НПД из ФНС API
(npd.nalog.ru/api/v1/tracker/taxpayer_status). Идёт прямо в справку КНД 1122035.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class NpdCandidate(SQLModel, table=True):
    """
    Чистый самозанятый из rmsp-pp, прошедший верификацию.

    Таблица отдельная от self_employed_registry — см. docstring модуля.
    """

    __tablename__ = "npd_candidate"

    inn: str = Field(primary_key=True, max_length=12)

    region_code: str = Field(max_length=2, index=True)
    full_name: Optional[str] = Field(default=None, max_length=255)

    rmsp_pp_id: Optional[int] = Field(default=None)
    rmsp_pp_support_date: Optional[date] = Field(default=None)

    status: str = Field(default="pending", max_length=24, index=True)

    egrul_found: Optional[bool] = Field(default=None)
    egrul_checked_at: Optional[datetime] = Field(default=None)

    npd_active: Optional[bool] = Field(default=None)
    npd_checked_at: Optional[datetime] = Field(default=None)

    # ГЛАВНОЕ ПОЛЕ: реальная дата постановки на учёт по НПД
    registration_date: Optional[date] = Field(default=None)

    fetched_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    verified_at: Optional[datetime] = Field(default=None)
    rejection_reason: Optional[str] = Field(default=None, max_length=512)

    allocated_until: Optional[datetime] = Field(default=None)

    used_by_applicant_id: Optional[int] = Field(default=None, index=True)
    used_at: Optional[datetime] = Field(default=None)


# === Pydantic-схемы (без table=True) ===


class NpdPoolStats(SQLModel):
    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_region_verified: dict[str, int] = Field(default_factory=dict)
    last_refill_at: Optional[datetime] = None
    last_refill_region: Optional[str] = None


class NpdPoolRefillResult(SQLModel):
    region_code: str
    rmsp_fetched: int = 0
    egrul_rejected: int = 0
    npd_rejected: int = 0
    verified_added: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0
