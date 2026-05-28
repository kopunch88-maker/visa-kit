"""
PDF forms builder — собирает все 6 испанских форм для одной заявки.

Возвращает dict {filename: bytes}, который потом добавляется в общий ZIP пакета.

Pack 36.0: flatten_pdf_form() для рендера на iOS/Telegram preview.
Pack 36.1: добавлены 15_MI-TIE.pdf и 16_EX-17.pdf — генерятся только если
у заявки заполнены application.nie И application.fingerprint_date
(обычно после одобрения заявления MI-T и получения уведомления от полиции).
Без этих полей просто пропускаются (skip с info-логом).
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from sqlmodel import Session

from app.models import Application, Applicant, Representative, SpainAddress, ApplicationType  # Pack 50.19
from .flatten_form import flatten_pdf_form
from .render_mi_t import render_mi_t
from .render_designacion import render_designacion
from .render_compromiso import render_compromiso
from .render_declaracion import render_declaracion
from .render_mi_tie import render_mi_tie    # Pack 36.1
from .render_ex17 import render_ex17        # Pack 36.1

log = logging.getLogger(__name__)


# Пути к шаблонам (относительно корня проекта visa_kit/)
TEMPLATES_PDF_DIR = Path("templates") / "pdf"
MI_T_TEMPLATE = "MI_T.pdf"
DESIGNACION_TEMPLATE = "DESIGNACION DE REPRESENTANTE. Editable.pdf"
MI_TIE_TEMPLATE = "MI_TIE.pdf"    # Pack 36.1
EX_17_TEMPLATE = "EX_17.pdf"      # Pack 36.1


def build_pdf_forms(
    application: Application,
    session: Session,
    templates_root: Optional[Path] = None,
) -> Dict[str, bytes]:
    """
    Генерирует все испанские PDF-формы для заявки.

    Args:
        application: заявка с заполненными связями
        session: SQLModel сессия (нужна для подгрузки applicant/representative/spain_address)
        templates_root: путь к папке templates/. Если None — берётся ./templates от cwd.

    Returns:
        dict {filename: bytes} с 4-6 PDF файлами (15 и 16 — только при наличии
        nie + fingerprint_date в заявке).
    """
    if templates_root is None:
        templates_root = Path("templates")

    pdf_dir = templates_root / "pdf"
    if not pdf_dir.exists():
        log.warning(f"PDF templates directory not found: {pdf_dir}. "
                    f"PDF forms will be skipped.")
        return {}

    # Подгружаем связанные сущности
    applicant: Optional[Applicant] = None
    if application.applicant_id:
        applicant = session.get(Applicant, application.applicant_id)

    representative: Optional[Representative] = None
    if application.representative_id:
        representative = session.get(Representative, application.representative_id)

    spain_address: Optional[SpainAddress] = None
    if application.spain_address_id:
        spain_address = session.get(SpainAddress, application.spain_address_id)

    result: Dict[str, bytes] = {}

    # 11. MI-T
    try:
        mi_t_path = pdf_dir / MI_T_TEMPLATE
        if mi_t_path.exists():
            result["11_MI-T.pdf"] = render_mi_t(
                application, applicant, representative, spain_address, mi_t_path
            )
        else:
            log.warning(f"MI-T template not found: {mi_t_path}")
    except Exception as e:
        log.exception(f"Failed to render MI-T: {e}")

    # 12. Designación de representante
    try:
        des_path = pdf_dir / DESIGNACION_TEMPLATE
        if des_path.exists():
            result["12_Designacion_representante.pdf"] = render_designacion(
                application, applicant, representative, spain_address, des_path
            )
        else:
            log.warning(f"Designación template not found: {des_path}")
    except Exception as e:
        log.exception(f"Failed to render Designación: {e}")

    # 13. Compromiso de alta en SS (RETA) — генерация с нуля.
    # Pack 50.19 — только для самозанятых; для НАЙМА (EMPLOYMENT) не нужна.
    if application.application_type != ApplicationType.EMPLOYMENT:
        try:
            compromiso_bytes = render_compromiso(application, applicant, spain_address)
            result["13_Compromiso_RETA.pdf"] = flatten_pdf_form(compromiso_bytes)
        except Exception as e:
            log.exception(f"Failed to render Compromiso: {e}")

    # 14. Declaración responsable — генерация с нуля.
    try:
        declaracion_bytes = render_declaracion(application, applicant, spain_address)
        result["14_Declaracion_antecedentes.pdf"] = flatten_pdf_form(declaracion_bytes)
    except Exception as e:
        log.exception(f"Failed to render Declaración: {e}")

    # === Pack 36.1: 15-16 TIE формы ===
    # Генерятся только если application.nie И application.fingerprint_date
    # заполнены (после одобрения MI-T и получения NIE от полиции).
    has_tie_data = bool(
        getattr(application, "nie", None) and
        getattr(application, "fingerprint_date", None)
    )

    if has_tie_data:
        # 15. MI-TIE (специальная для Ley 14/2013)
        try:
            mi_tie_path = pdf_dir / MI_TIE_TEMPLATE
            if mi_tie_path.exists():
                result["15_MI-TIE.pdf"] = render_mi_tie(
                    application, applicant, representative, spain_address, mi_tie_path
                )
            else:
                log.warning(f"MI-TIE template not found: {mi_tie_path}")
        except Exception as e:
            log.exception(f"Failed to render MI-TIE: {e}")

        # 16. EX-17 (универсальная от МВД)
        try:
            ex17_path = pdf_dir / EX_17_TEMPLATE
            if ex17_path.exists():
                result["16_EX-17.pdf"] = render_ex17(
                    application, applicant, representative, spain_address, ex17_path
                )
            else:
                log.warning(f"EX-17 template not found: {ex17_path}")
        except Exception as e:
            log.exception(f"Failed to render EX-17: {e}")
    else:
        log.info(
            f"Application #{application.id}: skipping MI-TIE/EX-17 "
            f"(nie or fingerprint_date not set)"
        )

    log.info(f"Generated {len(result)} PDF forms for application #{application.id}")
    return result
