"""
Representative — наш представитель в Испании.

У нас несколько представителей с NIE и сертификатом ЭЦП. Они подают заявки
от имени клиента в UGE.

Минимум на старте: Анастасия Коренева. Возможно ещё несколько.

Команда добавляет / редактирует / отключает представителей через админку.
"""

from typing import Optional

from sqlmodel import SQLModel, Field

from ._base import TimestampMixin


class Representative(TimestampMixin, table=True):
    __tablename__ = "representative"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identity (Spanish system uses Latin)
    first_name: str = Field(max_length=64)
    last_name: str = Field(max_length=64)

    # Spanish ID — NIE for foreigners, DNI for Spanish nationals
    nie: str = Field(
        max_length=16, index=True,
        description="NIE/DNI number, e.g. 'Z3751311Q'",
    )

    # Contacts
    email: str = Field(max_length=128)
    phone: str = Field(max_length=32, description="With country code, e.g. '+34 661 853 441'")

    # Address in Spain
    address_street: str = Field(max_length=256)
    address_number: str = Field(max_length=16)
    address_floor: Optional[str] = Field(default=None, max_length=16)
    address_zip: str = Field(max_length=8)
    address_city: str = Field(max_length=64)
    address_province: str = Field(max_length=64)

    # Optional notes (e.g. "preferred for Catalonia submissions")
    notes: Optional[str] = Field(default=None, max_length=512)

    is_active: bool = Field(default=True)


# === API schemas ===

class RepresentativeCreate(SQLModel):
    first_name: str
    last_name: str
    nie: str
    email: str
    phone: str
    address_street: str
    address_number: str
    address_floor: Optional[str] = None
    address_zip: str
    address_city: str
    address_province: str
    notes: Optional[str] = None


class RepresentativeUpdate(SQLModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nie: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_street: Optional[str] = None
    address_number: Optional[str] = None
    address_floor: Optional[str] = None
    address_zip: Optional[str] = None
    address_city: Optional[str] = None
    address_province: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class RepresentativeRead(SQLModel):
    id: int
    first_name: str
    last_name: str
    nie: str
    email: str
    phone: str
    address_street: str
    address_number: str
    address_floor: Optional[str]
    address_zip: str
    address_city: str
    address_province: str
    notes: Optional[str]
    is_active: bool

    # Computed
    application_count: Optional[int] = None
    full_name: Optional[str] = None  # convenience: f"{first_name} {last_name}"
