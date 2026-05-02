"""
Pack 17: Регион РФ — справочник используемый для генерации ИНН
самозанятого и адреса при заполнении анкеты заявителя.

Источник кодов KLADR: https://kladr-rf.ru/ (открытый классификатор адресов России).
KLADR-код = 13 цифр (регион 2 + район 3 + город 3 + ... + 00 в конце).

Связи с заявителями:
- Applicant.inn_kladr_code — KLADR региона из которого взят ИНН
- Region.diaspora_for_countries — JSON список ISO-3 стран для которых
  регион считается «диаспорой» (предлагается приоритетнее в автогенерации)
"""

from typing import Optional, List
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON

from ._base import TimestampMixin


class Region(TimestampMixin, table=True):
    __tablename__ = "region"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === Идентификация ===
    kladr_code: str = Field(
        max_length=13, unique=True, index=True,
        description="13-значный KLADR код. Например '7700000000000' = Москва, "
                    "'2300000700000' = г.о. Сочи."
    )
    # Двухзначный код субъекта РФ (первые 2 цифры KLADR)
    region_code: str = Field(
        max_length=2, index=True,
        description="'77'=Москва, '78'=СПб, '23'=Краснодарский край, и т.д."
    )

    # === Названия ===
    name: str = Field(
        max_length=128,
        description="Короткое имя для UI: 'Сочи', 'Москва', 'Краснодар'"
    )
    name_full: str = Field(
        max_length=256,
        description="Полное имя: 'Краснодарский край, городской округ Сочи'"
    )
    type: str = Field(
        max_length=32, default="city",
        description="Тип: 'city', 'region', 'district' — для будущих фильтров в UI"
    )

    # === Использование в pipeline ===
    is_active: bool = Field(
        default=True,
        description="Если False — регион не предлагается в автогенерации"
    )

    diaspora_for_countries: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="ISO-3 коды стран для которых этот регион — 'диаспора'. "
                    "Например ['TUR'] для Сочи (в Сочи много турецкой диаспоры). "
                    "Пустой список = регион доступен но не приоритетен."
    )

    notes: Optional[str] = Field(
        default=None, max_length=512,
        description="Свободные заметки менеджера (пример: 'избегать с октября по март')"
    )


# === API схемы ===

class RegionCreate(SQLModel):
    kladr_code: str
    region_code: str
    name: str
    name_full: str
    type: str = "city"
    is_active: bool = True
    diaspora_for_countries: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class RegionRead(RegionCreate):
    id: int


class RegionUpdate(SQLModel):
    kladr_code: Optional[str] = None
    region_code: Optional[str] = None
    name: Optional[str] = None
    name_full: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None
    diaspora_for_countries: Optional[List[str]] = None
    notes: Optional[str] = None
