"""
Pack 19.0 — справочник вузов и специальностей для автогенерации образования.

Цель: Когда клиент не указал ВУЗ в анкете, менеджер нажимает кнопку ✨ в
ApplicantDrawer → бэкенд подбирает подходящий вуз по:
  1. Региону клиента (из applicant.inn_kladr_code → first 2 chars = region_code)
  2. Должности из последнего work_history → специальность через
     PositionSpecialtyMap regex-маппинг
  3. Возрасту клиента → год выпуска (22 года + случайный 0-5 стажа)

Структура:
  - Specialty — справочник ОКСО (08.03.01 Строительство, и т.д.)
  - University — справочник вузов с привязкой к региону
  - UniversitySpecialtyLink — many-to-many (какие специальности преподают)
  - PositionSpecialtyMap — маппинг паттернов должностей на специальности
    (например "инженер.*проектировщик" → 08.03.01 Строительство)
"""

from typing import Optional, List, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship

from ._base import TimestampMixin


# === Many-to-many таблица University × Specialty ===

class UniversitySpecialtyLink(SQLModel, table=True):
    __tablename__ = "university_specialty_link"

    university_id: Optional[int] = Field(
        default=None, foreign_key="university.id", primary_key=True,
    )
    specialty_id: Optional[int] = Field(
        default=None, foreign_key="specialty.id", primary_key=True,
    )


# === Specialty — справочник ОКСО ===

class Specialty(TimestampMixin, table=True):
    __tablename__ = "specialty"

    id: Optional[int] = Field(default=None, primary_key=True)

    code: str = Field(
        max_length=10, unique=True, index=True,
        description="Код ОКСО, например '08.03.01' (Строительство, бакалавр) "
                    "или '09.04.04' (Программная инженерия, магистр)",
    )
    name: str = Field(
        max_length=256,
        description="Название специальности: 'Строительство', "
                    "'Информатика и вычислительная техника'",
    )
    level: str = Field(
        max_length=32, default="bachelor",
        description="Уровень: 'bachelor' (бакалавр), 'specialist' (специалист), "
                    "'master' (магистр). По коду ОКСО можно вычислить, "
                    "но храним явно для удобства фильтрации.",
    )

    # Какие вузы её преподают
    universities: List["University"] = Relationship(
        back_populates="specialties",
        link_model=UniversitySpecialtyLink,
    )


# === University — справочник вузов ===

class University(TimestampMixin, table=True):
    __tablename__ = "university"

    id: Optional[int] = Field(default=None, primary_key=True)

    region_code: str = Field(
        max_length=2, index=True,
        description="2-зн код субъекта РФ (как в Region.region_code). "
                    "Например '77'=Москва, '78'=СПб, '23'=Краснодарский край.",
    )
    city: str = Field(
        max_length=128,
        description="Город где находится вуз. Например 'Москва', 'Санкт-Петербург'.",
    )

    name_full: str = Field(
        max_length=512,
        description="Полное официальное название вуза, как в дипломе. "
                    "Например 'Федеральное государственное бюджетное "
                    "образовательное учреждение высшего образования "
                    "«Московский государственный технический университет "
                    "имени Н.Э. Баумана»'",
    )
    name_short: str = Field(
        max_length=128,
        description="Аббревиатура для UI: 'МГТУ им. Баумана', 'СПбГУ', 'НИУ ВШЭ'",
    )

    founding_year: Optional[int] = Field(
        default=None,
        description="Год основания. Используется для проверки правдоподобности "
                    "graduation_year (вуз должен быть основан раньше).",
    )

    is_active: bool = Field(
        default=True,
        description="Если False — вуз не предлагается генератором",
    )

    # Какие специальности преподаёт
    specialties: List[Specialty] = Relationship(
        back_populates="universities",
        link_model=UniversitySpecialtyLink,
    )


# === PositionSpecialtyMap — маппинг должность → специальность ===

class PositionSpecialtyMap(TimestampMixin, table=True):
    __tablename__ = "position_specialty_map"

    id: Optional[int] = Field(default=None, primary_key=True)

    position_pattern: str = Field(
        max_length=256, index=True,
        description="Lowercase подстрока для матчинга в position. "
                    "Например 'инженер-проектировщик' матчит "
                    "'Главный инженер-проектировщик AutoCAD'. "
                    "Сравнение через `pattern.lower() in position.lower()`.",
    )

    specialty_id: int = Field(
        foreign_key="specialty.id",
        description="К какой специальности относится этот паттерн.",
    )

    priority: int = Field(
        default=100,
        description="Приоритет матчинга. Чем меньше число — тем выше приоритет. "
                    "Например 'архитектор' (priority=10) должен матчиться "
                    "раньше чем 'инженер' (priority=100).",
    )

    is_active: bool = Field(
        default=True,
        description="Если False — паттерн не используется при матчинге",
    )

    # Relationship
    specialty: Optional[Specialty] = Relationship()


# === API schemas ===

class SpecialtyRead(SQLModel):
    id: int
    code: str
    name: str
    level: str


class UniversityRead(SQLModel):
    id: int
    region_code: str
    city: str
    name_full: str
    name_short: str
    founding_year: Optional[int] = None
    is_active: bool


class UniversitySuggestion(SQLModel):
    """
    Pack 19.0: результат работы generate_education() для applicant.

    Возвращается из POST /admin/applicants/{id}/regen-education.
    Frontend использует эти поля чтобы заполнить applicant.education[0]
    (структуру `EducationRecord` из applicant.py).
    """
    institution: str = Field(description="University.name_full — длинное название для CV")
    institution_short: str = Field(description="University.name_short — для UI")
    degree: str = Field(description="'Бакалавр' / 'Специалист' / 'Магистр'")
    specialty: str = Field(description="'08.03.01 Строительство'")
    graduation_year: int

    # Метаданные для отладки
    matched_pattern: Optional[str] = Field(
        default=None,
        description="Какой position_pattern совпал. Полезно для отладки.",
    )
    fallback_used: bool = Field(
        default=False,
        description="True если регион клиента не нашёлся в University, "
                    "и подобрали из Москвы как fallback.",
    )
