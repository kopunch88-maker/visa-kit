"""
PDF forms builder — собирает все 4 испанские формы для одной заявки.

Возвращает dict {filename: bytes}, который потом добавляется в общий ZIP пакета.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from sqlmodel import Session

from app.models import Application, Applicant, Representative, SpainAddress
from .render_mi_t import render_mi_t
from .render_designacion import render_designacion
from .render_compromiso import render_compromiso
from .render_declaracion import render_declaracion

log = logging.getLogger(__name__)


# Пути к шаблонам (относительно корня проекта visa_kit/)
TEMPLATES_PDF_DIR = Path("templates") / "pdf"
MI_T_TEMPLATE = "MI_T.pdf"
DESIGNACION_TEMPLATE = "DESIGNACION DE REPRESENTANTE. Editable.pdf"


def build_pdf_forms(
    application: Application,
    session: Session,
    templates_root: Optional[Path] = None,
) -> Dict[str, bytes]:
    """
    Генерирует все 4 PDF-формы для заявки.

    Args:
        application: заявка с заполненными связями
        session: SQLModel сессия (нужна для подгрузки applicant/representative/spain_address)
        templates_root: путь к папке templates/. Если None — берётся ./templates от cwd.

    Returns:
        dict {filename: bytes} с 4 PDF файлами
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

    # 13. Compromiso de alta en SS (RETA) — генерация с нуля
    try:
        result["13_Compromiso_RETA.pdf"] = render_compromiso(
            application, applicant, spain_address
        )
    except Exception as e:
        log.exception(f"Failed to render Compromiso: {e}")

    # 14. Declaración responsable — генерация с нуля
    try:
        result["14_Declaracion_antecedentes.pdf"] = render_declaracion(
            application, applicant, spain_address
        )
    except Exception as e:
        log.exception(f"Failed to render Declaración: {e}")

    log.info(f"Generated {len(result)} PDF forms for application #{application.id}")
    return result
