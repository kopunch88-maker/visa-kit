"""
Applicant — заявитель на визу.

Это данные, которые вводит сам клиент через анкету.

Поддерживает не только россиян: гражданство — обязательное поле, ИНН и
адрес в РФ — опциональные.

Связан с Application 1:N (теоретически один человек может подавать несколько раз —
например, если первый отказ).
"""

from datetime import date
from typing import Optional, List, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON

from ._base import TimestampMixin, CountryCode

if TYPE_CHECKING:
    from .application import Application


class Applicant(TimestampMixin, table=True):
    __tablename__ = "applicant"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === Names ===
    # Russian/native form (used in RU contracts, acts, banking docs)
    last_name_native: str = Field(max_length=64, description="Фамилия в родной форме")
    first_name_native: str = Field(max_length=64)
    middle_name_native: Optional[str] = Field(
        default=None, max_length=64,
        description="Отчество, если есть",
    )

    # Latin form as it appears in passport
    # Used in Spanish forms (MI-T, designación), and as primary identity for Spain
    last_name_latin: str = Field(max_length=64, description="ALIYEV (uppercase as in passport)")
    first_name_latin: str = Field(max_length=64, description="JAFAR")

    # === Demographics ===
    birth_date: date
    birth_place_latin: str = Field(max_length=128, description="'BAKU' for Spanish forms")
    nationality: CountryCode = Field(
        max_length=3,
        index=True,
        description="ISO-3 code: RUS, AZE, KAZ, BLR, UKR, ARM, MKD etc.",
    )

    # Spanish form expects single letter
    sex: str = Field(max_length=1, regex="^[HM]$", description="H=male (Hombre), M=female (Mujer)")

    # Marital status as expected by Spanish forms: S/C/V/D/Sp/Uh
    marital_status: str = Field(
        max_length=2, default="S",
        description="S=Soltero, C=Casado, V=Viudo, D=Divorciado, Sp=Separado, Uh=Unión hecho",
    )

    # Parents' names — required by some Spanish forms (designación)
    father_name_latin: Optional[str] = Field(default=None, max_length=64)
    mother_name_latin: Optional[str] = Field(default=None, max_length=64)

    # === Documents ===
    passport_number: str = Field(max_length=32, description="No regex — varies by country")
    passport_issue_date: Optional[date] = Field(default=None)
    passport_expiry_date: Optional[date] = Field(default=None)
    passport_issuer: Optional[str] = Field(default=None, max_length=128)

    # Russian INN — only for RU citizens, optional otherwise
    inn: Optional[str] = Field(default=None, max_length=12)
# === Personal banking (для договоров где клиент сам — получатель оплаты) ===
    bank_account: Optional[str] = Field(default=None, max_length=32)
    bank_name: Optional[str] = Field(default=None, max_length=128)
    bank_bic: Optional[str] = Field(default=None, max_length=16)
    bank_correspondent_account: Optional[str] = Field(default=None, max_length=32)

    # === Адрес — разбит на 2 строки для удобства использования в шаблонах ===
    # home_address (ниже) — full address as one string for forms
    # home_address_line1/line2 — for templates that need newlines
    home_address_line1: Optional[str] = Field(default=None, max_length=256)
    home_address_line2: Optional[str] = Field(default=None, max_length=256)
    # === Addresses ===
    home_address: str = Field(
        max_length=512,
        description="Free-form address of permanent residence, any country",
    )
    home_country: CountryCode = Field(
        max_length=3,
        description="Country of current residence (often equals nationality but not always)",
    )

    # === Contacts ===
    email: str = Field(max_length=128, index=True)
    phone: str = Field(max_length=32, description="With country code, e.g. '+7 999 ...' or '+34 ...'")

    # === Education and work ===
    # Stored as JSON — these are lists with sub-fields
    # See structure in `app/services/applicant_helpers.py`
    education: List[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description=(
            "[{institution, graduation_year, degree, specialty}]. "
            "Used in CV. Order: most recent first."
        ),
    )
    work_history: List[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description=(
            "[{period_start, period_end, company, position, duties: [...]}]. "
            "Order: most recent first. Used in CV."
        ),
    )
    languages: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Free-form list: ['Russian native', 'English B1']",
    )

    # === Relationships ===
    applications: list["Application"] = Relationship(back_populates="applicant")


# === API schemas ===

class EducationRecord(SQLModel):
    institution: str
    graduation_year: int
    degree: str
    specialty: str


class WorkRecord(SQLModel):
    period_start: str = Field(description="Free-form: 'Сентябрь 2025' or '09/2025'")
    period_end: str = Field(description="Free-form: 'по настоящее время' or '08/2025'")
    company: str
    position: str
    duties: List[str] = Field(default_factory=list)


class ApplicantCreate(SQLModel):
    last_name_native: str
    first_name_native: str
    middle_name_native: Optional[str] = None
    last_name_latin: str
    first_name_latin: str
    birth_date: date
    birth_place_latin: str
    nationality: CountryCode
    sex: str
    marital_status: str = "S"
    father_name_latin: Optional[str] = None
    mother_name_latin: Optional[str] = None
    passport_number: str
    passport_issue_date: Optional[date] = None
    passport_expiry_date: Optional[date] = None
    passport_issuer: Optional[str] = None
    inn: Optional[str] = None
    home_address: str
    home_country: CountryCode
    email: str
    phone: str
    education: List[EducationRecord] = Field(default_factory=list)
    work_history: List[WorkRecord] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)


class ApplicantRead(ApplicantCreate):
    id: int

    # Computed convenience fields
    full_name_native: Optional[str] = Field(default=None, description="'Алиев Джафар Надирович'")
    initials_native: Optional[str] = Field(default=None, description="'Алиев Д.Н.'")


# Update payload — all fields optional
class ApplicantUpdate(SQLModel):
    last_name_native: Optional[str] = None
    first_name_native: Optional[str] = None
    middle_name_native: Optional[str] = None
    last_name_latin: Optional[str] = None
    first_name_latin: Optional[str] = None
    birth_date: Optional[date] = None
    birth_place_latin: Optional[str] = None
    nationality: Optional[CountryCode] = None
    sex: Optional[str] = None
    marital_status: Optional[str] = None
    father_name_latin: Optional[str] = None
    mother_name_latin: Optional[str] = None
    passport_number: Optional[str] = None
    passport_issue_date: Optional[date] = None
    passport_expiry_date: Optional[date] = None
    passport_issuer: Optional[str] = None
    inn: Optional[str] = None
    home_address: Optional[str] = None
    home_country: Optional[CountryCode] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    education: Optional[List[EducationRecord]] = None
    work_history: Optional[List[WorkRecord]] = None
    languages: Optional[List[str]] = None
