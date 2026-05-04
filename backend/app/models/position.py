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
