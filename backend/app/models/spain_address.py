"""
SpainAddress — типовой адрес в Испании, по которому подаётся заявка.

У вас несколько адресов: квартиры представителей, офисы, съёмные адреса
для подачи. Менеджер выбирает один из них при распределении заявки.

Каждый адрес связан с провинцией → определяет UGE/Делегацию для подачи.
"""

from typing import Optional

from sqlmodel import SQLModel, Field

from ._base import TimestampMixin


class SpainAddress(TimestampMixin, table=True):
    __tablename__ = "spain_address"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Address fields (used in MI-T, designación, etc)
    street: str = Field(max_length=256, description="'CARRER DEL BALMES'")
    number: str = Field(max_length=16, description="House number, '128'")
    floor: Optional[str] = Field(default=None, max_length=16, description="'3-2'")
    zip: str = Field(max_length=8, description="Spanish postal code, '08008'")
    city: str = Field(max_length=64, description="'BARCELONA'")
    province: str = Field(max_length=64, description="'BARCELONA' or 'CATALUÑA'")

    # Submission routing — which UGE this address falls under
    uge_office: str = Field(
        max_length=64,
        description="UGE office/region: 'Cataluña', 'Madrid', 'Andalucía' etc.",
    )

    # Friendly label for picker in admin (e.g. "Балмес, Барселона (квартира)")
    label: str = Field(max_length=128)

    # Optional notes (e.g. "арендована до 2027", "адрес представителя Анны")
    notes: Optional[str] = Field(default=None, max_length=512)

    is_active: bool = Field(default=True)


# === API schemas ===

class SpainAddressCreate(SQLModel):
    street: str
    number: str
    floor: Optional[str] = None
    zip: str
    city: str
    province: str
    uge_office: str
    label: str
    notes: Optional[str] = None


class SpainAddressUpdate(SQLModel):
    street: Optional[str] = None
    number: Optional[str] = None
    floor: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    uge_office: Optional[str] = None
    label: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class SpainAddressRead(SQLModel):
    id: int
    street: str
    number: str
    floor: Optional[str]
    zip: str
    city: str
    province: str
    uge_office: str
    label: str
    notes: Optional[str]
    is_active: bool

    # Computed
    application_count: Optional[int] = None
