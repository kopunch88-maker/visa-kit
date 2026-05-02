"""
Pack 16 — Bank model.

Справочник банков для клиентов. Сейчас один банк (Альфа-Банк) — реквизиты
взяты из реальных выписок клиентов в /Подано/.

В будущем добавятся новые банки и для каждого будет свой шаблон выписки
(bank_statement_template_<bik>.docx). Выбор шаблона — по applicant.bank_id.

Pack 16 — только справочник + поля у Applicant. Шаблон выписки пока один,
жёстко под Альфа-Банк.
"""

from typing import Optional

from sqlmodel import SQLModel, Field

from ._base import TimestampMixin


class Bank(TimestampMixin, table=True):
    __tablename__ = "bank"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identity
    name: str = Field(max_length=128, index=True, description="«АО АЛЬФА-БАНК»")
    short_name: Optional[str] = Field(default=None, max_length=64, description="«Альфа-Банк»")

    # Bank-specific tax IDs
    bik: str = Field(max_length=9, index=True, description="БИК банка, ровно 9 цифр")
    inn: str = Field(max_length=12, description="ИНН банка")
    kpp: Optional[str] = Field(default=None, max_length=9, description="КПП банка")

    # Banking
    correspondent_account: str = Field(
        max_length=20,
        description="Корреспондентский счёт банка (к/с), 20 цифр",
    )
    swift: Optional[str] = Field(default=None, max_length=11, description="SWIFT/BIC код")

    # Contacts
    address: Optional[str] = Field(default=None, max_length=512)
    phone: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=128)
    website: Optional[str] = Field(default=None, max_length=128)

    # Status
    is_active: bool = Field(default=True)
    notes: Optional[str] = Field(default=None, max_length=2048)


# === API schemas ===

class BankCreate(SQLModel):
    name: str
    short_name: Optional[str] = None
    bik: str
    inn: str
    kpp: Optional[str] = None
    correspondent_account: str
    swift: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None


class BankUpdate(SQLModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    bik: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    correspondent_account: Optional[str] = None
    swift: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class BankRead(SQLModel):
    id: int
    name: str
    short_name: Optional[str]
    bik: str
    inn: str
    kpp: Optional[str]
    correspondent_account: str
    swift: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    website: Optional[str]
    is_active: bool
    notes: Optional[str]
    # Computed
    applicant_count: Optional[int] = Field(
        default=None,
        description="Сколько клиентов используют этот банк (filled by query)",
    )
