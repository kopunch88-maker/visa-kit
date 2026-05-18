# -*- coding: utf-8 -*-
"""
Pack 37.0 — AI Document Audit models.

Симуляция приёма документов в консульстве: ИИ-аудитор получает «досье» кейса
(applicant + company + 16+ сгенерированных документов + сырой OCR оригиналов),
сравнивает всё со всем и выдаёт структурированный список несоответствий с
рекомендациями по исправлению.

Архитектура двух таблиц:
- application_audit_report — 1 строка на каждый запуск проверки (метаданные прогона)
- audit_finding — N строк на отчёт (по 1 на каждое замечание)

Сырой OCR оригиналов уже хранится в applicant_document.parsed_data — отдельная
snapshot-таблица не нужна. Это даёт независимый источник истины относительно
полей applicant: если менеджер случайно переписал last_name_native, parsed_data
сохраняет то, что реально было распознано из паспорта.

Категории findings (поле category):
- identity      — ФИО, дата рождения, паспорт, ИНН
- financial     — суммы в договоре/актах/счетах/выписке, НПД база
- company       — реквизиты компании-нанимателя
- education     — диплом, вуз, специальность, work_history
- spain_pack    — испанские PDF + переводы
- formal        — комплектность пакета, сроки действия документов

Severity:
- critical      — отказ при приёме в консульстве, фикс обязателен
- warning       — повышенный риск отказа, желательно исправить
- info          — нормализация/косметика, по желанию

Verdict (общий по отчёту):
- FAIL          — есть critical → нельзя подавать
- WARN          — есть warning, но нет critical → можно подать с риском
- PASS          — только info или вообще ничего → можно подавать

Статусы finding (поле status):
- open           — новое, ждёт решения менеджера
- accepted       — менеджер нажал «Принять», fix применён
- dismissed      — менеджер нажал «Отклонить» (с опциональной причиной)
- manually_fixed — менеджер сам отредактировал значение
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List

from sqlmodel import Column, Field, SQLModel
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


# ====================================================================
# Enums
# ====================================================================

class AuditVerdict(str, Enum):
    PASS_ = "PASS"   # _ потому что pass — keyword
    WARN = "WARN"
    FAIL = "FAIL"


class AuditCategory(str, Enum):
    IDENTITY = "identity"
    FINANCIAL = "financial"
    COMPANY = "company"
    EDUCATION = "education"
    SPAIN_PACK = "spain_pack"
    FORMAL = "formal"


class AuditSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AuditFindingStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    MANUALLY_FIXED = "manually_fixed"


# ====================================================================
# Таблица 1 — прогон аудита
# ====================================================================

class AuditReport(SQLModel, table=True):
    """
    Один запуск проверки пакета.

    Создаётся в статусе verdict=WARN+error=None при старте, обновляется в финале
    с реальным verdict + summary_counts. Если LLM-вызов упал — error содержит
    текст исключения, findings нет.
    """
    __tablename__ = "application_audit_report"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    # Общий вердикт. На старте — WARN (placeholder), в финале — реальный.
    verdict: AuditVerdict = Field(default=AuditVerdict.WARN, max_length=20)

    # LLM telemetry
    model_used: Optional[str] = Field(default=None, max_length=100)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=4)

    # SHA256 от собранного контекста — для понимания «что менялось между прогонами»
    context_hash: Optional[str] = Field(default=None, max_length=64)

    # Тайминги
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Если упал — текст исключения; если успех — NULL
    error: Optional[str] = Field(default=None, sa_column=Column("error", JSON))
    # ↑ JSON чтобы влезали длинные tracebacks с переводами строк

    # Email менеджера, который запустил
    triggered_by: Optional[str] = Field(default=None, max_length=255)

    # Агрегаты findings для быстрого отображения в списке прогонов
    # {"critical": 3, "warning": 5, "info": 2, "total": 10, "open": 8, "resolved": 2}
    summary_counts: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Pack 37 — флаг что прогон активен (для async фона)
    # is_running=True пока BackgroundTask работает; в финале (успех или ошибка) → False.
    # Frontend polling'ом проверяет это поле каждые 2 сек.
    is_running: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ====================================================================
# Таблица 2 — отдельные findings
# ====================================================================

class AuditFinding(SQLModel, table=True):
    """
    Одно замечание из отчёта аудита.

    LLM возвращает массив findings, каждое сохраняется отдельной строкой —
    чтобы независимо трекать статус (open/accepted/dismissed) и применять
    fix_action через whitelist (см. fix_handlers.py).
    """
    __tablename__ = "audit_finding"

    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="application_audit_report.id", index=True)

    # Классификация
    category: AuditCategory = Field(max_length=50, index=True)
    severity: AuditSeverity = Field(max_length=20, index=True)

    # Заголовок и развёрнутое описание
    title: str = Field(max_length=500)
    description: Optional[str] = None

    # Доказательство — цитаты из документов, где найдено несоответствие
    # Пример: "В паспорте поле 'Фамилия' = ШАХИН (см. parsed_data passport_foreign),
    #          но в БД applicant.last_name_native = Исмаил"
    evidence: Optional[str] = None

    # Куда указывает finding — для UI «открыть соответствующее поле в Drawer»
    # Примеры: "applicant.last_name_native", "company.tax_id_primary",
    #          "applicant.work_history[0].company"
    field_path: Optional[str] = Field(default=None, max_length=255)

    # Что сейчас в БД и что предлагается. Для UI diff-вью.
    current_value: Optional[str] = None
    suggested_value: Optional[str] = None

    # === Fix action — ключ из whitelist в fix_handlers.py ===
    # Если LLM предложил action которого нет в whitelist — fix_action будет
    # сохранён, но кнопка «Принять» в UI не активна (только Dismiss и Manual fix).
    # Это защита от prompt injection и галлюцинаций модели.
    #
    # Примеры fix_action:
    #   "update_applicant_field"   — простой UPDATE одного поля
    #   "swap_first_and_last_name" — менять местами фамилию/имя
    #   "fix_transliteration"      — перегенерация _latin из _native
    #   "update_company_field"     — UPDATE поля компании
    #   "regenerate_inn"           — взять новый ИНН из npd_candidate pool
    #
    # fix_payload — параметры для handler (JSON Schema проверяется в handler'е)
    # Пример для update_applicant_field:
    #   {"field": "last_name_native", "value": "Шахин"}
    # Пример для swap_first_and_last_name:
    #   {} — handler сам берёт текущие значения и меняет местами
    fix_action: Optional[str] = Field(default=None, max_length=100)
    fix_payload: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Статус решения менеджера
    status: AuditFindingStatus = Field(
        default=AuditFindingStatus.OPEN,
        max_length=20,
        index=True,
    )

    # Аудит решения
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = Field(default=None, max_length=255)
    resolution_note: Optional[str] = None  # Для dismissed/manually_fixed

    # Порядок отображения (LLM выставляет по важности)
    sort_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ====================================================================
# DTO для API
# ====================================================================

class AuditFindingRead(SQLModel):
    """Что возвращаем фронту для каждого finding."""
    id: int
    report_id: int
    category: AuditCategory
    severity: AuditSeverity
    title: str
    description: Optional[str] = None
    evidence: Optional[str] = None
    field_path: Optional[str] = None
    current_value: Optional[str] = None
    suggested_value: Optional[str] = None
    fix_action: Optional[str] = None
    fix_payload: dict = {}
    # Флаг для UI: можно ли показывать кнопку «Принять» (handler есть в whitelist)
    can_auto_apply: bool = False
    status: AuditFindingStatus
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    sort_order: int = 0


class AuditReportRead(SQLModel):
    """Что возвращаем фронту для отчёта (без findings — отдельным запросом)."""
    id: int
    application_id: int
    verdict: AuditVerdict
    model_used: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[Decimal] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    is_running: bool
    error: Optional[str] = None
    triggered_by: Optional[str] = None
    summary_counts: dict = {}


class AuditReportWithFindings(AuditReportRead):
    """Полный отчёт с findings — для страницы /audit."""
    findings: List[AuditFindingRead] = []


class AuditRunRequest(SQLModel):
    """Тело POST /applications/{id}/audit/run (опционально)."""
    triggered_by: Optional[str] = None  # Email менеджера; если не задан — из auth


class AuditDismissRequest(SQLModel):
    """POST /audit/findings/{id}/dismiss."""
    note: Optional[str] = None  # Причина отклонения


class AuditManualFixRequest(SQLModel):
    """POST /audit/findings/{id}/manual-fix — менеджер сам ввёл правильное значение."""
    field_path: str           # Дублируем чтобы избежать MITM (не доверять fix_payload из БД)
    new_value: str
    note: Optional[str] = None


class AuditAcceptResponse(SQLModel):
    """Ответ POST /audit/findings/{id}/accept."""
    success: bool
    applied_changes: dict = {}  # {"applicant.last_name_native": ["Исмаил", "Шахин"]}
    message: Optional[str] = None


class AuditRunResponse(SQLModel):
    """Ответ POST /applications/{id}/audit/run — возвращает id нового прогона."""
    report_id: int
    status: str = "started"
