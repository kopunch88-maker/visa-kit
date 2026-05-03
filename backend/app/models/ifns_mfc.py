"""
Pack 18.0 — справочники ИФНС и МФЦ для генерации справки КНД 1122035.

Модели:
- IfnsOffice: налоговая инспекция / УФНС постановки на учёт по НПД
  Привязка: region_code (1:N — на регион может быть несколько ИФНС / обособленных
  подразделений в крупных регионах вроде Москвы/Подмосковья).
  Используется в: КНД 1122035 (поле «Наименование налогового органа»).

- MfcOffice: многофункциональный центр выдачи бумажной справки
  Привязка: region_code (1:N).
  staff_names — JSON-массив реальных русских ФИО уполномоченных сотрудников.
  При генерации справки: random.choice(staff_names).
  Используется в: КНД 1122035 (поле «МФЦ + ФИО сотрудника»).

ВАЖНО: ИФНС берётся по РЕГИОНУ АДРЕСА самозанятого (а не по первым 4 цифрам ИНН),
потому что в КНД 1122035 указывается ИФНС по месту постановки на учёт по НПД,
которая привязана к месту жительства (где живёт сейчас), а не к месту получения
ИНН (которое могло быть в другом регионе много лет назад).
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
    
    Примеры:
        - "УФНС России по г. Москве"
        - "Межрайонная ИФНС России №7 по Краснодарскому краю"
        - "УФНС России по Калужской области, обособленное подразделение в г. Малоярославец №1"
    
    code (4 цифры) — официальный код налогового органа в системе ФНС.
    Соответствует первым 4 цифрам ИНН тех ИП, которые этой ИФНС зарегистрированы.
    Не используется для матчинга с конкретным кандидатом — только для отображения
    в шаблоне справки и для админки.
    """
    __tablename__ = "ifns_office"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Код налогового органа (4 цифры, например "7728", "2367", "4028")
    # Не PK потому что в одном регионе может быть выбран один из нескольких
    # ИФНС — мы берём первый по region_code
    code: str = Field(max_length=4, index=True)

    # Регион (код субъекта РФ, 2 цифры) — для матчинга с region_code
    # из self_employed_registry / адреса заявителя
    region_code: int = Field(index=True)

    # Полное название (печатается в справке КНД 1122035)
    full_name: str = Field(max_length=500)

    # Краткое название (для UI/admin)
    short_name: str = Field(max_length=200)

    # Адрес ИФНС (для расширенного отображения в админке, не печатается в КНД 1122035)
    address: Optional[str] = Field(default=None, max_length=500)

    # Признак "по умолчанию для региона" — если в регионе несколько ИФНС,
    # берём ту что is_default=True (одна на регион). Для seed используем именно её.
    is_default: bool = Field(default=False)

    # Активность — отключённую ИФНС не выдаём
    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MfcOffice(SQLModel, table=True):
    """
    Многофункциональный центр выдачи справок.
    
    Примеры (Москва):
        - "МФЦ района Хамовники" (ЦАО)
        - "МФЦ района Чертаново Северное" (ЮАО)
    
    staff_names — массив реальных русских ФИО (Им.п. → пишем как «Иванов Иван Иванович»),
    для каждой генерации справки выбирается случайный.
    """
    __tablename__ = "mfc_office"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Регион (код субъекта РФ, 2 цифры)
    region_code: int = Field(index=True)

    # Город (для UI группировки и для поля «Адрес МФЦ»)
    city: str = Field(max_length=100)

    # Название МФЦ
    name: str = Field(max_length=300)

    # Полный адрес МФЦ (печатается в КНД 1122035)
    address: str = Field(max_length=500)

    # Массив ФИО сотрудников (JSON)
    # Пример: ["Иваничкина Ольга Николаевна", "Соколова Анна Дмитриевна", ...]
    staff_names: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )

    # Активность
    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
