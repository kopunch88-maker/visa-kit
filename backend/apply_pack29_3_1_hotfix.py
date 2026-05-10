# -*- coding: utf-8 -*-
"""
Pack 29.3.1 — Hotfix для render_contract.

Проблема: в Application модели нет relationship 'company', только foreign key
`company_id`. Pack 29.3 предполагал что `application.company` доступен напрямую
— это неверно. Нужно явно загружать Company через session.get().

Также исправляется логирование чтобы render_contract не молчал при ошибках —
build_full_package видимо ловит exception и пропускает файл, из-за чего контракт
просто не попадает в zip.

Применять как обычно через PowerShell.
"""
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(os.environ.get("VISA_REPO_ROOT", r"D:\VISA\visa_kit"))
BACKEND = REPO_ROOT / "backend"


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak_pre_pack29_3_1_{stamp}")
    shutil.copy2(path, bak)
    return bak


def replace_in_file(path: Path, old: str, new: str, count: int = 1) -> bool:
    raw = path.read_bytes()
    has_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    text_lf = text.replace("\r\n", "\n") if has_crlf else text

    occurrences = text_lf.count(old)
    if occurrences == 0:
        print(f"  ✗ NOT FOUND in {path.name}: {old[:60]!r}...")
        return False
    if count == 1 and occurrences > 1:
        print(f"  ✗ AMBIGUOUS in {path.name}: '{old[:60]}...' found {occurrences} times")
        return False

    new_text_lf = text_lf.replace(old, new, count)
    new_text = new_text_lf.replace("\n", "\r\n") if has_crlf else new_text_lf
    path.write_bytes(new_text.encode("utf-8"))
    print(f"  ✓ Patched {path.name}: {occurrences} replacement(s)")
    return True


def patch_docx_renderer():
    """Заменяем application.company → session.get(Company, application.company_id)."""
    path = BACKEND / "app" / "templates_engine" / "docx_renderer.py"
    print(f"\n[1/1] Patching {path.relative_to(REPO_ROOT)}")
    backup(path)

    # Меняем импорт — добавляем Company
    replace_in_file(path,
        "from app.models import Application\n"
        "from .context import build_context\n",
        "from app.models import Application, Company\n"
        "from .context import build_context\n"
    )

    # Меняем render_contract — load Company через session
    replace_in_file(path,
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
        "    return _render_from_repo_path(relative_path, context)\n",

        "def render_contract(application: Application, session: Session) -> bytes:\n"
        "    \"\"\"\n"
        "    Pack 29.0/29.3.1 — выбор шаблона по company.contract_template_slug:\n"
        "      1. Если slug задан и валиден → шаблон из contracts_registry.\n"
        "      2. Иначе если ИНН компании в COMPANY_INN_TO_SLUG → fallback по ИНН.\n"
        "      3. Иначе → 409 NEEDS_CONTRACT_TEMPLATE (фронт показывает модалку).\n"
        "\n"
        "    Pack 29.3.1 fix: Application не имеет relationship 'company',\n"
        "    только foreign key company_id. Загружаем Company явно через session.\n"
        "    \"\"\"\n"
        "    if not application.company_id:\n"
        "        raise ValueError(\n"
        "            f\"Application id={application.id} has no company_id assigned\"\n"
        "        )\n"
        "    company = session.get(Company, application.company_id)\n"
        "    if not company:\n"
        "        raise ValueError(\n"
        "            f\"Company id={application.company_id} not found for \"\n"
        "            f\"application id={application.id}\"\n"
        "        )\n"
        "\n"
        "    if not is_template_slug_valid(getattr(company, 'contract_template_slug', None)):\n"
        "        if (company.tax_id_primary or '') not in COMPANY_INN_TO_SLUG:\n"
        "            raise NeedsContractTemplateError(company)\n"
        "\n"
        "    context = build_context(application, session)\n"
        "    relative_path = resolve_contract_template_path(company)\n"
        "    return _render_from_repo_path(relative_path, context)\n"
    )


def main():
    print("=" * 75)
    print("Pack 29.3.1 — Hotfix: render_contract uses session.get(Company)")
    print("=" * 75)
    print(f"Repo: {REPO_ROOT}")

    if not BACKEND.exists():
        print(f"ERROR: backend dir not found: {BACKEND}")
        sys.exit(1)

    patch_docx_renderer()

    print("\n" + "=" * 75)
    print("✅ Pack 29.3.1 applied")
    print("=" * 75)
    print("\nNext: git commit + git push (Railway re-deploy)")


if __name__ == "__main__":
    main()
