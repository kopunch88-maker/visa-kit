"""
ApplicantDocument — документы клиента (паспорт, диплом и т.д.) для OCR.

Pack 13: клиент загружает фото документов через клиентский кабинет.
- Файл сохраняется в R2 (storage backend)
- Storage_key — путь в R2 (для скачивания)
- Doc_type — тип документа (passport_internal_main / passport_foreign / diploma_main и т.д.)
- Status — uploaded / ocr_pending / ocr_done / ocr_failed
- Parsed_data — JSON с распознанными полями (Pack 13.1)

Связан с Application 1:N (одна заявка — много документов).
"""

from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON

from ._base import TimestampMixin

if TYPE_CHECKING:
    from .application import Application


class DocumentType(str, Enum):
    """Типы документов которые загружает клиент."""
    PASSPORT_INTERNAL_MAIN = "passport_internal_main"      # Российский паспорт — главный разворот
    PASSPORT_INTERNAL_ADDRESS = "passport_internal_address"  # Российский паспорт — прописка
    PASSPORT_FOREIGN = "passport_foreign"                  # Загранпаспорт
    DIPLOMA_MAIN = "diploma_main"                          # Диплом — основная страница
    DIPLOMA_APOSTILLE = "diploma_apostille"                # Диплом — апостиль
    OTHER = "other"                                        # Прочее


class DocumentStatus(str, Enum):
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

    doc_type: DocumentType = Field(
        index=True,
        description="Тип документа (паспорт/диплом/...)",
    )

    # Хранилище файла
    storage_key: str = Field(
        max_length=512,
        description="Путь в R2/local storage, например 'applications/123/documents/passport_foreign_1714567890.jpg'",
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
    status: DocumentStatus = Field(
        default=DocumentStatus.UPLOADED,
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
        description="Был ли клиент уведомлён о распознанных данных и они применены",
    )


# === API schemas ===

class DocumentRead(SQLModel):
    id: int
    doc_type: DocumentType
    file_name: str
    file_size: int
    content_type: str
    status: DocumentStatus
    parsed_data: dict
    ocr_error: Optional[str] = None
    ocr_completed_at: Optional[datetime] = None
    applied_to_applicant: bool
    created_at: datetime
    download_url: Optional[str] = None  # signed URL для скачивания


class DocumentUploadResponse(SQLModel):
    id: int
    doc_type: DocumentType
    file_name: str
    status: DocumentStatus
    download_url: Optional[str] = None
