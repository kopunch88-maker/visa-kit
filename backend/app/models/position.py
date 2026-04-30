"""
Position — типовая должность в одной из наших компаний.
"""

from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON

from ._base import TimestampMixin

if TYPE_CHECKING:
    from .company import Company


class Position(TimestampMixin, table=True):
    __tablename__ = "position"

    id: Optional[int] = Field(default=None, primary_key=True)

    company_id: int = Field(foreign_key="company.id", index=True)

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
        description="'ingeniero topógrafo (gabinete)'",
    )

    # Duties — long list, used in contract / acts / employer letter
    duties: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of duties/services performed. Order preserved.",
    )

    # Compensation
    salary_rub_default: Decimal = Field(
        max_digits=12, decimal_places=2,
        description="Default monthly salary in RUB",
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

    # Relationships
    company: "Company" = Relationship(back_populates="positions")


# === API schemas ===

class PositionCreate(SQLModel):
    company_id: int
    title_ru: str
    title_ru_genitive: Optional[str] = None
    title_es: str
    duties: List[str]
    salary_rub_default: Decimal
    tags: List[str] = Field(default_factory=list)
    profile_description: str = ""


class PositionUpdate(SQLModel):
    title_ru: Optional[str] = None
    title_ru_genitive: Optional[str] = None
    title_es: Optional[str] = None
    duties: Optional[List[str]] = None
    salary_rub_default: Optional[Decimal] = None
    tags: Optional[List[str]] = None
    profile_description: Optional[str] = None
    is_active: Optional[bool] = None


class PositionRead(SQLModel):
    id: int
    company_id: int
    title_ru: str
    title_ru_genitive: Optional[str]
    title_es: str
    duties: List[str]
    salary_rub_default: Decimal
    tags: List[str]
    profile_description: str
    is_active: bool

    application_count: Optional[int] = None
    company_short_name: Optional[str] = None
