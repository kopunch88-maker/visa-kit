"""
FastAPI application — точка входа.

Запуск для разработки:
    uvicorn app.main:app --reload

Swagger UI: http://localhost:8000/docs
ReDoc:      http://localhost:8000/redoc
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
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown hooks.

    На старте — создаём таблицы в БД (для разработки) и применяем миграции.
    """
    init_db()
    print(f"📦 Database ready at {settings.database_url}")

    # Pack 10: поля is_archived / archived_at в application
    apply_pack10_migration()
    # Pack 11: поле password_hash в user (для bcrypt auth)
    apply_pack11_migration()
    # Pack 11.2: снять NOT NULL с applicant полей (для пошагового сохранения)
    apply_pack11_2_migration()

    if settings.storage_backend == "local":
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Local file storage: {settings.storage_path}")

    yield

    # На shutdown ничего не делаем


app = FastAPI(
    title="Visa kit API",
    description="Spain digital nomad visa application kit",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — фронт на 3000, бэк на 8000, без CORS не подключатся
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Подключаем роутеры ===
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
    bank_transactions,
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
app.include_router(bank_transactions.router, prefix="/api")


# === Health check ===

@app.get("/", tags=["meta"])
def root():
    """Корень — подтверждение что бэк работает."""
    return {
        "service": "visa-kit-backend",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
def health():
    """Health check для мониторинга."""
    return {"status": "ok"}