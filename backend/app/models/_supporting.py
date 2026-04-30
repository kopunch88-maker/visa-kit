"""
Supporting models grouped together for compactness.
Each could be split into its own file if it grows.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON

from ._base import TimestampMixin, CountryCode

if TYPE_CHECKING:
    from .application import Application


# ============================================================================
# PreviousResidence — for additional criminal record certificates
# ============================================================================

class PreviousResidence(TimestampMixin, table=True):
    """Country where applicant lived in the last 5 years (for additional certificates)."""
    __tablename__ = "previous_residence"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    country: CountryCode = Field(max_length=3)
    period_start: date
    period_end: date
    notes: Optional[str] = Field(default=None, max_length=512)

    application: "Application" = Relationship(back_populates="previous_residences")


# ============================================================================
# UploadedFile — files uploaded by client or manager
# ============================================================================

class UploadedFileKind(str, Enum):
    PASSPORT = "passport"
    CRIMINAL_RECORD = "criminal_record"
    CRIMINAL_RECORD_TRANSLATION = "criminal_record_translation"
    EGRYL_EXTRACT = "egryl_extract"
    EGRYL_TRANSLATION = "egryl_translation"
    DIPLOMA = "diploma"
    DIPLOMA_TRANSLATION = "diploma_translation"
    MARRIAGE_CERTIFICATE = "marriage_certificate"
    BIRTH_CERTIFICATE = "birth_certificate"
    TASA_PAYMENT = "tasa_payment"
    BOARDING_PASS = "boarding_pass"
    SPAIN_RESIDENCE_PROOF = "spain_residence_proof"
    SIGNED_CONTRACT_SCAN = "signed_contract_scan"
    SIGNED_DOCUMENT_SCAN = "signed_document_scan"
    OTHER = "other"


class UploadedFile(TimestampMixin, table=True):
    __tablename__ = "uploaded_file"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    kind: UploadedFileKind = Field(index=True)
    filename: str = Field(max_length=256, description="Original filename as uploaded")
    content_type: str = Field(max_length=64)
    size_bytes: int

    # Storage in S3-compatible
    s3_key: str = Field(max_length=512, description="Path in S3 bucket")

    # If file is for a specific family member (passport of spouse etc)
    family_member_id: Optional[int] = Field(default=None, foreign_key="family_member.id")

    # If file expires (e.g. criminal record valid 90 days, EGRYL 30 days)
    valid_until: Optional[date] = Field(
        default=None,
        description="Expiry date of the document (for legal validity, not file storage)",
    )

    notes: Optional[str] = Field(default=None, max_length=512)

    application: "Application" = Relationship(back_populates="uploaded_files")


# ============================================================================
# GeneratedDocument — system-rendered DOCX/PDF files
# ============================================================================

class DocumentType(str, Enum):
    """Types of documents the system generates."""
    CONTRACT = "contract"
    ACT = "act"
    INVOICE = "invoice"
    EMPLOYER_LETTER = "employer_letter"
    CV = "cv"
    BANK_STATEMENT = "bank_statement"
    MIT_FORM = "mit_form"
    MIF_FORM = "mif_form"
    DESIGNACION = "designacion"
    DECLARACION_PENALES = "declaracion_penales"
    COMPROMISO_RETA = "compromiso_reta"
    DECLARACION_MANTENIMIENTO = "declaracion_mantenimiento"


class DocumentSignStatus(str, Enum):
    """Some documents need to be printed, signed and re-uploaded as scans."""
    NOT_REQUIRED = "not_required"
    DRAFT = "draft"
    AWAITING_SIGNED_SCAN = "awaiting_signed_scan"
    SIGNED_SCAN_UPLOADED = "signed_scan_uploaded"
    DIGITALLY_SIGNED = "digitally_signed"


class GeneratedDocument(TimestampMixin, table=True):
    """Document rendered by the system. Multiple per application (acts, invoices)."""
    __tablename__ = "generated_document"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    type: DocumentType = Field(index=True)
    sequence_number: Optional[int] = Field(
        default=None,
        description="For docs that come in sequence: act #1, #2, #3 → 1, 2, 3",
    )

    # If document is for a specific family member
    family_member_id: Optional[int] = Field(default=None, foreign_key="family_member.id")

    filename: str = Field(max_length=256)
    s3_key: str = Field(max_length=512)
    template_version: str = Field(
        max_length=32,
        description="Which template version was used. Important for reproducibility.",
    )

    # Snapshot of data used for rendering — for audit + re-rendering
    snapshot_data: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Full Application data at the moment of rendering",
    )

    sign_status: DocumentSignStatus = Field(default=DocumentSignStatus.NOT_REQUIRED)
    signed_scan_file_id: Optional[int] = Field(
        default=None, foreign_key="uploaded_file.id",
        description="Link to UploadedFile with the signed scan",
    )

    application: "Application" = Relationship(back_populates="generated_documents")


# ============================================================================
# User — managers in admin panel
# ============================================================================

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    READONLY = "readonly"


class User(TimestampMixin, table=True):
    """Internal user (team member) for the admin panel."""
    __tablename__ = "user"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=128)
    full_name: str = Field(max_length=128)
    role: UserRole = Field(default=UserRole.MANAGER)
    is_active: bool = Field(default=True)
    password_hash: Optional[str] = Field(default=None, max_length=128)
    last_login_at: Optional[datetime] = None


# ============================================================================
# TimelineEvent — append-only log of actions on an application
# ============================================================================

class TimelineEvent(TimestampMixin, table=True):
    """Audit log entry — who did what to which application."""
    __tablename__ = "timeline_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    actor_type: str = Field(
        max_length=16,
        description="'system', 'manager', 'client'",
    )
    actor_id: Optional[int] = Field(
        default=None,
        description="user.id for manager, applicant.id for client, null for system",
    )

    event_type: str = Field(
        max_length=64,
        description="'status_changed', 'file_uploaded', 'document_generated', etc.",
    )
    summary: str = Field(max_length=256)
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Free-form data for the event",
    )
