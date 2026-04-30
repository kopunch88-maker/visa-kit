"""
COMPROMISO DE ALTA EN LA SEGURIDAD SOCIAL — генерация с нуля через ReportLab.

Это простой текстовый документ. Шаблон фиксирован, подставляем только:
- Имя клиента (UPPERCASE латиница)
- Номер паспорта
- Город подписания
- Дата подписания (DD.MM.YYYY)
"""

import io
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.models import Application, Applicant, SpainAddress
from .fonts import BODY_FONT, BODY_FONT_BOLD


def render_compromiso(
    application: Application,
    applicant: Optional[Applicant],
    spain_address: Optional[SpainAddress],
) -> bytes:
    """Генерирует PDF Compromiso. Возвращает bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Heading1"],
        fontSize=14, alignment=TA_LEFT, spaceAfter=4,
        fontName=BODY_FONT_BOLD,
    )
    subtitle_style = ParagraphStyle(
        "subtitle", parent=styles["Normal"],
        fontSize=11, alignment=TA_LEFT, spaceAfter=18,
        fontName=BODY_FONT,
    )
    body_style = ParagraphStyle(
        "body", parent=styles["Normal"],
        fontSize=11, alignment=TA_JUSTIFY,
        spaceAfter=10, leading=15,
        fontName=BODY_FONT,
    )
    bullet_style = ParagraphStyle(
        "bullet", parent=body_style,
        leftIndent=18,
    )
    sign_style = ParagraphStyle(
        "sign", parent=styles["Normal"],
        fontSize=11, alignment=TA_LEFT,
        spaceBefore=24, spaceAfter=8,
        fontName=BODY_FONT,
    )

    full_name = _full_name_latin(applicant)
    passport = applicant.passport_number if applicant else ""
    city = (spain_address.city if spain_address else "Barcelona") or "Barcelona"
    sign_date = application.submission_date or date.today()
    date_str = f"{sign_date.day:02d}.{sign_date.month:02d}.{sign_date.year}"

    story = []
    story.append(Paragraph("COMPROMISO DE ALTA EN LA SEGURIDAD SOCIAL", title_style))
    story.append(Paragraph("Modalidad: Trabajador Autónomo (RETA)", subtitle_style))

    story.append(Paragraph(
        f"Yo, <b>{full_name}</b>, con pasaporte número <b>{passport}</b>, manifiesto "
        f"mediante este escrito mi compromiso expreso de realizar mi alta en la "
        f"Seguridad Social española como trabajador autónomo (RETA) una vez me sea "
        f"concedida y notificada la Autorización de Residencia como Trabajador de "
        f"Carácter Internacional (Nómada Digital) solicitada ante la Unidad de "
        f"Grandes Empresas (UGE).",
        body_style,
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Declaro que:", body_style))

    story.append(Paragraph(
        "•&nbsp;&nbsp;Me daré de alta en la Seguridad Social dentro del plazo legal "
        "establecido, una vez se emita la resolución favorable.",
        bullet_style,
    ))
    story.append(Paragraph(
        "•&nbsp;&nbsp;Cumpliré con todas las obligaciones correspondientes al régimen "
        "de autónomos, incluyendo la cotización mensual y demás responsabilidades legales.",
        bullet_style,
    ))

    story.append(Paragraph(
        "Este compromiso se presenta como documentación adicional requerida para la "
        "tramitación del expediente ante UGE.",
        body_style,
    ))

    story.append(Paragraph(f"En {city}, {date_str}", sign_style))
    story.append(Paragraph(f"<b>{full_name}</b>", sign_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Firma:", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


def _full_name_latin(applicant: Optional[Applicant]) -> str:
    """LASTNAME FIRSTNAME (UPPERCASE)."""
    if not applicant:
        return ""
    parts = [applicant.last_name_latin, applicant.first_name_latin]
    return " ".join(p.upper() for p in parts if p)
