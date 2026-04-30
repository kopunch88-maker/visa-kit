"""
Models package.

All SQLModel entities live here. They serve as both ORM models and Pydantic
schemas (for FastAPI request/response validation).

Import from here, not from individual files:
    from app.models import Application, Company, Position
"""

# Base utilities
from ._base import TimestampMixin, utcnow, CountryCode, CurrencyCode

# Directory entities
from .company import Company, CompanyCreate, CompanyUpdate, CompanyRead
from .position import Position, PositionCreate, PositionUpdate, PositionRead
from .representative import (
    Representative, RepresentativeCreate, RepresentativeUpdate, RepresentativeRead,
)
from .spain_address import (
    SpainAddress, SpainAddressCreate, SpainAddressUpdate, SpainAddressRead,
)

# Application entities
from .applicant import (
    Applicant, ApplicantCreate, ApplicantUpdate, ApplicantRead,
    EducationRecord, WorkRecord,
)
from .family_member import (
    FamilyMember, FamilyMemberCreate, FamilyMemberUpdate, FamilyMemberRead,
)
from .application import (
    Application, ApplicationCreate, ApplicationAssign, ApplicationStatusUpdate,
    ApplicationRead, ApplicationStatus, TasaType,
)

# Supporting entities (smaller, grouped together)
from ._supporting import (
    PreviousResidence,
    UploadedFile, UploadedFileKind,
    GeneratedDocument, DocumentType, DocumentSignStatus,
    User, UserRole,
    TimelineEvent,
)

# Pack 13: client documents for OCR
# Имена ApplicantDocumentType / ApplicantDocumentStatus — чтобы не конфликтовать
# с DocumentType из _supporting (для GeneratedDocument)
from .applicant_document import (
    ApplicantDocument,
    ApplicantDocumentType,
    ApplicantDocumentStatus,
)

__all__ = [
    # Base
    "TimestampMixin", "utcnow", "CountryCode", "CurrencyCode",
    # Directories
    "Company", "CompanyCreate", "CompanyUpdate", "CompanyRead",
    "Position", "PositionCreate", "PositionUpdate", "PositionRead",
    "Representative", "RepresentativeCreate", "RepresentativeUpdate", "RepresentativeRead",
    "SpainAddress", "SpainAddressCreate", "SpainAddressUpdate", "SpainAddressRead",
    # Application
    "Applicant", "ApplicantCreate", "ApplicantUpdate", "ApplicantRead",
    "EducationRecord", "WorkRecord",
    "FamilyMember", "FamilyMemberCreate", "FamilyMemberUpdate", "FamilyMemberRead",
    "Application", "ApplicationCreate", "ApplicationAssign", "ApplicationStatusUpdate",
    "ApplicationRead", "ApplicationStatus", "TasaType",
    # Supporting
    "PreviousResidence",
    "UploadedFile", "UploadedFileKind",
    "GeneratedDocument", "DocumentType", "DocumentSignStatus",
    "User", "UserRole",
    "TimelineEvent",
    # Pack 13: applicant documents for OCR
    "ApplicantDocument",
    "ApplicantDocumentType",
    "ApplicantDocumentStatus",
]