"""
ApplicantDocument — документы клиента (паспорт, диплом и т.д.) для OCR.

Pack 13: клиент загружает фото документов через клиентский кабинет.
- Файл сохраняется в R2 (storage backend)
- Storage_key — путь в R2 (для скачивания)
- doc_type — тип документа (passport_internal_main / passport_foreign / diploma_main и т.д.)
- status — uploaded / ocr_pending / ocr_done / ocr_failed
- parsed_data — JSON с распознанными полями (Pack 13.1)

Связан с Application 1:N (одна заявка — много документов).

ВАЖНО: классы здесь называются ApplicantDocumentType / ApplicantDocumentStatus
чтобы НЕ конфликтовать с существующим DocumentType из _supporting.py
(он используется для GeneratedDocument — генерируемых нами документов).
"""

from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON

from ._base import TimestampMixin

if TYPE_CHECKING:
    from .application import Application


class ApplicantDocumentType(str, Enum):
    """Типы документов которые загружает клиент."""
    PASSPORT_INTERNAL_MAIN = "passport_internal_main"        # Российский паспорт — главный разворот
    PASSPORT_INTERNAL_ADDRESS = "passport_internal_address"  # Российский паспорт — прописка
    PASSPORT_FOREIGN = "passport_foreign"                    # Загранпаспорт
    DIPLOMA_MAIN = "diploma_main"                            # Диплом — основная страница
    DIPLOMA_APOSTILLE = "diploma_apostille"                  # Диплом — апостиль
    OTHER = "other"                                          # Прочее


class ApplicantDocumentStatus(str, Enum):
    """Статус документа в pipeline OCR."""
    UPLOADED = "uploaded"          # Загружен, OCR ещё не запускался
    OCR_PENDING = "ocr_pending"    # OCR в процессе
    OCR_DONE = "ocr_done"          # OCR успешно
    OCR_FAILED = "ocr_failed"      # OCR провалился (плохое качество и т.п.)


class ApplicantDocument(TimestampMixin, table=True):
    __tablename__ = "applicant_document"

    id: Optional[int] = Field(default=None, primary_key=True)

    application_id: int = Field(
        foreign_key="application.id",
        index=True,
        description="К какой заявке привязан документ",
    )

    doc_type: ApplicantDocumentType = Field(
        index=True,
        description="Тип документа (паспорт/диплом/...)",
    )

    # Хранилище файла
    storage_key: str = Field(
        max_length=512,
        description="Путь в R2/local storage",
    )
    file_name: str = Field(
        max_length=256,
        description="Оригинальное имя файла как у клиента",
    )
    file_size: int = Field(description="Размер файла в байтах")
    content_type: str = Field(
        max_length=64,
        description="MIME type, например 'image/jpeg'",
    )

    # OCR pipeline
    status: ApplicantDocumentStatus = Field(
        default=ApplicantDocumentStatus.UPLOADED,
        index=True,
    )
    parsed_data: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="JSON с распознанными полями (Pack 13.1)",
    )
    ocr_error: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Текст ошибки если OCR провалился",
    )
    ocr_completed_at: Optional[datetime] = Field(default=None)

    # Применение к Applicant — было ли применено?
    applied_to_applicant: bool = Field(
        default=False,
        description="Были ли распознанные данные применены к анкете",
    )


# === API schemas ===

class ApplicantDocumentRead(SQLModel):
    id: int
    doc_type: ApplicantDocumentType
    file_name: str
    file_size: int
    content_type: str
    status: ApplicantDocumentStatus
    parsed_data: dict
    ocr_error: Optional[str] = None
    ocr_completed_at: Optional[datetime] = None
    applied_to_applicant: bool
    created_at: datetime
    download_url: Optional[str] = None  # signed URL для скачивания


class ApplicantDocumentUploadResponse(SQLModel):
    id: int
    doc_type: ApplicantDocumentType
    file_name: str
    status: ApplicantDocumentStatus
    download_url: Optional[str] = None