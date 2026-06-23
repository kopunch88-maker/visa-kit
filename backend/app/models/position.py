"""
Position — типовая должность (Pack 20.0: отвязана от Company).

Pack 20.0 (04.05.2026):
- Убрано поле company_id и relationship company.
  Position теперь шаблон должности, переиспользуемый между разными
  компаниями. Связь Position↔Company идёт через Application
  (application.company_id + application.position_id, оба независимо).
- Добавлено primary_specialty_id (FK на specialty.id, nullable) — указывает
  на ОКСО-специальность к которой эта должность относится. Используется
  work_history_generator (Pack 20.3) для подбора шаблона под
  applicant.education[-1].specialty.
- Добавлено level (1=Junior, 2=Middle, 3=Senior, 4=Lead) для построения
  карьерной лестницы.
"""

from decimal import Decimal
from typing import Optional, List

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON

from ._base import TimestampMixin


class Position(TimestampMixin, table=True):
    __tablename__ = "position"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identity
    title_ru: str = Field(
        max_length=128,
        description="Именительный падеж: 'инженер-геодезист (камеральщик)'",
    )
    title_ru_genitive: Optional[str] = Field(
        default=None, max_length=128,
        description="Родительный падеж для договоров и актов: 'инженера-геодезиста (камеральщика)'",
    )
    title_es: str = Field(
        max_length=128,
        description="'ingeniero topografo (gabinete)'",
    )

    # Duties — long list, used in contract / acts / employer letter
    duties: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of duties/services performed. Order preserved.",
    )

    # Compensation — average market salary for this position level.
    # Real salary in a specific application overrides this via Application.salary_rub.
    salary_rub_default: Decimal = Field(
        max_digits=12, decimal_places=2,
        description="Default monthly salary in RUB (market average for level)",
    )

    # Pack 20.0: classification — specialty + level
    primary_specialty_id: Optional[int] = Field(
        default=None,
        foreign_key="specialty.id",
        index=True,
        description="ОКСО-специальность (FK на specialty.id). Используется "
                    "work_history_generator для подбора по applicant.education.",
    )
    level: Optional[int] = Field(
        default=None,
        description="Уровень должности: 1=Junior, 2=Middle, 3=Senior, 4=Lead",
    )

    # Tags for LLM recommendation engine
    tags: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    # Free-form description used by LLM to match candidates
    profile_description: str = Field(
        default="",
        max_length=2048,
    )

    is_active: bool = Field(default=True)

    # === Pack 40.0: Tech Opinion (Техническое заключение) ===
    international_analog_ru: Optional[str] = Field(
        default=None, max_length=255,
        description="Международный аналог должности (для §1 заключения): 'quantity surveyor'",
    )
    international_analog_es: Optional[str] = Field(
        default=None, max_length=255,
        description="Международный аналог на испанском: 'quantity surveyor'",
    )
    tech_opinion_description_ru: Optional[str] = Field(
        default=None,
        description="§1 — длинное описание деятельности (RU)",
    )
    tech_opinion_description_es: Optional[str] = Field(
        default=None,
        description="§1 — длинное описание деятельности (ES)",
    )
    tech_opinion_tools_ru: Optional[List[dict]] = Field(
        default=None, sa_column=Column(JSON),
        description="§2 — список инструментов: [{name, purpose}, ...] (RU)",
    )
    tech_opinion_tools_es: Optional[List[dict]] = Field(
        default=None, sa_column=Column(JSON),
        description="§2 — список инструментов (ES)",
    )
    tech_opinion_steps_ru: Optional[List[dict]] = Field(
        default=None, sa_column=Column(JSON),
        description="§3 — пошаговое описание процесса: [{title, body}, ...] (RU)",
    )
    tech_opinion_steps_es: Optional[List[dict]] = Field(
        default=None, sa_column=Column(JSON),
        description="§3 — пошаговое описание процесса (ES)",
    )
    tech_opinion_grounds_ru: Optional[List[str]] = Field(
        default=None, sa_column=Column(JSON),
        description="§4 — основания, по которым физическое присутствие не требуется (RU)",
    )
    tech_opinion_grounds_es: Optional[List[str]] = Field(
        default=None, sa_column=Column(JSON),
        description="§4 — основания (ES)",
    )
    tech_opinion_contract_clause_ru: Optional[str] = Field(
        default=None,
        description="§4 — цитата из договора о дистанционном характере (RU)",
    )
    tech_opinion_contract_clause_es: Optional[str] = Field(
        default=None,
        description="§4 — цитата из договора (ES)",
    )

    # Pack CV-AUTO — поля для генерации блоков «Дополнительная информация»,
    # «Сертификаты» и «Интересы» в CV. Заполняются LLM при создании позиции,
    # выбираются в шаблон детерминированно по applicant.id.
    cv_skills_summary_ru: Optional[str] = Field(
        default=None,
        description="CV-AUTO: 1-3 предложения о ключевых навыках и инструментах "
                    "должности (Agile/Scrum, Jira, SQL и т.п.). Вставляется в "
                    "«Дополнительную информацию» CV для всех заявителей с этой "
                    "позицией.",
    )
    cv_hobbies_pool_ru: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="CV-AUTO: пул из 6 хобби, подходящих для DN-нарратива "
                    "(путешествия, языки, спорт, культура). В каждое CV "
                    "выбираются 3 элемента детерминированно по applicant.id.",
    )
    cv_certificates_pool: Optional[List[dict]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="CV-AUTO: пул из 6 правдоподобных сертификатов: "
                    "[{name, issuer, year_offset}, ...]. year_offset — "
                    "смещение от года выпуска вуза (0..3). В CV "
                    "выбираются 2 сертификата детерминированно по applicant.id.",
    )

    # Pack 50.7-A — цель командировки для Приказа Т-9 (найм)
    # Текст для блока "с целью..." в приказе. Генерируется LLM при создании
    # должности, может правиться вручную в админке.
    business_trip_purpose: Optional[str] = Field(
        default=None,
        description="Цель командировки (Т-9, найм). Текст до 2048 символов.",
    )
    # Pack 50.9-A — Справка СТД-Р: код функции по ОКЗ (Общероссийский
    # классификатор занятий, например '2631.5' для Бизнес-аналитика).
    okz_code: Optional[str] = Field(
        default=None,
        max_length=10,
        description="Код по ОКЗ (пример: '2631.5') — для §3 справки СТД-Р",
    )


# === API schemas ===

class PositionCreate(SQLModel):
    title_ru: str
    title_ru_genitive: Optional[str] = None
    title_es: str
    duties: List[str]
    salary_rub_default: Decimal
    primary_specialty_id: Optional[int] = None  # Pack 20.0
    level: Optional[int] = None                 # Pack 20.0
    tags: List[str] = Field(default_factory=list)
    profile_description: str = ""
    # Pack 40.0: tech_opinion
    international_analog_ru: Optional[str] = None
    international_analog_es: Optional[str] = None
    tech_opinion_description_ru: Optional[str] = None
    tech_opinion_description_es: Optional[str] = None
    tech_opinion_tools_ru: Optional[List[dict]] = None
    tech_opinion_tools_es: Optional[List[dict]] = None
    tech_opinion_steps_ru: Optional[List[dict]] = None
    tech_opinion_steps_es: Optional[List[dict]] = None
    tech_opinion_grounds_ru: Optional[List[str]] = None
    tech_opinion_grounds_es: Optional[List[str]] = None
    tech_opinion_contract_clause_ru: Optional[str] = None
    tech_opinion_contract_clause_es: Optional[str] = None
    # Pack 50.7-A — цель командировки
    business_trip_purpose: Optional[str] = None
    # Pack 50.9-A — код ОКЗ для СТД-Р
    okz_code: Optional[str] = None
    # Pack CV-AUTO — поля для CV
    cv_skills_summary_ru: Optional[str] = None
    cv_hobbies_pool_ru: Optional[List[str]] = None
    cv_certificates_pool: Optional[List[dict]] = None


class PositionUpdate(SQLModel):
    title_ru: Optional[str] = None
    title_ru_genitive: Optional[str] = None
    title_es: Optional[str] = None
    duties: Optional[List[str]] = None
    salary_rub_default: Optional[Decimal] = None
    primary_specialty_id: Optional[int] = None  # Pack 20.0
    level: Optional[int] = None                 # Pack 20.0
    tags: Optional[List[str]] = None
    profile_description: Optional[str] = None
    is_active: Optional[bool] = None
    # Pack 40.0: tech_opinion
    international_analog_ru: Optional[str] = None
    international_analog_es: Optional[str] = None
    tech_opinion_description_ru: Optional[str] = None
    tech_opinion_description_es: Optional[str] = None
    tech_opinion_tools_ru: Optional[List[dict]] = None
    tech_opinion_tools_es: Optional[List[dict]] = None
    tech_opinion_steps_ru: Optional[List[dict]] = None
    tech_opinion_steps_es: Optional[List[dict]] = None
    tech_opinion_grounds_ru: Optional[List[str]] = None
    tech_opinion_grounds_es: Optional[List[str]] = None
    tech_opinion_contract_clause_ru: Optional[str] = None
    tech_opinion_contract_clause_es: Optional[str] = None
    # Pack 50.7-A — цель командировки
    business_trip_purpose: Optional[str] = None
    # Pack 50.9-A — код ОКЗ для СТД-Р
    okz_code: Optional[str] = None


class PositionRead(SQLModel):
    id: int
    title_ru: str
    title_ru_genitive: Optional[str]
    title_es: str
    duties: List[str]
    salary_rub_default: Decimal
    primary_specialty_id: Optional[int] = None  # Pack 20.0
    level: Optional[int] = None                 # Pack 20.0
    tags: List[str]
    profile_description: str
    is_active: bool

    application_count: Optional[int] = None
    # Pack 40.0: tech_opinion
    international_analog_ru: Optional[str] = None
    international_analog_es: Optional[str] = None
    tech_opinion_description_ru: Optional[str] = None
    tech_opinion_description_es: Optional[str] = None
    tech_opinion_tools_ru: Optional[List[dict]] = None
    tech_opinion_tools_es: Optional[List[dict]] = None
    tech_opinion_steps_ru: Optional[List[dict]] = None
    tech_opinion_steps_es: Optional[List[dict]] = None
    tech_opinion_grounds_ru: Optional[List[str]] = None
    tech_opinion_grounds_es: Optional[List[str]] = None
    tech_opinion_contract_clause_ru: Optional[str] = None
    tech_opinion_contract_clause_es: Optional[str] = None
    # Pack 50.7-A — цель командировки
    business_trip_purpose: Optional[str] = None
    # Pack 50.9-A — код ОКЗ для СТД-Р
    okz_code: Optional[str] = None
