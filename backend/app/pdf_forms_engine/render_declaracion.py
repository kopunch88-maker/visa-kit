"""
DECLARACIÓN RESPONSABLE DE CARECER DE ANTECEDENTES PENALES — ReportLab генерация.

Простая декларация с подстановкой:
- ФИО, гражданство, паспорт
- Адрес в Испании (улица + номер + этаж)
- C.P., город
- Город и дата подписания
"""

import io
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.models import Application, Applicant, SpainAddress
from .countries_es import country_es, month_es_lower
from .fonts import BODY_FONT, BODY_FONT_BOLD


def render_declaracion(
    application: Application,
    applicant: Optional[Applicant],
    spain_address: Optional[SpainAddress],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Heading1"],
        fontSize=13, alignment=TA_CENTER, spaceAfter=24,
        fontName=BODY_FONT_BOLD,
    )
    label_style = ParagraphStyle(
        "label", parent=styles["Normal"],
        fontSize=11, alignment=TA_LEFT, spaceAfter=8, leading=15,
        fontName=BODY_FONT,
    )
    body_style = ParagraphStyle(
        "body", parent=styles["Normal"],
        fontSize=11, alignment=TA_JUSTIFY,
        spaceBefore=18, spaceAfter=10, leading=15,
        fontName=BODY_FONT,
    )
    sign_style = ParagraphStyle(
        "sign", parent=styles["Normal"],
        fontSize=11, alignment=TA_LEFT,
        spaceBefore=30, spaceAfter=8,
        fontName=BODY_FONT,
    )

    # Данные
    full_name = _full_name_latin(applicant)
    nationality = country_es(applicant.nationality) if applicant else ""
    # В образце: "AZERBAIYAN" (всё капсом). Применим тот же стиль.
    passport = applicant.passport_number if applicant else ""

    # Адрес: "Carrer de Balmes, 128, 3º 2" — используем как есть из БД
    addr_line = ""
    if spain_address:
        parts = []
        if spain_address.street:
            parts.append(spain_address.street)
        if spain_address.number:
            parts.append(spain_address.number)
        if spain_address.floor:
            parts.append(f"{spain_address.floor}")
        addr_line = ", ".join(parts)

    cp = spain_address.zip if spain_address else ""
    city = (spain_address.city if spain_address else "Barcelona") or "Barcelona"

    sign_date = application.submission_date or date.today()
    date_text = f"{sign_date.day:02d} de {month_es_lower(sign_date.month)} de {sign_date.year}"

    story = []
    story.append(Paragraph(
        "DECLARACIÓN RESPONSABLE DE CARECER DE ANTECEDENTES PENALES",
        title_style,
    ))

    # Блок с данными
    story.append(Paragraph(f"<b>Nombre y apellidos:</b> {full_name}", label_style))
    story.append(Paragraph(f"<b>Nacionalidad:</b> {nationality}", label_style))
    story.append(Paragraph(f"<b>Pasaporte:</b> {passport}", label_style))
    story.append(Paragraph(f"<b>Domicilio:</b> {addr_line}", label_style))
    story.append(Paragraph(f"<b>C.P.:</b> {cp}", label_style))
    story.append(Paragraph(f"<b>Localidad:</b> {city}, España", label_style))

    # Текст декларации
    story.append(Paragraph(
        "<b>DECLARO BAJO MI RESPONSABILIDAD</b> que no tengo antecedentes penales "
        "ni en España ni en los países donde he residido en los últimos cinco años "
        "anteriores a la fecha de la presente declaración.",
        body_style,
    ))

    story.append(Paragraph(
        "La presente declaración se formula a mi leal saber y entender.",
        body_style,
    ))

    # Подпись
    story.append(Paragraph(f"En {city}, a {date_text}", sign_style))
    story.append(Spacer(1, 30))
    story.append(Paragraph("Firma", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


def _full_name_latin(applicant: Optional[Applicant]) -> str:
    if not applicant:
        return ""
    parts = [applicant.last_name_latin, applicant.first_name_latin]
    return " ".join(p.upper() for p in parts if p)
