"""
Pack 18.3.3 — Рендер DOCX-шаблона `npd_certificate_lkn_template.docx`
(справка о постановке на учёт самозанятого через ЛКН, форма КНД 1122035).

Отличие от МФЦ-формата (`npd_certificate_template.docx`):
- Нет блока «Документ выведен на бумажный носитель и выдан заявителю...»
- Нет имени МФЦ, адреса МФЦ, Уполномоченного сотрудника МФЦ
- Внизу — синяя плашка электронной подписи ФНС (зашита в шаблоне)

Используется тот же `build_npd_certificate_context()` что и МФЦ —
лишние ключи (`mfc.*`) docxtpl просто игнорирует, это нормально.

Импортируется в:
- app/templates_engine/__init__.py (re-export)
- app/api/applications.py (регистрация в _DOWNLOAD_FILES под id 'npd_certificate_lkn')
- app/api/render_endpoints.py (download-file/npd_certificate_lkn)
"""
from __future__ import annotations

import io
from pathlib import Path

from docxtpl import DocxTemplate
from sqlmodel import Session

from app.models import Application

from .context_npd_certificate import build_npd_certificate_context


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "docx"
TEMPLATE_NAME = "npd_certificate_lkn_template.docx"


def render_npd_certificate_lkn(application: Application, session: Session) -> bytes:
    """
    Рендерит справку КНД 1122035 в формате ЛКН (электронная подпись ФНС внизу).

    Параметры и контракт ошибок идентичны render_npd_certificate (МФЦ-формат):
    может выбросить ValueError если у applicant'а нет ИНН/паспорта/даты НПД —
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
