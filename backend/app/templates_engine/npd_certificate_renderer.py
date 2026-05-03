"""
Pack 18.3 — Рендер DOCX-шаблона `npd_certificate_template.docx`
(справка о постановке на учёт самозанятого, форма КНД 1122035).

Отдельный модуль чтобы не разрастать docx_renderer.py — справка использует
свой context-builder (`build_npd_certificate_context`), не общий
`build_context`.

Импортируется в:
- app/templates_engine/__init__.py (re-export)
- app/api/applications.py (регистрация в _DOWNLOAD_FILES под id 'npd_certificate')
"""
from __future__ import annotations

import io
from pathlib import Path

from docxtpl import DocxTemplate
from sqlmodel import Session

from app.models import Application

from .context_npd_certificate import build_npd_certificate_context


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "docx"
TEMPLATE_NAME = "npd_certificate_template.docx"


def render_npd_certificate(application: Application, session: Session) -> bytes:
    """
    Рендерит справку КНД 1122035 для applicant'а заявки.

    Может выбросить ValueError если у applicant'а нет ИНН/паспорта/даты НПД —
    endpoint конвертирует это в HTTP 422 с понятным сообщением.

    Возвращает байты DOCX-файла (готовы к стримингу).
    """
    template_path = TEMPLATES_DIR / TEMPLATE_NAME
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    context = build_npd_certificate_context(application, session)

    template = DocxTemplate(str(template_path))
    template.render(context)

    buffer = io.BytesIO()
    template.save(buffer)
    return buffer.getvalue()
