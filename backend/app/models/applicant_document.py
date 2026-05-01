"""
ApplicantDocument — документы, загруженные клиентом для OCR-распознавания.

Это отдельная модель от старой UploadedFile (которая в _supporting.py
для GeneratedDocument). Renamed enums чтобы не конфликтовать.

Pack 13.1.3: добавлено поле original_storage_key для хранения оригинала PDF
(когда клиент загружает PDF, на сервере хранятся оба файла: PDF + конвертированный JPEG).
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Column, Field, SQLModel
from sqlalchemy import JSON


class ApplicantDocumentType(str, Enum):
    """Тип документа клиента — для OCR/автозаполнения."""
    PASSPORT_INTERNAL_MAIN = "passport_internal_main"
    PASSPORT_INTERNAL_ADDRESS = "passport_internal_address"
    PASSPORT_FOREIGN = "passport_foreign"
    DIPLOMA_MAIN = "diploma_main"
    DIPLOMA_APOSTILLE = "diploma_apostille"
    OTHER = "other"


class ApplicantDocumentStatus(str, Enum):
    """Статус OCR-обработки документа."""
    UPLOADED = "uploaded"
    OCR_PENDING = "ocr_pending"
    OCR_DONE = "ocr_done"
    OCR_FAILED = "ocr_failed"


class ApplicantDocument(SQLModel, table=True):
    """
    Документ клиента, загруженный для распознавания.

    Привязан к Application (заявке). Файл хранится в storage backend
    (Cloudflare R2 в production, LocalStorage в dev).

    Pack 13.1.3: storage_key всегда указывает на JPEG для OCR (он же используется
    для превью). original_storage_key опционально содержит оригинальный PDF
    (когда клиент загрузил PDF и мы конвертировали его в JPEG).
    """
    __tablename__ = "applicant_document"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    doc_type: ApplicantDocumentType = Field(index=True)
    status: ApplicantDocumentStatus = Field(default=ApplicantDocumentStatus.UPLOADED)

    # Storage
    # storage_key — основной файл для OCR + превью (всегда JPEG/PNG/WebP)
    storage_key: str = Field(max_length=500)
    # original_storage_key — оригинал, если был PDF (опционально)
    original_storage_key: Optional[str] = Field(default=None, max_length=500)

    file_name: str = Field(max_length=255)
    file_size: int  # размер основного файла (storage_key) в байтах
    content_type: str = Field(max_length=100)  # content_type основного файла

    # Pack 13.1.3: метаданные оригинала (если был PDF)
    original_file_name: Optional[str] = Field(default=None, max_length=255)
    original_file_size: Optional[int] = None
    original_content_type: Optional[str] = Field(default=None, max_length=100)

    # OCR результаты
    parsed_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    ocr_error: Optional[str] = Field(default=None, max_length=1000)
    ocr_completed_at: Optional[datetime] = None

    # Применены ли распознанные данные к Applicant
    applied_to_applicant: bool = Field(default=False)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"onupdate": datetime.utcnow},
    )


# Pydantic схемы для API


class ApplicantDocumentResponse(SQLModel):
    """Ответ API с документом + signed URL для скачивания."""
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
    download_url: Optional[str] = None  # signed URL основного файла (JPEG)
    # Pack 13.1.3: оригинальный PDF
    has_original: bool = False
    original_download_url: Optional[str] = None
    original_file_name: Optional[str] = None
