"""
Rendering service — собирает полный пакет документов для заявки.

Pack 9: добавлены 4 испанских PDF-формы в подпапку forms_es/.
Pack 23.5: добавлены 3 DOCX в корень ZIP — справка НПД (МФЦ), справка НПД (ЛКН),
           апостиль. До этого они были доступны только через одиночное скачивание
           карточки в DocumentsGrid, но в общий ZIP-архив не попадали.

Структура ZIP:
    /                          ← корень: 13 русских DOCX
    01_Договор.docx
    02_Акт_1.docx
    ...
    10_Выписка_по_счету.docx
    15_Справка_НПД.docx                ← Pack 23.5
    15b_Справка_НПД_ЛКН.docx           ← Pack 23.5
    16_Апостиль.docx                   ← Pack 23.5
    /forms_es/                 ← подпапка: 4 испанских PDF
        11_MI-T.pdf
        12_Designacion_representante.pdf
        13_Compromiso_RETA.pdf
        14_Declaracion_antecedentes.pdf
"""
import io
import zipfile
import logging
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from app.models import Application
from app.templates_engine import (
    render_contract, render_act, render_invoice,
    render_employer_letter, render_cv, render_bank_statement,
    # Pack 23.5: справки НПД и апостиль (раньше были только через download-file)
    render_npd_certificate,
    render_npd_certificate_lkn,
    render_apostille,
)
from app.pdf_forms_engine import build_pdf_forms

logger = logging.getLogger(__name__)


def _try_render(name: str, fn, *args) -> Optional[bytes]:
    try:
        return fn(*args)
    except FileNotFoundError as e:
        logger.warning(f"[{name}] template not found: {e}")
        return None
    except Exception as e:
        logger.error(f"[{name}] render failed: {type(e).__name__}: {e}")
        return None


def build_full_package(
    application: Application,
    session: Session,
    include_bank_statement: bool = True,
    include_pdf_forms: bool = True,
) -> tuple[bytes, dict]:
    """
    Собирает ZIP-архив с документами заявки.

    Args:
        application: Application instance
        session: DB session
        include_bank_statement: True по умолчанию. Если выписка не нужна — False
        include_pdf_forms: True по умолчанию (Pack 9). Включает 4 испанские PDF-формы

    Returns:
        (zip_bytes, status_dict)
    """
    files_to_render = [
        ("01_Договор.docx", "contract", render_contract, (application, session)),
        ("02_Акт_1.docx", "act_1", render_act, (application, session, 1)),
        ("03_Акт_2.docx", "act_2", render_act, (application, session, 2)),
        ("04_Акт_3.docx", "act_3", render_act, (application, session, 3)),
        ("05_Счет_1.docx", "invoice_1", render_invoice, (application, session, 1)),
        ("06_Счет_2.docx", "invoice_2", render_invoice, (application, session, 2)),
        ("07_Счет_3.docx", "invoice_3", render_invoice, (application, session, 3)),
        ("08_Письмо_от_компании.docx", "employer_letter", render_employer_letter, (application, session)),
        ("09_Резюме.docx", "cv", render_cv, (application, session)),
    ]

    if include_bank_statement:
        files_to_render.append(
            ("10_Выписка_по_счету.docx", "bank_statement",
             render_bank_statement, (application, session))
        )

    # Pack 23.5: справки НПД и апостиль.
    # Кладём ПОСЛЕ выписки и ДО pdf-форм, чтобы порядок в ZIP совпадал
    # с нумерацией в DocumentsGrid (15, 15b, 16).
    # _try_render проглатывает FileNotFoundError и любые ошибки рендера —
    # если у заявки нет данных для апостиля или шаблон отсутствует,
    # карточка просто пропускается, заявка не падает.
    files_to_render.extend([
        ("15_Справка_НПД.docx", "npd_certificate",
         render_npd_certificate, (application, session)),
        ("15b_Справка_НПД_ЛКН.docx", "npd_certificate_lkn",
         render_npd_certificate_lkn, (application, session)),
        ("16_Апостиль.docx", "apostille",
         render_apostille, (application, session)),
    ])

    # Корректируем под payments_period_months
    months_count = application.payments_period_months or 3
    filtered = []
    for entry in files_to_render:
        filename, status_key, fn, args = entry
        if status_key.startswith("act_") or status_key.startswith("invoice_"):
            try:
                seq = int(status_key.split("_")[1])
                if seq > months_count:
                    continue
            except (IndexError, ValueError):
                pass
        filtered.append(entry)

    status: dict[str, str] = {}
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # === DOCX в корне ZIP (как было) ===
        for filename, status_key, fn, args in filtered:
            content = _try_render(status_key, fn, *args)
            if content is None:
                status[status_key] = "skipped"
                continue
            zf.writestr(filename, content)
            status[status_key] = "ok"

        # === Pack 9: испанские PDF-формы в forms_es/ ===
        if include_pdf_forms:
            try:
                # Шаблоны лежат в visa_kit/templates/pdf/ — на уровень выше backend/
                # Cwd = D:\VISA\visa_kit\backend\, нужен путь D:\VISA\visa_kit\templates\
                templates_root = Path(__file__).resolve().parent.parent.parent.parent / "templates"
                pdf_forms = build_pdf_forms(application, session, templates_root)
                for filename, pdf_bytes in pdf_forms.items():
                    zf.writestr(f"forms_es/{filename}", pdf_bytes)
                    # ключ статуса = имя без расширения, для удобства
                    status_key = filename.rsplit(".", 1)[0]
                    status[status_key] = "ok"
                if not pdf_forms:
                    status["pdf_forms"] = "skipped (no templates found)"
            except Exception as e:
                logger.exception(f"PDF forms generation failed: {e}")
                status["pdf_forms"] = f"error: {type(e).__name__}: {e}"

    buffer.seek(0)
    return buffer.getvalue(), status
