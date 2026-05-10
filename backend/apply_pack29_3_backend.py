# -*- coding: utf-8 -*-
"""
Pack 29.3 — Backend integration of per-company contract templates.

Patcher script — применяется поверх существующих файлов в репо.

Изменения:
  1. models/company.py — добавляем contract_template_slug в 4 места
  2. db/migrations.py — добавляем apply_pack29_0_migration() функцию
  3. main.py — вызываем миграцию в lifespan
  4. templates_engine/docx_renderer.py — переписываем render_contract +
     добавляем NeedsContractTemplateError exception
  5. api/companies.py — добавляем GET /admin/companies/contract-templates

Применять:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:PYTHONIOENCODING="utf-8"
    python apply_pack29_3_backend.py
"""
import os
import sys
import re
import shutil
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(os.environ.get("VISA_REPO_ROOT", r"D:\VISA\visa_kit"))
BACKEND = REPO_ROOT / "backend"


def backup(path: Path) -> Path:
    """Make a timestamped backup of a file before patching."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak_pre_pack29_3_{stamp}")
    shutil.copy2(path, bak)
    return bak


def replace_in_file(path: Path, old: str, new: str, count: int = 1) -> bool:
    """
    Replace `old` with `new` exactly `count` times in file.
    Normalizes line endings to LF for comparison, preserves original EOL style on save.
    Returns True if any replacement happened, False if old not found.
    """
    raw = path.read_bytes()
    # Detect original EOL style
    has_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    if has_crlf:
        text_lf = text.replace("\r\n", "\n")
    else:
        text_lf = text

    occurrences = text_lf.count(old)
    if occurrences == 0:
        print(f"  ✗ NOT FOUND in {path.name}: {old[:60]!r}...")
        return False
    if count == 1 and occurrences > 1:
        print(f"  ✗ AMBIGUOUS in {path.name}: '{old[:60]}...' found {occurrences} times, expected 1")
        return False
    new_text_lf = text_lf.replace(old, new, count)
    # Restore original EOL style
    if has_crlf:
        new_text = new_text_lf.replace("\n", "\r\n")
    else:
        new_text = new_text_lf
    path.write_bytes(new_text.encode("utf-8"))
    print(f"  ✓ Patched {path.name}: {occurrences} replacement(s)")
    return True


def patch_company_model():
    """Add contract_template_slug field to Company model + 3 schemas."""
    path = BACKEND / "app" / "models" / "company.py"
    print(f"\n[1/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # === 1.1: Class Company ===
    # Вставляем поле прямо перед "# Banking" блоком
    replace_in_file(path,
        "    # Banking — primary account used for receiving payments under contracts\n"
        "    bank_name: str = Field(max_length=128)",
        "    # Pack 29.0: контрактный шаблон (slug в contracts_registry)\n"
        "    contract_template_slug: Optional[str] = Field(\n"
        "        default=None,\n"
        "        max_length=64,\n"
        "        index=True,\n"
        "        description=\"Slug шаблона договора (см. contracts_registry). \"\n"
        "                    \"Если NULL — fallback на COMPANY_INN_TO_SLUG[tax_id_primary] или 'default'. \"\n"
        "                    \"Если ни то ни другое — render_contract вернёт 409 NEEDS_CONTRACT_TEMPLATE.\",\n"
        "    )\n"
        "\n"
        "    # Banking — primary account used for receiving payments under contracts\n"
        "    bank_name: str = Field(max_length=128)"
    )

    # === 1.2: CompanyCreate ===
    replace_in_file(path,
        "    director_full_name_latin: Optional[str] = None  # Pack 15.1\n"
        "    bank_name: str\n"
        "    bank_account: str\n"
        "    bank_bic: str\n"
        "    bank_correspondent_account: Optional[str] = None\n"
        "    egryl_extract_date: Optional[date] = None\n"
        "    notes: Optional[str] = None",
        "    director_full_name_latin: Optional[str] = None  # Pack 15.1\n"
        "    contract_template_slug: Optional[str] = None  # Pack 29.0\n"
        "    bank_name: str\n"
        "    bank_account: str\n"
        "    bank_bic: str\n"
        "    bank_correspondent_account: Optional[str] = None\n"
        "    egryl_extract_date: Optional[date] = None\n"
        "    notes: Optional[str] = None"
    )

    # === 1.3: CompanyUpdate ===
    replace_in_file(path,
        "    director_full_name_latin: Optional[str] = None  # Pack 15.1\n"
        "    bank_name: Optional[str] = None\n"
        "    bank_account: Optional[str] = None\n"
        "    bank_bic: Optional[str] = None\n"
        "    bank_correspondent_account: Optional[str] = None\n"
        "    egryl_extract_date: Optional[date] = None\n"
        "    is_active: Optional[bool] = None\n"
        "    notes: Optional[str] = None",
        "    director_full_name_latin: Optional[str] = None  # Pack 15.1\n"
        "    contract_template_slug: Optional[str] = None  # Pack 29.0\n"
        "    bank_name: Optional[str] = None\n"
        "    bank_account: Optional[str] = None\n"
        "    bank_bic: Optional[str] = None\n"
        "    bank_correspondent_account: Optional[str] = None\n"
        "    egryl_extract_date: Optional[date] = None\n"
        "    is_active: Optional[bool] = None\n"
        "    notes: Optional[str] = None"
    )

    # === 1.4: CompanyRead ===
    replace_in_file(path,
        "    director_full_name_latin: Optional[str] = None  # Pack 15.1\n"
        "    bank_name: str\n"
        "    bank_account: str\n"
        "    bank_bic: str\n"
        "    bank_correspondent_account: Optional[str]\n"
        "    egryl_extract_date: Optional[date]\n"
        "    is_active: bool",
        "    director_full_name_latin: Optional[str] = None  # Pack 15.1\n"
        "    contract_template_slug: Optional[str] = None  # Pack 29.0\n"
        "    bank_name: str\n"
        "    bank_account: str\n"
        "    bank_bic: str\n"
        "    bank_correspondent_account: Optional[str]\n"
        "    egryl_extract_date: Optional[date]\n"
        "    is_active: bool"
    )


def patch_migrations():
    """Add apply_pack29_0_migration() function to db/migrations.py."""
    path = BACKEND / "app" / "db" / "migrations.py"
    print(f"\n[2/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    new_function = '''

# ============================================================================
# Pack 29.0 — Per-company contract template slug
# ============================================================================
def apply_pack29_0_migration():
    """
    Pack 29.0 — добавление company.contract_template_slug + индекс +
    backfill по ИНН для известных компаний.

    Идемпотентна. Применяется при каждом старте через lifespan.
    """
    from sqlalchemy import create_engine, text as sa_text
    from app.config import settings

    # Маппинг ИНН → slug. Должен совпадать с
    # contracts_registry.COMPANY_INN_TO_SLUG (Pack 29.0).
    COMPANY_INN_TO_SLUG = {
        "6168006148": "sk10",
        "9705067089": "ssk",
        "7701411241": "kns_grupp",
        "4003040489": "hayat",
        "7714709349": "avtodom",
        "7727286316": "factor_stroy",
        "7810890724": "protech",
        "7706796034": "buki_vedi",
        "7729634103": "tikompani",
        "7731579629": "king_david",
    }

    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        # 1. ADD COLUMN IF NOT EXISTS
        col_exists = conn.execute(sa_text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'company' AND column_name = 'contract_template_slug'
        """)).first()
        if not col_exists:
            conn.execute(sa_text("""
                ALTER TABLE company
                ADD COLUMN contract_template_slug VARCHAR(64) NULL
            """))
            print("  ✓ Pack 29.0: ADD COLUMN company.contract_template_slug")

        # 2. CREATE INDEX IF NOT EXISTS
        idx_exists = conn.execute(sa_text("""
            SELECT 1 FROM pg_indexes
            WHERE indexname = 'ix_company_contract_template_slug'
        """)).first()
        if not idx_exists:
            conn.execute(sa_text("""
                CREATE INDEX ix_company_contract_template_slug
                ON company (contract_template_slug)
            """))
            print("  ✓ Pack 29.0: CREATE INDEX ix_company_contract_template_slug")

        # 3. Backfill — только для компаний с известным ИНН и пустым slug
        for inn, slug in COMPANY_INN_TO_SLUG.items():
            conn.execute(sa_text("""
                UPDATE company
                SET contract_template_slug = :slug
                WHERE tax_id_primary = :inn
                  AND (contract_template_slug IS NULL OR contract_template_slug = '')
            """), {"slug": slug, "inn": inn})
'''

    # Просто дописываем в конец файла
    text = path.read_text(encoding="utf-8")
    if "apply_pack29_0_migration" in text:
        print("  = apply_pack29_0_migration уже есть, skip")
        return
    path.write_text(text.rstrip() + new_function + "\n", encoding="utf-8")
    print(f"  ✓ Appended apply_pack29_0_migration() to {path.name}")


def patch_main():
    """Add apply_pack29_0_migration to imports + lifespan."""
    path = BACKEND / "app" / "main.py"
    print(f"\n[3/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # === 3.1: добавим в импорт ===
    replace_in_file(path,
        "    apply_pack28_5_migration,\n)",
        "    apply_pack28_5_migration,\n"
        "    apply_pack29_0_migration,\n"
        ")"
    )

    # === 3.2: вызовем в lifespan ===
    replace_in_file(path,
        "    apply_pack28_5_migration()  # Pack 28.5 result_registration_date column",
        "    apply_pack28_5_migration()  # Pack 28.5 result_registration_date column\n"
        "    apply_pack29_0_migration()  # Pack 29.0 company.contract_template_slug + backfill"
    )


def patch_docx_renderer():
    """Rewrite render_contract to use contract template registry."""
    path = BACKEND / "app" / "templates_engine" / "docx_renderer.py"
    print(f"\n[4/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # === 4.1: добавим импорты + класс исключения после TEMPLATES_DIR ===
    replace_in_file(path,
        "TEMPLATES_DIR = Path(__file__).resolve().parents[3] / \"templates\" / \"docx\"\n",
        "TEMPLATES_DIR = Path(__file__).resolve().parents[3] / \"templates\" / \"docx\"\n"
        "REPO_ROOT = Path(__file__).resolve().parents[3]  # Pack 29.0: для resolve_contract_template_path\n"
        "\n"
        "# Pack 29.0: реестр контрактных шаблонов\n"
        "from .contracts_registry import (\n"
        "    resolve_contract_template_path,\n"
        "    is_template_slug_valid,\n"
        "    COMPANY_INN_TO_SLUG,\n"
        "    get_available_template_options,\n"
        ")\n"
        "from fastapi import HTTPException\n"
        "\n"
        "\n"
        "class NeedsContractTemplateError(HTTPException):\n"
        "    \"\"\"\n"
        "    Pack 29.0 — поднимается из render_contract когда у компании не выбран\n"
        "    шаблон договора и ИНН не в COMPANY_INN_TO_SLUG. Frontend ловит 409\n"
        "    и показывает модалку выбора шаблона.\n"
        "    \"\"\"\n"
        "    def __init__(self, company):\n"
        "        super().__init__(\n"
        "            status_code=409,\n"
        "            detail={\n"
        "                \"code\": \"NEEDS_CONTRACT_TEMPLATE\",\n"
        "                \"message\": (\n"
        "                    f\"Для компании '{company.short_name}' (id={company.id}) \"\n"
        "                    f\"не выбран шаблон договора. Выберите шаблон в форме компании.\"\n"
        "                ),\n"
        "                \"company_id\": company.id,\n"
        "                \"company_short_name\": company.short_name,\n"
        "                \"available_templates\": get_available_template_options(),\n"
        "            },\n"
        "        )\n"
    )

    # === 4.2: добавим _render_from_path после _render ===
    replace_in_file(path,
        "def _render(template_name: str, context: dict) -> bytes:\n"
        "    template_path = TEMPLATES_DIR / template_name\n"
        "    if not template_path.exists():\n"
        "        raise FileNotFoundError(f\"Template not found: {template_path}\")\n"
        "\n"
        "    template = DocxTemplate(str(template_path))\n"
        "    template.render(context)\n"
        "\n"
        "    buffer = io.BytesIO()\n"
        "    template.save(buffer)\n"
        "    return buffer.getvalue()\n",
        "def _render(template_name: str, context: dict) -> bytes:\n"
        "    template_path = TEMPLATES_DIR / template_name\n"
        "    if not template_path.exists():\n"
        "        raise FileNotFoundError(f\"Template not found: {template_path}\")\n"
        "\n"
        "    template = DocxTemplate(str(template_path))\n"
        "    template.render(context)\n"
        "\n"
        "    buffer = io.BytesIO()\n"
        "    template.save(buffer)\n"
        "    return buffer.getvalue()\n"
        "\n"
        "\n"
        "def _render_from_repo_path(repo_relative_path: str, context: dict) -> bytes:\n"
        "    \"\"\"\n"
        "    Pack 29.0 — рендер шаблона по пути относительно корня репо\n"
        "    (например 'templates/docx/contracts/by_company/sk10/contract_template.docx').\n"
        "    Используется для контрактных шаблонов, выбираемых через contracts_registry.\n"
        "    \"\"\"\n"
        "    template_path = REPO_ROOT / repo_relative_path\n"
        "    if not template_path.exists():\n"
        "        raise FileNotFoundError(f\"Template not found: {template_path}\")\n"
        "\n"
        "    template = DocxTemplate(str(template_path))\n"
        "    template.render(context)\n"
        "\n"
        "    buffer = io.BytesIO()\n"
        "    template.save(buffer)\n"
        "    return buffer.getvalue()\n"
    )

    # === 4.3: переписываем render_contract ===
    replace_in_file(path,
        "def render_contract(application: Application, session: Session) -> bytes:\n"
        "    context = build_context(application, session)\n"
        "    return _render(\"contract_template.docx\", context)\n",
        "def render_contract(application: Application, session: Session) -> bytes:\n"
        "    \"\"\"\n"
        "    Pack 29.0 — выбор шаблона по company.contract_template_slug:\n"
        "      1. Если slug задан и валиден → шаблон из contracts_registry.\n"
        "      2. Иначе если ИНН компании в COMPANY_INN_TO_SLUG → fallback по ИНН.\n"
        "      3. Иначе → 409 NEEDS_CONTRACT_TEMPLATE (фронт показывает модалку).\n"
        "    \"\"\"\n"
        "    company = application.company\n"
        "    if not is_template_slug_valid(getattr(company, 'contract_template_slug', None)):\n"
        "        if (company.tax_id_primary or '') not in COMPANY_INN_TO_SLUG:\n"
        "            raise NeedsContractTemplateError(company)\n"
        "\n"
        "    context = build_context(application, session)\n"
        "    relative_path = resolve_contract_template_path(company)\n"
        "    return _render_from_repo_path(relative_path, context)\n"
    )


def patch_companies_api():
    """Add GET /admin/companies/contract-templates endpoint."""
    path = BACKEND / "app" / "api" / "companies.py"
    print(f"\n[5/5] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # === 5.1: добавим импорт contracts_registry ===
    replace_in_file(path,
        "from app.services.transliteration import transliterate_name\n",
        "from app.services.transliteration import transliterate_name\n"
        "# Pack 29.0\n"
        "from app.templates_engine.contracts_registry import (\n"
        "    get_available_template_options,\n"
        "    is_template_slug_valid,\n"
        ")\n"
    )

    # === 5.2: добавим endpoint после list_companies ===
    # Вставляем перед "@router.get(\"/{company_id}\""
    new_endpoint = (
        "@router.get(\"/contract-templates\", tags=[\"companies\"])\n"
        "def list_contract_templates(_user=Depends(require_manager)) -> dict:\n"
        "    \"\"\"\n"
        "    Pack 29.0 — список slug-ов контрактных шаблонов для UI dropdown\n"
        "    при создании/редактировании компании.\n"
        "    \"\"\"\n"
        "    return {\"templates\": get_available_template_options()}\n"
        "\n"
        "\n"
        "@router.get(\"/{company_id}\", response_model=CompanyRead)\n"
    )

    replace_in_file(path,
        "@router.get(\"/{company_id}\", response_model=CompanyRead)\n",
        new_endpoint
    )

    # === 5.3: добавим валидацию slug в create_company ===
    replace_in_file(path,
        "    existing = session.exec(\n"
        "        select(Company).where(Company.short_name == payload.short_name)\n"
        "    ).first()\n"
        "    if existing:\n"
        "        raise HTTPException(409, f\"Company '{payload.short_name}' already exists\")",
        "    existing = session.exec(\n"
        "        select(Company).where(Company.short_name == payload.short_name)\n"
        "    ).first()\n"
        "    if existing:\n"
        "        raise HTTPException(409, f\"Company '{payload.short_name}' already exists\")\n"
        "\n"
        "    # Pack 29.0: валидация контрактного шаблона если указан\n"
        "    if payload.contract_template_slug and not is_template_slug_valid(payload.contract_template_slug):\n"
        "        raise HTTPException(\n"
        "            400,\n"
        "            f\"Unknown contract_template_slug: {payload.contract_template_slug}\",\n"
        "        )"
    )

    # === 5.4: то же самое в update_company ===
    replace_in_file(path,
        "    update_data = payload.model_dump(exclude_unset=True)\n"
        "    for key, value in update_data.items():\n"
        "        setattr(company, key, value)",
        "    update_data = payload.model_dump(exclude_unset=True)\n"
        "    # Pack 29.0: валидация контрактного шаблона если меняется\n"
        "    new_slug = update_data.get(\"contract_template_slug\")\n"
        "    if new_slug is not None and new_slug != \"\" and not is_template_slug_valid(new_slug):\n"
        "        raise HTTPException(\n"
        "            400,\n"
        "            f\"Unknown contract_template_slug: {new_slug}\",\n"
        "        )\n"
        "    for key, value in update_data.items():\n"
        "        setattr(company, key, value)"
    )


def main():
    print("=" * 75)
    print("Pack 29.3 — Backend integration of contract templates")
    print("=" * 75)
    print(f"Repo root: {REPO_ROOT}")
    print(f"Backend:   {BACKEND}")

    if not BACKEND.exists():
        print(f"\nERROR: backend dir not found: {BACKEND}")
        sys.exit(1)

    patch_company_model()
    patch_migrations()
    patch_main()
    patch_docx_renderer()
    patch_companies_api()

    print("\n" + "=" * 75)
    print("✅ Pack 29.3 backend integration applied")
    print("=" * 75)
    print("\nNext steps:")
    print("  1. Restart your backend (Railway will auto-restart on push,")
    print("     или перезапустите локально). При старте автоматически применится")
    print("     apply_pack29_0_migration() — добавит колонку contract_template_slug")
    print("     если её ещё нет (но она уже была применена через apply_pack29.ps1).")
    print("  2. Зайдите в /docs — должны увидеть новый endpoint:")
    print("     GET /api/admin/companies/contract-templates")
    print("  3. Сгенерируйте пакет для заявки с привязанной компанией")
    print("     (например СК10 id=2) — контракт должен использовать sk10 шаблон")
    print("     вместо базового contract_template.docx.")
    print("  4. Сгенерируйте пакет для заявки с НЕ привязанной компанией")
    print("     (например MACHINE HEADS id=7) — должен прийти 409 NEEDS_CONTRACT_TEMPLATE.")
    print("  5. Frontend (модалка) — отдельным паком, нужен tree глубже.")


if __name__ == "__main__":
    main()
