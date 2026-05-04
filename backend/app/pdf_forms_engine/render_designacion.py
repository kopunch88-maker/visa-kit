"""
DESIGNACIÓN DE REPRESENTANTE — заполнение AcroForm.

Имена полей плохие (Texto1...Texto40), расшифровка по образцу:
- Texto1-22:  данные заявителя (Solicitante)
- Texto23-35: данные представителя (Representante)
- Texto36-39: место и дата подписи
- Casilla de verificación 1-5: estado civil (S/C/V/D/Sp)
"""

import io
from datetime import date
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter

from app.models import Application, Applicant, Representative, SpainAddress
from .countries_es import country_es, month_es


# Тип авторизации — константа (для DN)
TIPO_AUTORIZACION_TEXT = (
    "AUTORIZACIÓN DE RESIDENCIA DE TELETRABAJADOR DE CARÁCTER INTERNACIONAL"
)


def render_designacion(
    application: Application,
    applicant: Optional[Applicant],
    representative: Optional[Representative],
    spain_address: Optional[SpainAddress],
    template_path: Path,
) -> bytes:
    """Заполняет DESIGNACION_DE_REPRESENTANTE.pdf."""
    reader = PdfReader(str(template_path))
    writer = PdfWriter(clone_from=reader)

    fields = _build_designacion_fields(application, applicant, representative, spain_address)

    for page in writer.pages:
        writer.update_page_form_field_values(page, fields)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _build_designacion_fields(
    app: Application,
    applicant: Optional[Applicant],
    rep: Optional[Representative],
    addr: Optional[SpainAddress],
) -> dict:
    fields: dict = {}

    # ============= Datos del Solicitante (Texto1-Texto22) =============
    if applicant:
        # ФИО (латиница UPPERCASE)
        # Texto1 = Nombre, Texto2 = 1er Apellido, Texto3 = 2º Apellido (пусто)
        fields["Texto1"] = (applicant.first_name_latin or "").upper()
        fields["Texto2"] = (applicant.last_name_latin or "").upper()
        fields["Texto3"] = ""  # 2-я фамилия

        # Гражданство и паспорт
        fields["Texto4"] = country_es(applicant.nationality)  # Nacionalidad
        fields["Texto5"] = ""  # NIE — для первичной всегда пусто
        fields["Texto6"] = applicant.passport_number or ""

        # Дата рождения по частям
        if applicant.birth_date:
            d = applicant.birth_date
            fields["Texto7"] = f"{d.day:02d}"
            fields["Texto8"] = f"{d.month:02d}"
            fields["Texto9"] = str(d.year)
        else:
            fields["Texto7"] = ""
            fields["Texto8"] = ""
            fields["Texto9"] = ""

        # Место рождения
        fields["Texto10"] = (applicant.birth_place_latin or "").upper()
        # Pack 18.10: País de nacimiento — отдельная страна рождения,
        # fallback на nationality для legacy applicant'ов
        fields["Texto11"] = country_es(applicant.birth_country or applicant.nationality)

        # Имена родителей
        fields["Texto12"] = (applicant.father_name_latin or "").upper()
        fields["Texto13"] = (applicant.mother_name_latin or "").upper()

    # Адрес в Испании (для заявителя)
    if addr:
        fields["Texto14"] = (addr.street or "").upper()
        fields["Texto15"] = addr.number or ""
        fields["Texto16"] = addr.floor or ""
        fields["Texto17"] = (addr.city or "").upper()
        fields["Texto18"] = addr.zip or ""
        fields["Texto19"] = (addr.province or "").upper()

    # Контакты заявителя
    if applicant:
        fields["Texto20"] = applicant.phone or ""
        fields["Texto21"] = (applicant.email or "").upper()

    # Тип авторизации
    fields["Texto22"] = TIPO_AUTORIZACION_TEXT

    # ============= Datos del Representante (Texto23-Texto35) =============
    if rep:
        fields["Texto23"] = (rep.nie or "").upper()
        fields["Texto24"] = ""  # Razón Social — для физлица-представителя пусто
        fields["Texto25"] = (rep.first_name or "").upper()
        fields["Texto26"] = (rep.last_name or "").upper()
        fields["Texto27"] = ""  # 2-я фамилия

        # Адрес представителя в Испании
        fields["Texto28"] = (rep.address_street or "").upper()
        fields["Texto29"] = rep.address_number or ""
        fields["Texto30"] = rep.address_floor or ""
        fields["Texto31"] = (rep.address_city or "").upper()
        fields["Texto32"] = rep.address_zip or ""
        fields["Texto33"] = (rep.address_province or "").upper()

        # Контакты представителя
        fields["Texto34"] = rep.phone or ""
        fields["Texto35"] = (rep.email or "").upper()

    # ============= Подпись (Texto36-Texto39) =============
    sign_date = app.submission_date or date.today()
    sign_city = (addr.city if addr else "BARCELONA") or "BARCELONA"

    fields["Texto36"] = sign_city.upper()
    fields["Texto37"] = f"{sign_date.day:02d}"
    fields["Texto38"] = month_es(sign_date.month)
    fields["Texto39"] = str(sign_date.year)
    fields["Texto40"] = ""  # доп. поле — оставляем пустым

    # ============= Estado civil (Casilla de verificación 1-5) =============
    # Casilla 1=Soltero, 2=Casado, 3=Viudo, 4=Divorciado, 5=Separado
    # Для каждой нужно установить '/Yes' если стоит, иначе пусто.
    ec_to_casilla = {
        "S": 1,    # Soltero
        "C": 2,    # Casado
        "V": 3,    # Viudo
        "D": 4,    # Divorciado
        "Sp": 5,   # Separado
    }

    if applicant and applicant.marital_status in ec_to_casilla:
        casilla_num = ec_to_casilla[applicant.marital_status]
        fields[f"Casilla de verificación{casilla_num}"] = "/Yes"

    return fields
