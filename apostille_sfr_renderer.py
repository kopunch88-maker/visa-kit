"""
Pack 50.20 — Рендер DOCX-шаблона `apostille_sfr_template.docx`
(апостиль Минфина/СФР для НАЙМА).

По аналогии с apostille_renderer.py (апостиль самозанятого).
Использует context_apostille_sfr.build_apostille_sfr_context().

Импортируется в:
- app/templates_engine/__init__.py (re-export)
- app/api/applications.py (регистрация в _DOWNLOAD_FILES под id 'apostille_sfr')
- app/services/rendering.py (pipeline, naimOnly)
"""
from __future__ import annotations

import io
from pathlib import Path

from docxtpl import DocxTemplate
from sqlmodel import Session

from app.models import Application

from .context_apostille_sfr import build_apostille_sfr_context


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "docx"
TEMPLATE_NAME = "apostille_sfr_template.docx"


def render_apostille_sfr(application: Application, session: Session) -> bytes:
    """Рендерит апостиль Минфина/СФР (найм). Возвращает байты DOCX."""
    template_path = TEMPLATES_DIR / TEMPLATE_NAME
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    context = build_apostille_sfr_context(application, session)

    template = DocxTemplate(str(template_path))
    template.render(context)

    buffer = io.BytesIO()
    template.save(buffer)
    return buffer.getvalue()
