"""
FastAPI application — точка входа.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.db.migrations import (
    apply_pack10_migration,
    apply_pack11_migration,
    apply_pack11_2_migration,
    apply_pack13_migration,
    apply_pack15_migration,
    apply_pack15_1_migration,
    apply_pack16_migration,
    apply_pack17_0_migration,
    apply_pack17_2_4_migration,
    apply_pack17_2_4_1_migration,
    apply_pack28_0_migration,
    apply_pack28_2_migration,
    apply_pack28_5_migration,
    apply_pack29_0_migration,
    apply_pack30_0_migration,
    apply_pack34_2_migration,  # Pack 30.0
    apply_pack35_2_migration,  # Pack 35.2 — applicant.passport_issuer_ru
    apply_pack38_1_migration,  # Pack 38.1 — application.is_paid
    apply_pack36_1_migration,  # Pack 36.1 — application.nie + fingerprint_date
    apply_pack37_0_migration,
    apply_pack39_0_migration,  # Pack 39.0 Final Submission Audit
    apply_pack39_0_A2_migration,  # Pack 39.0-A2 rename s3_key → storage_key  # Pack 37.0 — AI Document Audit
    apply_pack50_0_A_migration,  # Pack 50.0-A application.application_type
    apply_pack50_7_A_migration,  # Pack 50.7-A business_trip fields (T-9)
    apply_pack50_7_C_prep_migration,  # Pack 50.7-C-prep applicant.full_name_accusative
    apply_pack50_41_name_cases_migration,  # Pack 50.41 родительный+творительный ФИО
    apply_pack50_42_dative_migration,  # Pack 50.42 дательный ФИО
    apply_pack50_1_A_migration,  # Pack 50.1-A company.ogrn + email (Трудовой договор)
    apply_pack50_1_F2_migration,  # Pack 50.1-F2 applicant.snils
    apply_pack50_1_H_migration,  # Pack 50.1-H company.contract_font_family
    apply_pack50_1_G_migration,  # Pack 50.1-G employment_contract_template_slug + font_family
    apply_pack50_8_migration,  # Pack 50.8-A 2-NDFL fields (ndfl_2_* + company.oktmo/phone)
    apply_pack50_9_migration,  # Pack 50.9-A СТД-Р fields (stdr_* + company.sfr_registration_number + position.okz_code)
    apply_pack50_10_migration,  # Pack 50.10-A Расчётный листок (company.accountant_short_ru)
    apply_pack50_12_migration,  # Pack 50.12-A СОО (application.soo_number + soo_date)
    apply_pack50_15_migration,  # Pack 50.15-A русский телефон (applicant.phone_ru)
    apply_pack56_0_migration,  # Pack 56.0 поля окна «Ситы» (applicant.cita_*)
    apply_pack56_2_migration,  # Pack 56.1 локация ситы (applicant.cita_location)
    apply_pack56_3_migration,  # Pack 56.4 флаг отлова сит (applicant.cita_catching)
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print(f"📦 Database ready at {settings.database_url}")

    apply_pack10_migration()
    apply_pack11_migration()
    apply_pack11_2_migration()
    apply_pack13_migration()
    apply_pack15_migration()
    apply_pack15_1_migration()
    apply_pack16_migration()  # Bank table + applicant.bank_id (Pack 16)
    apply_pack17_0_migration()  # Region table + applicant.inn_* fields (Pack 17.0)
    apply_pack17_2_4_migration()  # self_employed_registry + registry_import_log (Pack 17.2.4)
    apply_pack17_2_4_1_migration()  # BigInteger fix + reset stuck imports (Pack 17.2.4.1)
    apply_pack28_0_migration()  # npd_candidate indexes (Pack 28.0)
    apply_pack28_2_migration()  # npd_refill_task table + indexes (Pack 28.2)
    apply_pack28_5_migration()  # Pack 28.5 result_registration_date column
    apply_pack29_0_migration()  # Pack 29.0 company.contract_template_slug + backfill
    apply_pack30_0_migration()
    apply_pack34_2_migration()  # Pack 30.0 application.is_urgent
    apply_pack35_2_migration()  # Pack 35.2 applicant.passport_issuer_ru
    apply_pack38_1_migration()  # Pack 38.1 application.is_paid
    apply_pack36_1_migration()  # Pack 36.1 application.nie + fingerprint_date
    apply_pack37_0_migration()
    apply_pack39_0_migration()  # Pack 39.0 Final Submission Audit tables
    apply_pack39_0_A2_migration()  # Pack 39.0-A2 storage_key rename  # Pack 37.0 AI Document Audit indexes
    apply_pack50_0_A_migration()  # Pack 50.0-A application.application_type
    apply_pack50_7_A_migration()  # Pack 50.7-A business_trip fields (T-9)
    apply_pack50_7_C_prep_migration()  # Pack 50.7-C-prep applicant.full_name_accusative
    apply_pack50_41_name_cases_migration()  # Pack 50.41 родительный+творительный ФИО
    apply_pack50_42_dative_migration()  # Pack 50.42 дательный ФИО
    apply_pack50_1_A_migration()  # Pack 50.1-A company.ogrn + email
    apply_pack50_1_F2_migration()  # Pack 50.1-F2 applicant.snils
    apply_pack50_1_H_migration()  # Pack 50.1-H company.contract_font_family
    apply_pack50_1_G_migration()  # Pack 50.1-G employment_contract_template_slug + font_family
    apply_pack50_8_migration()  # Pack 50.8-A 2-NDFL fields (ndfl_2_* + company.oktmo/phone)
    apply_pack50_9_migration()  # Pack 50.9-A СТД-Р fields
    apply_pack50_10_migration()  # Pack 50.10-A Расчётный листок
    apply_pack50_12_migration()  # Pack 50.12-A СОО
    apply_pack50_15_migration()  # Pack 50.15-A русский телефон
    apply_pack56_0_migration()  # Pack 56.0 поля окна «Ситы» (applicant.cita_*)
    apply_pack56_2_migration()  # Pack 56.1 локация ситы (applicant.cita_location)
    apply_pack56_3_migration()  # Pack 56.4 флаг отлова сит
    if settings.storage_backend == "local":
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Local file storage: {settings.storage_path}")

    yield


app = FastAPI(
    title="Visa kit API",
    description="Spain digital nomad visa application kit",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api import (  # noqa: E402
    auth,
    companies,
    positions,
    representatives,
    spain_addresses,
    applications,
    render_endpoints,
    applicants,
    client_portal,
    client_documents_admin,
    import_package,
    bank_transactions,
    translations,
    banks,
    regions,
    inn_debug,
    inn_generation,
    inn_debug_pipeline,
    registry_admin,  # Pack 17.2.4
    npd_pool_admin,  # Pack 28.2
    inn_date_refine,  # Pack 28.5
    audit,  # ← Pack 37.0 AI Document Audit
)
from app.api import ifns_mfc
from app.api import final_submission  # Pack 39.0-B
from app.api import tech_opinion  # Pack 40.0
app.include_router(auth.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(representatives.router, prefix="/api")
app.include_router(spain_addresses.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(render_endpoints.router, prefix="/api")
app.include_router(applicants.router, prefix="/api")
app.include_router(client_portal.router, prefix="/api")
app.include_router(client_documents_admin.router, prefix="/api")
app.include_router(import_package.router, prefix="/api")
app.include_router(bank_transactions.router, prefix="/api")
app.include_router(translations.router, prefix="/api")
app.include_router(banks.router, prefix="/api")
app.include_router(ifns_mfc.router)
app.include_router(regions.router, prefix="/api")
app.include_router(inn_debug.router, prefix="/api")
app.include_router(inn_generation.router, prefix="/api")
app.include_router(inn_debug_pipeline.router, prefix="/api")
app.include_router(registry_admin.router, prefix="/api")  # Pack 17.2.4
app.include_router(npd_pool_admin.router, prefix="/api")  # Pack 28.2
app.include_router(inn_date_refine.router, prefix="/api")  # Pack 28.5
app.include_router(audit.router)
app.include_router(final_submission.router)  # Pack 39.0-B Final Submission
app.include_router(tech_opinion.router, prefix="/api")  # Pack 40.0 Tech Opinion

@app.get("/", tags=["meta"])
def root():
    return {
        "service": "visa-kit-backend",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
# Force rebuild after storage fix
