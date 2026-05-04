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

Pack 16: добавлено поле bank_id (FK на Bank). Существующие поля bank_name/bic
остаются для обратной совместимости и денормализации (могут быть пустыми, если
выбран bank_id — тогда реквизиты берутся из связанного банка).
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
    # Pack 18.10: страна рождения (отдельно от гражданства). ISO-3 код.
    # Если NULL — render_mi_t / render_designacion подставляют nationality
    # как fallback (обратная совместимость для legacy applicant'ов).
    birth_country: Optional[CountryCode] = Field(
        default=None,
        max_length=3,
        description="ISO-3 страна рождения. Может отличаться от nationality "
                    "(человек родился в одной стране, гражданство другой).",
    )
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

    # Pack 17: автогенерация ИНН самозанятого через rmsp-pp.nalog.ru
    inn_registration_date: Optional[date] = Field(
        default=None,
        description="Дата регистрации ИНН как самозанятого (НПД). "
                    "Берётся через NPD API при автогенерации либо вручную.",
    )
    inn_source: Optional[str] = Field(
        default=None, max_length=32,
        description="'auto-generated' если ИНН подобран через rmsp-pp, "
                    "'manual' если введён руками. Используется для аудита.",
    )
    inn_kladr_code: Optional[str] = Field(
        default=None, max_length=13,
        description="13-значный KLADR код региона из которого взят ИНН. "
                    "Используется для отслеживания распределения по регионам.",
    )

    # Pack 18.9: подписант апостиля. Все 3 поля — переопределение дефолта
    # «Байрамов Н.А.» / стандартная должность. Если пустые — используется
    # дефолт. Менеджер может задать другого подписанта в UI ApplicantDrawer.
    apostille_signer_short: Optional[str] = Field(
        default=None, max_length=100,
        description="Pack 18.9: 'Фамилия И.О.' для таблицы апостиля. "
                    "Если пусто — дефолт 'Байрамов Н.А.'",
    )
    apostille_signer_signature: Optional[str] = Field(
        default=None, max_length=100,
        description="Pack 18.9: 'И.О. Фамилия' для подписи внизу апостиля. "
                    "Если пусто — дефолт 'Н.А. Байрамов'",
    )
    apostille_signer_position: Optional[str] = Field(
        default=None, max_length=500,
        description="Pack 18.9: должность подписанта апостиля. "
                    "Если пусто — дефолт 'Заместитель начальника отдела ...'",
    )

    # === Personal banking ===
    # Pack 16: bank_id — FK на справочник банков (новый способ).
    # Старые поля bank_name/bic/correspondent_account остаются для обратной
    # совместимости — заполняются автоматически из Bank при сохранении в drawer
    # (или вручную если bank_id не выбран).
    bank_id: Optional[int] = Field(
        default=None,
        foreign_key="bank.id",
        index=True,
        description="Pack 16: FK на справочник банков. None если используются legacy поля ниже.",
    )
    bank_account: Optional[str] = Field(
        default=None, max_length=32, index=True,
        description="20-значный расчётный счёт клиента. Pack 16 проверяет уникальность при генерации.",
    )
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
    Pack 11: все поля кроме имён теперь Optional.
    Pack 16: добавлены bank_id + банковские поля.
    """
    last_name_native: str
    first_name_native: str
    middle_name_native: Optional[str] = None
    last_name_latin: str
    first_name_latin: str
    birth_date: Optional[date] = None
    birth_place_latin: Optional[str] = None
    birth_country: Optional[CountryCode] = None  # Pack 18.10
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
    # Pack 17: INN auto-generation
    inn_registration_date: Optional[date] = None
    inn_source: Optional[str] = None
    inn_kladr_code: Optional[str] = None
    # Pack 16: banking
    bank_id: Optional[int] = None
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None
    bank_bic: Optional[str] = None
    bank_correspondent_account: Optional[str] = None
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
    birth_country: Optional[CountryCode] = None  # Pack 18.10
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
    # Pack 17: INN auto-generation
    inn_registration_date: Optional[date] = None
    inn_source: Optional[str] = None
    inn_kladr_code: Optional[str] = None
    # Pack 18.9: подписант апостиля (опциональное переопределение дефолта)
    apostille_signer_short: Optional[str] = None
    apostille_signer_signature: Optional[str] = None
    apostille_signer_position: Optional[str] = None
    # Pack 16: banking
    bank_id: Optional[int] = None
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None
    bank_bic: Optional[str] = None
    bank_correspondent_account: Optional[str] = None
    home_address: Optional[str] = None
    home_country: Optional[CountryCode] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    education: Optional[List[EducationRecord]] = None
    work_history: Optional[List[WorkRecord]] = None
    languages: Optional[List[str]] = None



