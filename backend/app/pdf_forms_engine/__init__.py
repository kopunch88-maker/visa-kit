"""
PDF Forms Engine — генерация испанских PDF-форм для DN-визы.

4 формы:
- MI-T  — solicitud de autorización (через AcroForm-заполнение)
- DESIGNACION DE REPRESENTANTE — назначение представителя (AcroForm)
- COMPROMISO DE ALTA EN LA SEGURIDAD SOCIAL — обязательство (генерация с нуля через ReportLab)
- DECLARACION RESPONSABLE DE CARECER DE ANTECEDENTES — декларация (ReportLab)

Использование:
    from app.pdf_forms_engine import build_pdf_forms

    forms_dict = build_pdf_forms(application, session)
    # → {"11_MI-T.pdf": bytes, "12_Designacion.pdf": bytes, ...}
"""

from .builder import build_pdf_forms

__all__ = ["build_pdf_forms"]
