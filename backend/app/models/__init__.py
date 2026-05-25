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
from app.models.npd_refill_task import NpdRefillTask
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

# Pack 19.1: LegendCompany / CareerTrack (генератор work_history)
# LegendCompany — справочник «фейковых» компаний для CV-легенды
# (префикс legend_* специально, чтобы НЕ путать с Company-нанимателями выше).
# CareerTrack — career-track должностей по специальности (1=Junior...4=Lead).
from .legend_company import (
    LegendCompany,
    CareerTrack,
    LegendCompanyRead,
    CareerTrackRead,
    WorkRecordSuggestion,
    WorkHistorySuggestion,
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
    ApplicationRead, ApplicationStatus, ApplicationType, TasaType,
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

from .npd_candidate import NpdCandidate, NpdPoolStats, NpdPoolRefillResult

# Pack 37.0: AI Document Audit — симуляция приёма документов в консульстве
from .audit import (
    AuditReport,
    AuditFinding,
    AuditVerdict,
    AuditCategory,
    AuditSeverity,
    AuditFindingStatus,
    AuditReportRead,
    AuditReportWithFindings,
    AuditFindingRead,
    AuditRunRequest,
    AuditRunResponse,
    AuditDismissRequest,
    AuditManualFixRequest,
    AuditAcceptResponse,
)

# Pack 39.0: Final Submission Audit
from .final_submission import (
    # Tables
    FinalSubmissionDocument,
    FinalSubmissionAuditReport,
    FinalSubmissionFinding,
    # Enums
    FinalSubmissionVerdict,
    FinalSubmissionCategory,
    FinalSubmissionSeverity,
    FinalSubmissionFindingStatus,
    FinalSubmissionDocCategory,
    FinalSubmissionExtractionMethod,
    FinalSubmissionDocSource,
    # DTO
    FinalSubmissionDocumentRead,
    FinalSubmissionFindingRead,
    FinalSubmissionAuditReportRead,
    FinalSubmissionAuditReportWithFindings,
    FinalSubmissionRunRequest,
    FinalSubmissionRunResponse,
    FinalSubmissionUploadResponse,
    FinalSubmissionReplaceRequest,
    FinalSubmissionDismissRequest,
    FinalSubmissionAcknowledgeRequest,
    FinalSubmissionDocCategoryUpdateRequest,
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
    # Pack 19.1: LegendCompany / CareerTrack (work_history generator)
    "LegendCompany",
    "CareerTrack",
    "LegendCompanyRead",
    "CareerTrackRead",
    "WorkRecordSuggestion",
    "WorkHistorySuggestion",
    # Application
    "Applicant", "ApplicantCreate", "ApplicantUpdate", "ApplicantRead",
    "EducationRecord", "WorkRecord",
    "FamilyMember", "FamilyMemberCreate", "FamilyMemberUpdate", "FamilyMemberRead",
    "Application", "ApplicationCreate", "ApplicationAssign", "ApplicationStatusUpdate",
    "ApplicationRead", "ApplicationStatus", "ApplicationType", "TasaType",
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
    "NpdCandidate", "NpdPoolStats", "NpdPoolRefillResult",
    "NpdRefillTask",
    # Pack 37.0: AI Document Audit
    "AuditReport",
    "AuditFinding",
    "AuditVerdict",
    "AuditCategory",
    "AuditSeverity",
    "AuditFindingStatus",
    "AuditReportRead",
    "AuditReportWithFindings",
    "AuditFindingRead",
    "AuditRunRequest",
    "AuditRunResponse",
    "AuditDismissRequest",
    "AuditManualFixRequest",
    "AuditAcceptResponse",
    # Pack 39.0: Final Submission Audit
    "FinalSubmissionDocument",
    "FinalSubmissionAuditReport",
    "FinalSubmissionFinding",
    "FinalSubmissionVerdict",
    "FinalSubmissionCategory",
    "FinalSubmissionSeverity",
    "FinalSubmissionFindingStatus",
    "FinalSubmissionDocCategory",
    "FinalSubmissionExtractionMethod",
    "FinalSubmissionDocSource",
    "FinalSubmissionDocumentRead",
    "FinalSubmissionFindingRead",
    "FinalSubmissionAuditReportRead",
    "FinalSubmissionAuditReportWithFindings",
    "FinalSubmissionRunRequest",
    "FinalSubmissionRunResponse",
    "FinalSubmissionUploadResponse",
    "FinalSubmissionReplaceRequest",
    "FinalSubmissionDismissRequest",
    "FinalSubmissionAcknowledgeRequest",
    "FinalSubmissionDocCategoryUpdateRequest",
]
