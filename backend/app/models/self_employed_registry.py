"""
SelfEmployedRegistry — локальная БД самозанятых из открытого дампа ФНС.

Pack 17.2.4: вместо live-парсинга rmsp-pp.nalog.ru качаем раз в месяц
открытый дамп ФНС (https://www.nalog.gov.ru/opendata/7707329152-rsmppp/),
парсим XML стримом, сохраняем сюда. Поиск идёт по индексам в этой таблице
вместо HTTP-запросов к ФНС.

Источник: data-YYYYMMDD-structure-20230615.zip (~5 ГБ распакованный XML)
Обновляется ФНС 15-го числа каждого месяца.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlmodel import SQLModel, Field


class SelfEmployedRegistry(SQLModel, table=True):
    """
    Запись о самозанятом из реестра МСП-ПП.

    PK = inn (12 цифр для физлиц / самозанятых).
    Таблица денормализована намеренно — это staging-данные для быстрого поиска,
    SQL-индексы делают запросы мгновенными.
    """

    __tablename__ = "self_employed_registry"

    # Основной ключ — ИНН самозанятого
    inn: str = Field(primary_key=True, max_length=12, index=True)

    # Регион для (опциональной) фильтрации в будущем
    region_code: Optional[str] = Field(default=None, max_length=2, index=True)

    # ФИО из реестра — для логов и проверки в Яндексе на «не светится ли»
    # (само ФИО мы клиенту не подставляем — у нас своё)
    full_name: Optional[str] = Field(default=None, max_length=255)

    # Дата начала поддержки — нижняя граница даты регистрации НПД
    support_begin_date: Optional[date] = Field(default=None)

    # Дата создания записи в реестре (dt_create из XML)
    registry_create_date: Optional[date] = Field(default=None)

    # Когда мы импортировали эту запись (для очистки старых импортов)
    imported_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Использован ли этот ИНН для какого-то заявителя
    is_used: bool = Field(default=False, index=True)

    # Кому именно выдан (FK на applicant) — soft FK, без cascade
    used_by_applicant_id: Optional[int] = Field(default=None)

    # Когда выдан
    used_at: Optional[datetime] = Field(default=None)


class RegistryImportLog(SQLModel, table=True):
    """История импортов дампа ФНС — для админки и отладки."""

    __tablename__ = "registry_import_log"

    id: Optional[int] = Field(default=None, primary_key=True)

    # URL дампа (https://file.nalog.ru/opendata/...)
    dump_url: str = Field(max_length=512)

    # Дата дампа из имени файла (data-YYYYMMDD)
    dump_date: Optional[date] = Field(default=None)

    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = Field(default=None)

    # 'running' / 'success' / 'failed'
    status: str = Field(default="running", max_length=16)

    # Статистика парсинга
    records_total: int = Field(default=0)         # всего записей в XML
    records_imported: int = Field(default=0)      # сохранено в БД (только самозанятые)
    records_skipped: int = Field(default=0)       # отброшено (ИП, не НПД, дубли и т.д.)

    # Размеры файлов для диагностики
    zip_size_bytes: Optional[int] = Field(default=None)
    xml_size_bytes: Optional[int] = Field(default=None)

    error_message: Optional[str] = Field(default=None, max_length=2048)


# === Pydantic схемы для API ===

class SelfEmployedRegistryStats(SQLModel):
    """Статистика для админ-эндпоинта /registry/import-status."""
    total_records: int
    available_records: int       # is_used=False
    used_records: int            # is_used=True
    last_import_date: Optional[datetime]
    last_import_status: Optional[str]
    last_import_dump_date: Optional[date]


class RegistryImportLogRead(SQLModel):
    id: int
    dump_url: str
    dump_date: Optional[date]
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    records_total: int
    records_imported: int
    records_skipped: int
    zip_size_bytes: Optional[int]
    xml_size_bytes: Optional[int]
    error_message: Optional[str]


class StartImportRequest(SQLModel):
    """Запрос на старт импорта."""
    dump_url: Optional[str] = None  # если None — берём latest с портала ФНС
    purge_old: bool = True           # удалить старые записи перед импортом
