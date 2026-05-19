# -*- coding: utf-8 -*-
"""
Pack 39.0 — Final Submission Audit models.

Финальная проверка пакета документов ПЕРЕД подачей в консульство.
В отличие от Pack 37.0 (AI Document Audit), который проверяет
сгенерированные DOCX/PDF из БД, эта проверка работает с РЕАЛЬНЫМИ
физическими документами которые менеджер собрал на руках
(сканы паспортов, апостили, переводы jurada, банковские выписки).

LLM играет роль визового инспектора на приёме: сверяет ФИО/даты/номера
между всеми загруженными документами и выдаёт чеклист несоответствий.

Архитектура трёх таблиц:
- final_submission_document       — физические документы (привязка к applicant,
                                    ON DELETE CASCADE, история версий)
- final_submission_audit_report   — прогон проверки
- final_submission_finding        — отдельные находки

История версий:
- Менеджер загрузил passport.pdf → is_active=True
- Заметил опечатку, заказал новый, загрузил passport_v2.pdf
- Старая запись: is_active=False, replaced_at=NOW
- Новая запись: is_active=True, previous_version_id=<id старой>
- Удаление без замены: is_active=False, replaced_at=NULL
  (различаем «переделал» vs «удалил насовсем»)

Категории findings:
- A_identity     — ФИО, дата рождения, номер паспорта между документами
- B_numeric      — суммы в договоре = акты = счета = выписка; периоды
- C_dates        — логика дат (договор раньше актов, паспорт не истекает)
- D_company      — реквизиты компании одинаковые везде
- E_translation  — переводы jurada соответствуют оригиналам
- F_completeness — комплектность пакета (все обязательные документы)
- G_quality      — читаемость сканов, печати, подписи
- H_stale        — хвосты прошлых клиентов в шаблонах (ALIYEV problem)

Severity:
- critical — гарантированный отказ при приёме
- warning  — могут придраться, риск отказа
- info     — косметика

Verdict (общий):
- FAIL — есть critical → не подавать
- WARN — есть warning без critical → можно с риском
- PASS — только info или ничего → к подаче готово
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List

from sqlmodel import Column, Field, SQLModel
from sqlalchemy import JSON


# ====================================================================
# Enums
# ====================================================================

class FinalSubmissionVerdict(str, Enum):
    PASS_ = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class FinalSubmissionCategory(str, Enum):
    """Категории findings инспектора."""
    A_IDENTITY = "A_identity"
    B_NUMERIC = "B_numeric"
    C_DATES = "C_dates"
    D_COMPANY = "D_company"
    E_TRANSLATION = "E_translation"
    F_COMPLETENESS = "F_completeness"
    G_QUALITY = "G_quality"
    H_STALE = "H_stale"


class FinalSubmissionSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class FinalSubmissionFindingStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"   # «учёл, иду переделывать»
    DISMISSED = "dismissed"         # «false positive»


class FinalSubmissionDocCategory(str, Enum):
    """
    Тип документа в пакете. Определяется AI-классификатором при загрузке,
    менеджер может вручную поправить.
    """
    PASSPORT_MAIN = "passport_main"
    PASSPORT_OTHER = "passport_other"
    APOSTILLE = "apostille"
    CONTRACT = "contract"
    ACT = "act"
    INVOICE = "invoice"
    BANK_STATEMENT = "bank_statement"
    CV = "cv"
    NPD_CERTIFICATE = "npd_certificate"
    DIPLOMA = "diploma"
    JURADA_TRANSLATION = "jurada_translation"
    MI_T_FORM = "mi_t_form"
    DESIGNACION = "designacion"
    COMPROMISO = "compromiso"
    DECLARACION = "declaracion"
    EX17 = "ex17"
    PHOTO_3X4 = "photo_3x4"
    MEDICAL_INSURANCE = "medical_insurance"
    CRIMINAL_RECORD = "criminal_record"
    MARRIAGE_CERTIFICATE = "marriage_certificate"
    OTHER = "other"


class FinalSubmissionExtractionMethod(str, Enum):
    PYPDF = "pypdf"
    VISION = "vision"
    DOCX2TXT = "docx2txt"
    MIXED = "mixed"


class FinalSubmissionDocSource(str, Enum):
    """Откуда взялась категория документа."""
    AI = "ai"
    MANUAL = "manual"


# ====================================================================
# Таблица 1 — физические документы клиента
# ====================================================================

class FinalSubmissionDocument(SQLModel, table=True):
    """
    Физический документ из пакета на подачу.

    Привязка к applicant (а не application) — документы могут переиспользоваться
    при повторной подаче того же клиента.

    История версий: при замене файла старая запись помечается is_active=False
    и replaced_at=NOW, новая запись получает previous_version_id=<id старой>.
    Среди is_active=True не может быть двух одинаковых файлов одного клиента
    (UNIQUE на applicant_id+sha256 partial по WHERE is_active=TRUE).

    ON DELETE CASCADE: удалили клиента → ушли документы из БД.
    R2-cleanup делается хуком в endpoint удаления (Pack 39.0-B).
    """
    __tablename__ = "final_submission_document"

    id: Optional[int] = Field(default=None, primary_key=True)
    applicant_id: int = Field(foreign_key="applicant.id", index=True)
    application_id: Optional[int] = Field(
        default=None,
        foreign_key="application.id",
        index=True,
    )

    # --- файл ---
    original_filename: str = Field(max_length=512)
    mime_type: str = Field(max_length=128)
    file_size_bytes: int  # BigInteger в БД (см. migrations.py)
    s3_key: str = Field(max_length=512)
    sha256: str = Field(max_length=64)

    # --- классификация ---
    doc_category: Optional[FinalSubmissionDocCategory] = Field(
        default=None, max_length=50, index=True,
    )
    doc_category_confidence: Optional[Decimal] = Field(
        default=None, max_digits=4, decimal_places=3,
    )
    doc_category_source: FinalSubmissionDocSource = Field(
        default=FinalSubmissionDocSource.AI, max_length=20,
    )

    # --- кэш извлечённого текста (чтобы не платить Vision повторно) ---
    extracted_text: Optional[str] = None
    extraction_method: Optional[FinalSubmissionExtractionMethod] = Field(
        default=None, max_length=20,
    )
    extraction_cost_usd: Optional[Decimal] = Field(
        default=Decimal("0"), max_digits=10, decimal_places=4,
    )
    page_count: Optional[int] = None

    # --- история версий ---
    is_active: bool = Field(default=True, index=True)
    previous_version_id: Optional[int] = Field(
        default=None,
        foreign_key="final_submission_document.id",
    )
    replaced_at: Optional[datetime] = None

    # --- аудит ---
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    uploaded_by: Optional[str] = Field(default=None, max_length=255)


# ====================================================================
# Таблица 2 — прогон финальной проверки
# ====================================================================

class FinalSubmissionAuditReport(SQLModel, table=True):
    """
    Один запуск финальной проверки физического пакета.

    В отличие от AuditReport (Pack 37.0), который проверяет
    сгенерированные DOCX из БД, здесь проверяются реально загруженные
    файлы (сканы, переводы и т.д.).

    is_running=True пока BackgroundTask работает; в финале → False.
    Frontend polling'ом проверяет каждые 2 сек (как Pack 37.0).
    """
    __tablename__ = "final_submission_audit_report"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    applicant_id: int = Field(foreign_key="applicant.id", index=True)

    verdict: FinalSubmissionVerdict = Field(
        default=FinalSubmissionVerdict.WARN, max_length=20,
    )

    # LLM telemetry
    model_used: Optional[str] = Field(default=None, max_length=100)
    prompt_version: Optional[str] = Field(default=None, max_length=20)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    vision_pages: Optional[int] = Field(default=0)
    cost_usd: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=4)

    # Снимок документов которые участвовали в этом прогоне (id из final_submission_document).
    # При замене файла потом — видно «какая версия была в прогоне №1»
    included_document_ids: List[int] = Field(default_factory=list, sa_column=Column(JSON))

    # {"passport_main": 1, "apostille": 1, "contract": 1, ...} — для quick-view в истории
    document_categories_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Тайминги
    is_running: bool = Field(default=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    error: Optional[str] = Field(default=None, sa_column=Column("error", JSON))

    triggered_by: Optional[str] = Field(default=None, max_length=255)

    # {"critical": 3, "warning": 5, "info": 2, "total": 10}
    summary_counts: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Резюме инспектора одной фразой: «Что бы сказал сотрудник консульства»
    # Пример: «Не приму: в договоре номер паспорта без пробела, в паспорте — с пробелом»
    inspector_summary: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ====================================================================
# Таблица 3 — отдельные находки
# ====================================================================

class FinalSubmissionFinding(SQLModel, table=True):
    """
    Одна находка инспектора в физическом пакете.

    В отличие от AuditFinding (Pack 37.0), здесь нет fix_action —
    менеджер не правит БД, он идёт переделывать документ.
    Есть recommendation (что делать) и affected_documents (где смотреть).
    """
    __tablename__ = "final_submission_finding"

    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(
        foreign_key="final_submission_audit_report.id", index=True,
    )

    category: FinalSubmissionCategory = Field(max_length=30, index=True)
    severity: FinalSubmissionSeverity = Field(max_length=20, index=True)

    title: str = Field(max_length=500)
    description: Optional[str] = None
    # Что менеджеру делать (конкретное действие, не общая фраза).
    # Пример: «Переоформить договор у директора — в паспорте номер с пробелом после серии»
    recommendation: Optional[str] = None

    # Какие документы затрагивает finding (для UI «открыть документ X на странице Y»).
    # [{"document_id": 12, "filename": "passport.pdf", "page": 2}, ...]
    affected_documents: List[dict] = Field(default_factory=list, sa_column=Column(JSON))

    # Имя поля где расхождение.
    # Примеры: "passport_number", "contract_amount", "director_name"
    field_name: Optional[str] = Field(default=None, max_length=128)

    # Что нашли в каждом документе — для UI diff-вью.
    # {"passport.pdf": "75 1234567", "contract.docx": "751234567"}
    values_found: dict = Field(default_factory=dict, sa_column=Column(JSON))

    status: FinalSubmissionFindingStatus = Field(
        default=FinalSubmissionFindingStatus.OPEN, max_length=20, index=True,
    )

    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = Field(default=None, max_length=255)
    resolution_note: Optional[str] = None

    sort_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ====================================================================
# DTO для API
# ====================================================================

class FinalSubmissionDocumentRead(SQLModel):
    """Что возвращаем фронту для каждого загруженного документа."""
    id: int
    applicant_id: int
    application_id: Optional[int] = None

    original_filename: str
    mime_type: str
    file_size_bytes: int
    s3_key: str
    sha256: str

    doc_category: Optional[FinalSubmissionDocCategory] = None
    doc_category_confidence: Optional[Decimal] = None
    doc_category_source: FinalSubmissionDocSource = FinalSubmissionDocSource.AI

    extraction_method: Optional[FinalSubmissionExtractionMethod] = None
    page_count: Optional[int] = None

    is_active: bool
    previous_version_id: Optional[int] = None
    replaced_at: Optional[datetime] = None

    uploaded_at: datetime
    uploaded_by: Optional[str] = None


class FinalSubmissionFindingRead(SQLModel):
    """Что возвращаем фронту для каждой находки."""
    id: int
    report_id: int
    category: FinalSubmissionCategory
    severity: FinalSubmissionSeverity
    title: str
    description: Optional[str] = None
    recommendation: Optional[str] = None
    affected_documents: List[dict] = []
    field_name: Optional[str] = None
    values_found: dict = {}
    status: FinalSubmissionFindingStatus
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    sort_order: int = 0


class FinalSubmissionAuditReportRead(SQLModel):
    """Что возвращаем фронту для отчёта (без findings — отдельным запросом)."""
    id: int
    application_id: int
    applicant_id: int
    verdict: FinalSubmissionVerdict
    model_used: Optional[str] = None
    prompt_version: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    vision_pages: Optional[int] = 0
    cost_usd: Optional[Decimal] = None
    included_document_ids: List[int] = []
    document_categories_snapshot: dict = {}
    is_running: bool
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    triggered_by: Optional[str] = None
    summary_counts: dict = {}
    inspector_summary: Optional[str] = None


class FinalSubmissionAuditReportWithFindings(FinalSubmissionAuditReportRead):
    """Полный отчёт с findings + список документов для страницы /audit."""
    findings: List[FinalSubmissionFindingRead] = []
    documents: List[FinalSubmissionDocumentRead] = []


class FinalSubmissionRunRequest(SQLModel):
    """POST /applicants/{id}/final-submission/audit/run."""
    application_id: int
    triggered_by: Optional[str] = None


class FinalSubmissionRunResponse(SQLModel):
    """Ответ POST /applicants/{id}/final-submission/audit/run — id нового прогона."""
    report_id: int
    status: str = "started"


class FinalSubmissionUploadResponse(SQLModel):
    """Ответ POST /applicants/{id}/final-submission/upload."""
    uploaded: List[FinalSubmissionDocumentRead] = []
    skipped_duplicates: List[str] = []  # filenames которые уже были (по SHA256)
    errors: List[dict] = []  # [{"filename": "...", "error": "..."}]


class FinalSubmissionReplaceRequest(SQLModel):
    """POST /applicants/{id}/final-submission/{doc_id}/replace."""
    keep_category: bool = True  # копировать категорию старого файла на новый


class FinalSubmissionDismissRequest(SQLModel):
    """POST /final-submission/findings/{id}/dismiss."""
    note: Optional[str] = None


class FinalSubmissionAcknowledgeRequest(SQLModel):
    """POST /final-submission/findings/{id}/acknowledge — «учёл, иду переделывать»."""
    note: Optional[str] = None


class FinalSubmissionDocCategoryUpdateRequest(SQLModel):
    """PATCH /applicants/{id}/final-submission/{doc_id}/category — менеджер вручную правит категорию."""
    doc_category: FinalSubmissionDocCategory
