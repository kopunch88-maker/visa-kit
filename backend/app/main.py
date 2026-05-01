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
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print(f"📦 Database ready at {settings.database_url}")

    apply_pack10_migration()
    apply_pack11_migration()
    apply_pack11_2_migration()
    apply_pack13_migration()  # applicant_document table
    apply_pack15_migration()  # translation table (Pack 15)

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
)

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
