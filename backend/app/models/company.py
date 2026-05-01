"""
Company — наше юридическое лицо (заказчик услуг).

На старте в системе ~8 компаний (СК10, BUKI VEDI, ProTechnologies и т.д.).
Один раз создаём — переиспользуем во всех заявках.

Большинство компаний российские, но бывают и казахстанские (TIKOmpani) и др.

Pack 15.1: добавлено поле director_full_name_latin — для подстановки в
переводы (jurada-черновики) до отправки в LLM.
"""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship

from ._base import TimestampMixin, CountryCode

if TYPE_CHECKING:
    from .position import Position


class Company(TimestampMixin, table=True):
    __tablename__ = "company"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identity
    short_name: str = Field(max_length=64, index=True, description="Краткое: 'СК10'")
    full_name_ru: str = Field(max_length=256, description="Юр. название на русском")
    full_name_es: str = Field(max_length=256, description="Транслитерация для исп. документов")

    # Jurisdiction
    country: CountryCode = Field(
        max_length=3,
        default="RUS",
        description="ISO-3 country code where company is registered",
    )

    # Tax IDs (formats vary by country; we don't validate strictly)
    tax_id_primary: str = Field(
        max_length=20,
        description="Primary tax ID: ИНН for RU, БИН for KZ etc",
    )
    tax_id_secondary: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Secondary tax ID: КПП for RU companies, null for others",
    )

    # Addresses — free-form strings, no parsing
    legal_address: str = Field(max_length=512)
    postal_address: Optional[str] = Field(default=None, max_length=512)

    # Те же адреса, но разбитые на 2 строки — для шаблонов с переносами
    legal_address_line1: Optional[str] = Field(default=None, max_length=256)
    legal_address_line2: Optional[str] = Field(default=None, max_length=256)
    postal_address_line1: Optional[str] = Field(default=None, max_length=256)
    postal_address_line2: Optional[str] = Field(default=None, max_length=256)

    # Director (used in contract and other docs)
    director_full_name_ru: str = Field(
        max_length=128,
        description="Full name in Russian, e.g. 'Тараскин Юрий Александрович'",
    )
    director_full_name_genitive_ru: str = Field(
        max_length=128,
        description="Genitive case for contract header: 'Тараскина Юрия Александровича'",
    )
    director_short_ru: str = Field(
        max_length=64,
        description="Short for signature: 'Тараскин Ю.А.'",
    )
    director_position_ru: str = Field(
        default="Генерального директора",
        max_length=64,
    )
    # Pack 15.1
    director_full_name_latin: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Latin form for translations: 'Tarakin Yury Aleksandrovich'. "
                    "If empty, GOST transliteration is used as fallback.",
    )

    # Banking — primary account used for receiving payments under contracts
    bank_name: str = Field(max_length=128)
    bank_account: str = Field(max_length=32)
    bank_bic: str = Field(max_length=16)
    bank_correspondent_account: Optional[str] = Field(default=None, max_length=32)

    # EGRYL excerpt (for RU companies) — date of latest fresh extract
    # System warns when older than 30 days
    egryl_extract_date: Optional[date] = Field(
        default=None,
        description="Date of latest EGRYL extract on file. Used to warn about expiry.",
    )

    # Status — soft delete instead of hard delete
    is_active: bool = Field(default=True, description="Inactive companies hidden from new applications")
    notes: Optional[str] = Field(default=None, max_length=2048, description="Internal notes for the team")

    # Relationships
    positions: list["Position"] = Relationship(back_populates="company")


# === API schemas ===

class CompanyCreate(SQLModel):
    """Payload for POST /api/companies"""
    short_name: str
    full_name_ru: str
    full_name_es: str
    country: CountryCode = "RUS"
    tax_id_primary: str
    tax_id_secondary: Optional[str] = None
    legal_address: str
    postal_address: Optional[str] = None
    director_full_name_ru: str
    director_full_name_genitive_ru: str
    director_short_ru: str
    director_position_ru: str = "Генерального директора"
    director_full_name_latin: Optional[str] = None  # Pack 15.1
    bank_name: str
    bank_account: str
    bank_bic: str
    bank_correspondent_account: Optional[str] = None
    egryl_extract_date: Optional[date] = None
    notes: Optional[str] = None


class CompanyUpdate(SQLModel):
    """Payload for PATCH /api/companies/{id}. All fields optional."""
    short_name: Optional[str] = None
    full_name_ru: Optional[str] = None
    full_name_es: Optional[str] = None
    country: Optional[CountryCode] = None
    tax_id_primary: Optional[str] = None
    tax_id_secondary: Optional[str] = None
    legal_address: Optional[str] = None
    postal_address: Optional[str] = None
    director_full_name_ru: Optional[str] = None
    director_full_name_genitive_ru: Optional[str] = None
    director_short_ru: Optional[str] = None
    director_position_ru: Optional[str] = None
    director_full_name_latin: Optional[str] = None  # Pack 15.1
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_bic: Optional[str] = None
    bank_correspondent_account: Optional[str] = None
    egryl_extract_date: Optional[date] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class CompanyRead(SQLModel):
    """Response for GET /api/companies/{id} and list endpoints"""
    id: int
    short_name: str
    full_name_ru: str
    full_name_es: str
    country: CountryCode
    tax_id_primary: str
    tax_id_secondary: Optional[str]
    legal_address: str
    postal_address: Optional[str]
    director_full_name_ru: str
    director_full_name_genitive_ru: str
    director_short_ru: str
    director_position_ru: str
    director_full_name_latin: Optional[str] = None  # Pack 15.1
    bank_name: str
    bank_account: str
    bank_bic: str
    bank_correspondent_account: Optional[str]
    egryl_extract_date: Optional[date]
    is_active: bool
    notes: Optional[str]
    created_at: "datetime"  # forward ref to avoid circular
    updated_at: "datetime"

    # Computed fields for admin UI
    egryl_is_fresh: Optional[bool] = Field(
        default=None,
        description="True if EGRYL extract is younger than 30 days. None if no date on file.",
    )
    application_count: Optional[int] = Field(
        default=None,
        description="How many applications used this company (filled by query, not stored)",
    )


from datetime import datetime  # noqa: E402  (resolves forward ref above)
