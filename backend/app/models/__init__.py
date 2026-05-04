"""
Models package.

All SQLModel entities live here. They serve as both ORM models and Pydantic
schemas (for FastAPI request/response validation).

Import from here, not from individual files:
    from app.models import Application, Company, Position
"""

# Base utilities
from ._base import TimestampMixin, utcnow, CountryCode, CurrencyCode
from app.models.ifns_mfc import IfnsOffice, MfcOffice
# Directory entities
from .company import Company, CompanyCreate, CompanyUpdate, CompanyRead
from .position import Position, PositionCreate, PositionUpdate, PositionRead
from .representative import (
    Representative, RepresentativeCreate, RepresentativeUpdate, RepresentativeRead,
)
from .spain_address import (
    SpainAddress, SpainAddressCreate, SpainAddressUpdate, SpainAddressRead,
)

# Pack 16: Bank directory
from .bank import Bank, BankCreate, BankUpdate, BankRead

# Pack 17: Regions directory (for INN auto-generation)
from .region import Region, RegionCreate, RegionUpdate, RegionRead

# Pack 17.2.4: Self-employed registry (local DB built from FNS open data dump)
from .self_employed_registry import (
    SelfEmployedRegistry,
    RegistryImportLog,
    SelfEmployedRegistryStats,
    RegistryImportLogRead,
    StartImportRequest,
)

# Pack 19.0: University / Specialty / PositionSpecialtyMap (генератор образования)
from .university import (
    University,
    Specialty,
    UniversitySpecialtyLink,
    PositionSpecialtyMap,
    UniversityRead,
    SpecialtyRead,
    UniversitySuggestion,
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

# Supporting entities
from ._supporting import (
    PreviousResidence,
    UploadedFile, UploadedFileKind,
    GeneratedDocument, DocumentType, DocumentSignStatus,
    User, UserRole,
    TimelineEvent,
)

# Pack 13: client documents for OCR
from .applicant_document import (
    ApplicantDocument,
    ApplicantDocumentType,
    ApplicantDocumentStatus,
)

# Pack 15: translations
from .translation import (
    Translation,
    TranslationKind,
    TranslationStatus,
)

__all__ = [
    # Base
    "TimestampMixin", "utcnow", "CountryCode", "CurrencyCode",
    # Directories
    "Company", "CompanyCreate", "CompanyUpdate", "CompanyRead",
    "Position", "PositionCreate", "PositionUpdate", "PositionRead",
    "Representative", "RepresentativeCreate", "RepresentativeUpdate", "RepresentativeRead",
    "SpainAddress", "SpainAddressCreate", "SpainAddressUpdate", "SpainAddressRead",
    # Pack 16: Bank
    "Bank", "BankCreate", "BankUpdate", "BankRead",
    # Pack 17: Region
    "Region", "RegionCreate", "RegionUpdate", "RegionRead",
    # Pack 17.2.4: Self-employed registry
    "SelfEmployedRegistry",
    "RegistryImportLog",
    "SelfEmployedRegistryStats",
    "RegistryImportLogRead",
    "StartImportRequest",
    # Pack 19.0: University / Specialty
    "University",
    "Specialty",
    "UniversitySpecialtyLink",
    "PositionSpecialtyMap",
    "UniversityRead",
    "SpecialtyRead",
    "UniversitySuggestion",
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
    # Pack 15: translations
    "Translation",
    "TranslationKind",
    "TranslationStatus",
      # ... existing ...
    "IfnsOffice",
    "MfcOffice",
]



