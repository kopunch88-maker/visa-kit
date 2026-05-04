"""
Pack 18.9 — Рендер DOCX-шаблона `apostille_template.docx`
(апостиль к справке о постановке на учёт самозанятого).

Использует context_apostille.build_apostille_context(), который сам зависит
от context_npd_certificate (для подписанта МФЦ и даты выдачи справки).

Импортируется в:
- app/templates_engine/__init__.py (re-export)
- app/api/applications.py (регистрация в _DOWNLOAD_FILES под id 'apostille')
- app/api/render_endpoints.py (download endpoint)
"""
from __future__ import annotations

import io
from pathlib import Path

from docxtpl import DocxTemplate
from sqlmodel import Session

from app.models import Application

from .context_apostille import build_apostille_context


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "docx"
TEMPLATE_NAME = "apostille_template.docx"


def render_apostille(application: Application, session: Session) -> bytes:
    """
    Рендерит апостиль к справке КНД 1122035.

    Может выбросить ValueError если у applicant'а нет ИНН/паспорта/даты НПД
    (как и render_npd_certificate — это зависит от того же контекст-генератора
    через цепочку context_npd_certificate).

    Возвращает байты DOCX-файла.
    """
    template_path = TEMPLATES_DIR / TEMPLATE_NAME
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    context = build_apostille_context(application, session)

    template = DocxTemplate(str(template_path))
    template.render(context)

    buffer = io.BytesIO()
    template.save(buffer)
    return buffer.getvalue()
