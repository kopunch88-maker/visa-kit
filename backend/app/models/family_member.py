"""
FamilyMember — член семьи главного заявителя.

В ~20% подач на digital nomad визу подаются семьями. На каждого члена семьи
нужен свой комплект документов:
- MI-F анкета (вместо MI-T у главного)
- Паспорт
- Designación de representante
- Tasa 038
- Certificado bancario (что главный его содержит)

Главный заявитель дополнительно подаёт DECLARACION JURADA DE MANTENIMIENTO.

В админке — это под-карточки внутри одной заявки, которые рендерятся как
суб-пакет внутри основного.
"""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship

from ._base import TimestampMixin, CountryCode

if TYPE_CHECKING:
    from .application import Application


class FamilyMember(TimestampMixin, table=True):
    __tablename__ = "family_member"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    relation: str = Field(
        max_length=16,
        description="'spouse', 'child', 'parent' — defines required documents",
    )

    # Names
    last_name_native: str = Field(max_length=64)
    first_name_native: str = Field(max_length=64)
    middle_name_native: Optional[str] = Field(default=None, max_length=64)
    last_name_latin: str = Field(max_length=64)
    first_name_latin: str = Field(max_length=64)

    # Demographics
    birth_date: date
    birth_place_latin: str = Field(max_length=128)
    nationality: CountryCode = Field(max_length=3)
    sex: str = Field(max_length=1, regex="^[HM]$")

    # Passport
    passport_number: str = Field(max_length=32)
    passport_issue_date: Optional[date] = Field(default=None)
    passport_expiry_date: Optional[date] = Field(default=None)

    # Children: school/age info — sometimes required by UGE
    is_minor: bool = Field(
        default=False,
        description="True for children under 18 — different document requirements",
    )

    # Relationships
    application: "Application" = Relationship(back_populates="family_members")


# === API schemas ===

class FamilyMemberCreate(SQLModel):
    relation: str
    last_name_native: str
    first_name_native: str
    middle_name_native: Optional[str] = None
    last_name_latin: str
    first_name_latin: str
    birth_date: date
    birth_place_latin: str
    nationality: CountryCode
    sex: str
    passport_number: str
    passport_issue_date: Optional[date] = None
    passport_expiry_date: Optional[date] = None
    is_minor: bool = False


class FamilyMemberRead(FamilyMemberCreate):
    id: int
    application_id: int


class FamilyMemberUpdate(SQLModel):
    relation: Optional[str] = None
    last_name_native: Optional[str] = None
    first_name_native: Optional[str] = None
    middle_name_native: Optional[str] = None
    last_name_latin: Optional[str] = None
    first_name_latin: Optional[str] = None
    birth_date: Optional[date] = None
    birth_place_latin: Optional[str] = None
    nationality: Optional[CountryCode] = None
    sex: Optional[str] = None
    passport_number: Optional[str] = None
    passport_issue_date: Optional[date] = None
    passport_expiry_date: Optional[date] = None
    is_minor: Optional[bool] = None
