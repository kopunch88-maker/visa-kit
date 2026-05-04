"""
Pack 18.0 — справочники ИФНС и МФЦ для генерации справки КНД 1122035.

FIX 2: region_code как str (varchar(2)), не int.
Причина: коды субъектов РФ это идентификаторы с лидирующими нулями (02, 05, 09, 20),
не числа для арифметики. В self_employed_registry.region_code тоже varchar(2).
Чтобы JOIN'иться без кастингов — везде str.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class IfnsOffice(SQLModel, table=True):
    """
    ИФНС / УФНС постановки на учёт по НПД.
    """
    __tablename__ = "ifns_office"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=4, index=True)
    # Код субъекта РФ как строка из 2 символов с лидирующим нулём (02, 05, 20, 77)
    region_code: str = Field(max_length=2, index=True)
    full_name: str = Field(max_length=500)
    short_name: str = Field(max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MfcOffice(SQLModel, table=True):
    """
    Многофункциональный центр выдачи справок.
    """
    __tablename__ = "mfc_office"

    id: Optional[int] = Field(default=None, primary_key=True)
    region_code: str = Field(max_length=2, index=True)
    city: str = Field(max_length=100)
    # Pack 18.9.0: расширили с 300 до 500 — длинные названия типа
    # "Филиал Государственного бюджетного учреждения города Москвы ..."
    # не помещались в 300 символов
    name: str = Field(max_length=500)
    address: str = Field(max_length=500)
    staff_names: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    # Pack 18.9.0: если True — этот МФЦ используется для ВСЕХ клиентов,
    # независимо от их региона. Применяется в _pick_mfc().
    # Ожидается ровно одна запись с is_universal=True во всей таблице.
    # Если хочешь вернуться к региональным МФЦ — установи is_universal=False.
    is_universal: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
