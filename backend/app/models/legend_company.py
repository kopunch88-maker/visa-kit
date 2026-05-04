"""
Pack 19.1 — справочник компаний и должностей для генерации легенды work_history.

Цель: Когда менеджер нажимает кнопку ✨ в секции «Опыт работы» Drawer'а — генератор
подбирает правдоподобные 1-3 записи трудового стажа на основе:
  1. Регион клиента (из applicant.inn_kladr_code → first 2 chars = region_code)
  2. Специальность из applicant.education[-1] или из work_history (если уже что-то заполнено)
  3. Длительность последней работы — минимум 3.5 года (требование DN-визы)

Структура:
  - LegendCompany — справочник «фейковых» компаний для CV-легенды.
    Префикс legend_* специально чтобы НЕ путать с реальной таблицей `company`,
    которая содержит компании-наниматели для DN-визы (Application.company_id).
  - CareerTrack — career-track должностей по специальности с уровнями
    (1=Junior, 2=Middle, 3=Senior, 4=Lead).
    Используется для подбора должности в зависимости от количества записей в
    легенде (одна работа = Senior/Lead; три работы = career progression).

Связь со Specialty (Pack 19.0): обе новые таблицы FK на specialty.id.

Pack 19.1a (этот пакет): без поля duties в CareerTrack — заполним в 19.1b
после ревью CV-шаблона.
"""

from typing import Optional, List

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON

from ._base import TimestampMixin


# === LegendCompany — справочник фейковых компаний ===

class LegendCompany(TimestampMixin, table=True):
    __tablename__ = "legend_company"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Регион — для подбора компании в регионе клиента
    region_code: str = Field(
        max_length=2, index=True,
        description="2-зн код субъекта РФ (как в Region.region_code и University.region_code). "
                    "Например '77'=Москва, '78'=СПб, '23'=Краснодарский край.",
    )
    city: str = Field(
        max_length=128,
        description="Город где зарегистрирована компания. Например 'Москва', 'Санкт-Петербург'.",
    )

    # Названия
    name_full: str = Field(
        max_length=512,
        description="Полное название с организационно-правовой формой. "
                    "Например 'Общество с ограниченной ответственностью «Промстройпроект»'. "
                    "Используется в CV / резюме.",
    )
    name_short: str = Field(
        max_length=256,
        description="Аббревиатура / сокращение для UI. Например 'ООО «Промстройпроект»'.",
    )

    # Привязка к одной основной специальности (для MVP — без M2M).
    # Если потом окажется что компании имеют несколько профилей — добавим
    # LegendCompanySpecialtyLink по аналогии с UniversitySpecialtyLink.
    primary_specialty_id: int = Field(
        foreign_key="specialty.id",
        index=True,
        description="Основная специальность профиля компании. Генератор использует её "
                    "для подбора компании под specialty клиента.",
    )

    # Размер компании — пока инфа, может пригодиться для подбора уровня должности
    # (в маленькой компании реже встречаются Lead-позиции).
    size: str = Field(
        max_length=16, default="medium",
        description="Размер: 'small'/'medium'/'large'. По умолчанию 'medium'.",
    )

    is_active: bool = Field(
        default=True,
        description="Если False — не предлагается генератором.",
    )


# === CareerTrack — career-track должностей по специальности ===

class CareerTrack(TimestampMixin, table=True):
    __tablename__ = "career_track"

    id: Optional[int] = Field(default=None, primary_key=True)

    specialty_id: int = Field(
        foreign_key="specialty.id",
        index=True,
        description="К какой специальности относится этот career-track.",
    )

    level: int = Field(
        index=True,
        description="Уровень должности: 1=Junior, 2=Middle, 3=Senior, 4=Lead/Head. "
                    "Генератор подбирает должности по уровням в обратном порядке "
                    "(новейшая работа — старший level, более ранние — младше).",
    )

    title_ru: str = Field(
        max_length=128,
        description="Название должности на русском. Например 'Главный инженер проекта'.",
    )
    title_es: Optional[str] = Field(
        default=None, max_length=128,
        description="Название на испанском. Опционально — пока не используется, "
                    "оставлено для будущей поддержки переводов CV.",
    )

    # Pack 19.1a: оставляем поле duties в модели но в seed заполняем пустыми.
    # Pack 19.1b — после ревью CV-шаблона — наполним 3-5 фразами обязанностей.
    duties: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Список обязанностей для CV. В Pack 19.1a пустой — будет наполнен "
                    "в 19.1b после ревью текущего CV-шаблона.",
    )

    is_active: bool = Field(
        default=True,
        description="Если False — не предлагается генератором.",
    )


# === API schemas ===

class LegendCompanyRead(SQLModel):
    id: int
    region_code: str
    city: str
    name_full: str
    name_short: str
    primary_specialty_id: int
    size: str
    is_active: bool


class CareerTrackRead(SQLModel):
    id: int
    specialty_id: int
    level: int
    title_ru: str
    title_es: Optional[str] = None
    duties: List[str]
    is_active: bool


class WorkRecordSuggestion(SQLModel):
    """
    Pack 19.1: одна запись работы для подсунуть в applicant.work_history[].

    Возвращается из POST /admin/applicants/{id}/regen-work-history.
    Frontend получает массив таких записей (1-3 шт) и перезаписывает state'ом.
    """
    period_start: str = Field(description="Free-form: 'Сентябрь 2022' или '09/2022'")
    period_end: str = Field(description="Free-form: 'по настоящее время' или '08/2025'")
    company: str = Field(description="Полное название компании (для CV)")
    position: str = Field(description="Название должности на русском")
    duties: List[str] = Field(default_factory=list)


class WorkHistorySuggestion(SQLModel):
    """
    Pack 19.1: результат работы suggest_work_history() для applicant.

    Содержит массив записей + метаданные о fallback'е и отладочную инфу.
    """
    records: List[WorkRecordSuggestion] = Field(default_factory=list)
    fallback_used: bool = Field(
        default=False,
        description="True если для региона клиента не нашлось компаний и был использован "
                    "fallback на Москву.",
    )
    specialty_used: str = Field(
        description="'08.03.01 Строительство' — какая специальность была определена",
    )
    matched_pattern: Optional[str] = Field(
        default=None,
        description="Какой position_pattern сработал при определении specialty (для отладки)",
    )
