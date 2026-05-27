"""
Application — заявка на визу.

Pack 10 правки:
- Добавлены поля is_archived (bool) и archived_at (datetime) для архивирования
  завершённых заявок. Скрыты из основного списка, видны на странице /admin/archive
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON

from ._base import TimestampMixin

if TYPE_CHECKING:
    from .applicant import Applicant
    from .company import Company
    from .position import Position
    from .representative import Representative
    from .spain_address import SpainAddress
    from .family_member import FamilyMember
    from .previous_residence import PreviousResidence
    from .uploaded_file import UploadedFile
    from .generated_document import GeneratedDocument


class ApplicationType(str, Enum):
    """Pack 50.0-A — тип заявки на визу.

    SELF_EMPLOYED — самозанятый по НПД (исторически основная ветка проекта,
                    рендерит акты/счета/НПД-справку/Tech Opinion).
    EMPLOYMENT    — найм по трудовому договору (Pack 50.x — расчётные листки,
                    2-НДФЛ, ЭТК, свидетельство об отъезде из СФР).
    """
    SELF_EMPLOYED = "SELF_EMPLOYED"
    EMPLOYMENT = "EMPLOYMENT"


class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_DATA = "awaiting_data"
    READY_TO_ASSIGN = "ready_to_assign"
    ASSIGNED = "assigned"
    DRAFTS_GENERATED = "drafts_generated"
    AT_TRANSLATOR = "at_translator"
    AWAITING_SCANS = "awaiting_scans"
    AWAITING_DIGITAL_SIGN = "awaiting_digital_sign"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_FOLLOWUP = "needs_followup"
    HOLD = "hold"
    CANCELLED = "cancelled"


# Финальные статусы — заявку с таким статусом можно архивировать (Pack 10)
ARCHIVABLE_STATUSES = {
    ApplicationStatus.APPROVED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.CANCELLED,
}


class TasaType(str, Enum):
    TASA_038 = "038"
    TASA_039 = "039"
    TASA_030 = "030"


class Application(TimestampMixin, table=True):
    __tablename__ = "application"

    id: Optional[int] = Field(default=None, primary_key=True)
    reference: str = Field(unique=True, index=True, max_length=16)
    # Pack 50.0-A: тип заявки (самозанятый по НПД / найм по трудовому договору)
    application_type: ApplicationType = Field(
        default=ApplicationType.SELF_EMPLOYED,
        index=True,
        max_length=16,
    )
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT, index=True)
    status_notes: Optional[str] = Field(default=None, max_length=512)
    client_access_token: str = Field(unique=True, index=True, max_length=64)
    applicant_id: Optional[int] = Field(default=None, foreign_key="applicant.id", index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)
    position_id: Optional[int] = Field(default=None, foreign_key="position.id", index=True)
    representative_id: Optional[int] = Field(default=None, foreign_key="representative.id", index=True)
    spain_address_id: Optional[int] = Field(default=None, foreign_key="spain_address.id", index=True)
    contract_number: Optional[str] = Field(default=None, max_length=32)
    contract_sign_date: Optional[date] = None
    contract_sign_city: Optional[str] = Field(default=None, max_length=64)
    contract_end_date: Optional[date] = None
    salary_rub: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    employer_letter_date: Optional[date] = None
    employer_letter_number: Optional[str] = Field(default=None, max_length=32)
    submission_date: Optional[date] = Field(default=None)
    payments_period_months: Optional[int] = Field(default=3)
    tasa_type: TasaType = Field(default=TasaType.TASA_038)
    tasa_nrc: Optional[str] = Field(default=None, max_length=64)
    recommendation_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    bank_transactions_override: Optional[list] = Field(default=None, sa_column=Column(JSON))
    eur_rate_override: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=4)
    monthly_documents_override: Optional[list] = Field(default=None, sa_column=Column(JSON))
    # === Параметры расчётов банковской выписки ===
    bank_npd_rate: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=4)
    bank_monthly_fee: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    # Pack 25.9: ручной override даты формирования банковской выписки.
    # Если NULL — генератор берёт today - random(7..10).
    # Если задано — генератор использует эту дату как statement_date,
    # период считается как [statement_date - 3мес, statement_date].
    bank_statement_date: Optional[date] = None
    bank_period_start: Optional[date] = None
    bank_period_end: Optional[date] = None
    bank_opening_balance: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    assigned_manager_id: Optional[int] = Field(default=None, foreign_key="user.id")
    internal_notes: Optional[str] = Field(default=None, max_length=4096)

    # === Pack 10: архивирование ===
    is_archived: bool = Field(default=False, index=True)
    archived_at: Optional[datetime] = Field(default=None)
    # === Pack 30.0: флаг "срочно" ===
    is_urgent: bool = Field(default=False, index=True)
    # === Pack 34.2: флаг "Готово, можно забирать" ===
    is_ready_for_pickup: bool = Field(default=False, index=True)
    is_filed: bool = Field(default=False, index=True)  # Pack 36.0
    is_paid: bool = Field(default=False, index=True)  # Pack 38.1
    # === Pack 36.1: TIE card fields ===
    nie: Optional[str] = Field(default=None, max_length=16)
    fingerprint_date: Optional[date] = None
    # Pack 27.0 — soft-delete с автоудалением через 7 дней
    deleted_at: Optional[datetime] = Field(default=None, index=True)

    # === Pack 40.0: Tech Opinion (Техническое заключение) ===
    outgoing_number: Optional[str] = Field(default=None, max_length=50, description="Исх. № документа для tech_opinion")
    outgoing_date: Optional[date] = Field(default=None, description="Дата исх. документа")
    tech_opinion_override_text: Optional[str] = Field(default=None, description="Override §1-§4 для конкретной заявки")

    # === Pack 50.7-A: Приказ Т-9 о командировке (найм) ===
    business_trip_order_number: Optional[str] = Field(default=None, max_length=16, description="№ приказа Т-9 ('37/к')")
    business_trip_order_date: Optional[date] = Field(default=None, description="Дата приказа Т-9 (default = contract_sign_date)")
    business_trip_start_date: Optional[date] = Field(default=None, description="Начало командировки")
    business_trip_end_date: Optional[date] = Field(default=None, description="Конец командировки (default = start + 3 года)")
    business_trip_purpose_override: Optional[str] = Field(default=None, description="Переопределение цели командировки для этой заявки (default = position.business_trip_purpose)")
    business_trip_duration_words: Optional[str] = Field(default=None, max_length=32, description="Срок словами ('Сорок шесть'). Авто, если NULL.")
    business_trip_duration_unit: Optional[str] = Field(default=None, max_length=16, description="Единица: 'days', 'months', 'years'. Авто, если NULL.")
    business_trip_place_short: bool = Field(default=False, description="True = 'Испания, г. Барселона', False = полный адрес с индексом")
    employee_tab_number: Optional[str] = Field(default=None, max_length=16, description="Табельный номер сотрудника")

    # === Pack 50.8-A: Справка 2-НДФЛ (найм) ===
    ndfl_2_year: Optional[int] = Field(default=None, description="Год отчётного периода 2-НДФЛ")
    ndfl_2_period_from: Optional[int] = Field(default=None, description="Месяц начала (1..12)")
    ndfl_2_period_to: Optional[int] = Field(default=None, description="Месяц конца (1..12)")
    ndfl_2_issue_date: Optional[date] = Field(default=None, description="Дата формирования справки 2-НДФЛ")

    applicant: Optional["Applicant"] = Relationship(back_populates="applications")
    family_members: List["FamilyMember"] = Relationship(back_populates="application")
    previous_residences: List["PreviousResidence"] = Relationship(back_populates="application")
    uploaded_files: List["UploadedFile"] = Relationship(back_populates="application")
    generated_documents: List["GeneratedDocument"] = Relationship(back_populates="application")

    def validate_business_rules(self) -> List[str]:
        problems: List[str] = []
        if not self.contract_sign_date or not self.submission_date:
            return problems
        days_old = (self.submission_date - self.contract_sign_date).days
        if days_old < 90:
            problems.append(f"Договор подписан {days_old} дней назад, минимум требуется 90")
        if self.contract_end_date and self.contract_end_date <= self.submission_date:
            problems.append(
                f"Договор заканчивается {self.contract_end_date}, до даты подачи {self.submission_date}"
            )
        if not self.company_id or not self.position_id:
            problems.append("Не выбрана компания или должность")
        if not self.representative_id or not self.spain_address_id:
            problems.append("Не выбран представитель или адрес в Испании")
        return problems

    def can_be_archived(self) -> bool:
        """Pack 10: можно ли архивировать. Проверяет финальный статус."""
        return self.status in ARCHIVABLE_STATUSES


# === API schemas ===

class ApplicationCreate(SQLModel):
    applicant_email: Optional[str] = None
    has_family: bool = False
    has_lived_abroad: bool = False
    notes: Optional[str] = None
    submission_date: Optional[date] = None
    # Pack 50.0-B: тип заявки на стадии создания (опционально)
    application_type: Optional[ApplicationType] = None


class ApplicationAssign(SQLModel):
    company_id: int
    position_id: int
    representative_id: int
    spain_address_id: int
    contract_number: str
    contract_sign_date: date
    contract_sign_city: str
    contract_end_date: Optional[date] = None
    salary_rub: Decimal
    submission_date: Optional[date] = None
    payments_period_months: Optional[int] = 3


class ApplicationStatusUpdate(SQLModel):
    new_status: ApplicationStatus
    notes: Optional[str] = None


class ApplicationRead(SQLModel):
    """Read-схема (используется только для документации, реально возвращаем dict)."""
    id: int
    reference: str
    application_type: Optional[ApplicationType] = None  # Pack 50.0-A
    status: ApplicationStatus
    status_notes: Optional[str] = None
    applicant_id: Optional[int] = None
    company_id: Optional[int] = None
    position_id: Optional[int] = None
    representative_id: Optional[int] = None
    spain_address_id: Optional[int] = None
    contract_number: Optional[str] = None
    contract_sign_date: Optional[date] = None
    contract_sign_city: Optional[str] = None
    contract_end_date: Optional[date] = None
    salary_rub: Optional[Decimal] = None
    employer_letter_date: Optional[date] = None
    submission_date: Optional[date] = None
    payments_period_months: Optional[int] = None
    tasa_type: Optional[TasaType] = None
    tasa_nrc: Optional[str] = None
    assigned_manager_id: Optional[int] = None
    internal_notes: Optional[str] = None
    client_access_token: Optional[str] = None
    recommendation_snapshot: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    has_family: Optional[bool] = None
    family_size: Optional[int] = None
    business_rule_problems: Optional[List[str]] = None
    # Pack 10
    is_archived: Optional[bool] = None
    archived_at: Optional[datetime] = None
    can_be_archived: Optional[bool] = None
    # Pack 30.0
    is_urgent: Optional[bool] = None
    # Pack 50.7-A — Приказ Т-9 о командировке (найм)
    business_trip_order_number: Optional[str] = None
    business_trip_order_date: Optional[date] = None
    business_trip_start_date: Optional[date] = None
    business_trip_end_date: Optional[date] = None
    business_trip_purpose_override: Optional[str] = None
    business_trip_duration_words: Optional[str] = None
    business_trip_duration_unit: Optional[str] = None
    business_trip_place_short: Optional[bool] = None
    employee_tab_number: Optional[str] = None
    # Pack 50.8-A — Справка 2-НДФЛ (найм)
    ndfl_2_year: Optional[int] = None
    ndfl_2_period_from: Optional[int] = None
    ndfl_2_period_to: Optional[int] = None
    ndfl_2_issue_date: Optional[date] = None
