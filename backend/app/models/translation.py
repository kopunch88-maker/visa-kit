"""
Pack 15 — Translation model.

Хранит переводы отрендеренных русских DOCX документов на испанский.
Каждая запись = один переведённый документ конкретного типа (kind)
для конкретной заявки (application_id).

Lifecycle:
1. Менеджер жмёт «Перевести пакет» → создаются 10 записей со статусом PENDING
2. BackgroundTask переводит каждый документ:
   - рендерит русский DOCX
   - прогоняет через docx_translator
   - складывает в R2
   - меняет статус на DONE (или FAILED + error_message)
3. Менеджер видит миниатюры с галочками/крестиками, может перевести отдельный заново

При повторном «Перевести заново» — старые записи удаляются вместе с R2-объектами,
создаются новые.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class TranslationKind(str, Enum):
    """Тип переведённого документа — соответствует document_type в render_endpoints."""
    CONTRACT = "contract"
    ACT_1 = "act_1"
    ACT_2 = "act_2"
    ACT_3 = "act_3"
    INVOICE_1 = "invoice_1"
    INVOICE_2 = "invoice_2"
    INVOICE_3 = "invoice_3"
    EMPLOYER_LETTER = "employer_letter"
    CV = "cv"
    BANK_STATEMENT = "bank_statement"


class TranslationStatus(str, Enum):
    """Статус перевода."""
    PENDING = "pending"      # запущен, ожидает обработки
    IN_PROGRESS = "in_progress"  # сейчас переводится LLM
    DONE = "done"            # успешно, файл в R2
    FAILED = "failed"        # ошибка, см. error_message


class Translation(SQLModel, table=True):
    """
    Переведённый документ пакета.

    Уникальная пара (application_id, kind) — для одной заявки в один момент
    времени один перевод каждого типа. При retry старые записи удаляются.
    """
    __tablename__ = "translation"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    kind: TranslationKind = Field(index=True)
    status: TranslationStatus = Field(default=TranslationStatus.PENDING, index=True)

    # R2 storage — заполняется когда status = DONE
    storage_key: Optional[str] = Field(default=None, max_length=500)
    file_name: Optional[str] = Field(default=None, max_length=255)
    file_size: Optional[int] = None

    # Если status = FAILED, тут описание
    error_message: Optional[str] = Field(default=None, max_length=2000)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
