"""
Applicant — заявитель на визу.

Это данные, которые вводит сам клиент через анкету.

Pack 11 fix: большинство полей сделаны Optional/nullable. Это нужно потому
что клиент сохраняет анкету **по шагам** — после каждого шага мастера часть
полей ещё не заполнена. Финальная проверка полноты делается в админке через
`business_rule_problems`, а не через NOT NULL в БД.

Обязательными остаются только имена (без них невозможно даже черновик создать)
и id. Всё остальное — Optional с default=None.

Поддерживает не только россиян: гражданство — опциональное.

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

    # === Names — единственные обязательные поля (без них даже черновик не создать) ===
    last_name_native: str = Field(max_length=64, description="Фамилия в родной форме")
    first_name_native: str = Field(max_length=64)
    middle_name_native: Optional[str] = Field(
        default=None, max_length=64,
        description="Отчество, если есть",
    )

    last_name_latin: str = Field(max_length=64, description="ALIYEV (uppercase as in passport)")
    first_name_latin: str = Field(max_length=64, description="JAFAR")

    # === Demographics — все Optional для пошагового сохранения ===
    birth_date: Optional[date] = Field(default=None)
    birth_place_latin: Optional[str] = Field(default=None, max_length=128)
    nationality: Optional[CountryCode] = Field(
        default=None,
        max_length=3,
        index=True,
        description="ISO-3 code: RUS, AZE, KAZ, BLR, UKR, ARM, MKD etc.",
    )

    sex: Optional[str] = Field(
        default=None, max_length=1,
        description="H=male (Hombre), M=female (Mujer)",
    )

    marital_status: Optional[str] = Field(
        default="S", max_length=2,
        description="S=Soltero, C=Casado, V=Viudo, D=Divorciado, Sp=Separado, Uh=Unión hecho",
    )

    father_name_latin: Optional[str] = Field(default=None, max_length=64)
    mother_name_latin: Optional[str] = Field(default=None, max_length=64)

    # === Documents ===
    passport_number: Optional[str] = Field(default=None, max_length=32)
    passport_issue_date: Optional[date] = Field(default=None)
    passport_expiry_date: Optional[date] = Field(default=None)
    passport_issuer: Optional[str] = Field(default=None, max_length=128)

    inn: Optional[str] = Field(default=None, max_length=12)

    # === Personal banking ===
    bank_account: Optional[str] = Field(default=None, max_length=32)
    bank_name: Optional[str] = Field(default=None, max_length=128)
    bank_bic: Optional[str] = Field(default=None, max_length=16)
    bank_correspondent_account: Optional[str] = Field(default=None, max_length=32)

    # === Адрес ===
    home_address_line1: Optional[str] = Field(default=None, max_length=256)
    home_address_line2: Optional[str] = Field(default=None, max_length=256)

    home_address: Optional[str] = Field(
        default=None, max_length=512,
        description="Free-form address of permanent residence, any country",
    )
    home_country: Optional[CountryCode] = Field(
        default=None, max_length=3,
        description="Country of current residence (often equals nationality)",
    )

    # === Contacts ===
    email: Optional[str] = Field(default=None, max_length=128, index=True)
    phone: Optional[str] = Field(
        default=None, max_length=32,
        description="With country code, e.g. '+7 999 ...' or '+34 ...'",
    )

    # === Education and work (JSON, default empty list) ===
    education: List[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="[{institution, graduation_year, degree, specialty}]",
    )
    work_history: List[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="[{period_start, period_end, company, position, duties: [...]}]",
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
    """
    Pack 11: все поля кроме имён теперь Optional. Это позволяет создавать
    запись по шагам мастера, не требуя всех данных сразу.
    """
    last_name_native: str
    first_name_native: str
    middle_name_native: Optional[str] = None
    last_name_latin: str
    first_name_latin: str
    birth_date: Optional[date] = None
    birth_place_latin: Optional[str] = None
    nationality: Optional[CountryCode] = None
    sex: Optional[str] = None
    marital_status: Optional[str] = "S"
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
    education: List[EducationRecord] = Field(default_factory=list)
    work_history: List[WorkRecord] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)


class ApplicantRead(ApplicantCreate):
    id: int
    full_name_native: Optional[str] = Field(default=None, description="'Алиев Джафар Надирович'")
    initials_native: Optional[str] = Field(default=None, description="'Алиев Д.Н.'")


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