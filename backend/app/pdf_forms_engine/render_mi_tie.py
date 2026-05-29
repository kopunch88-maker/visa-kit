"""
MI-TIE form generator — заполнение AcroForm полей в шаблоне MI_TIE.pdf.

Pack 36.1: новая форма "Solicitud de Tarjeta de Identidad de Extranjero" —
специальная версия от DIRECCIÓN GENERAL DE LA POLICÍA для Ley 14/2013
(Movilidad Internacional). 79 полей.

Заполняется когда у заявки есть NIE (получен после одобрения заявления MI-T)
и fingerprint_date (дата визита в комиссариат для снятия отпечатков).

SITUACIÓN EN ESPAÑA = INVESTIGADOR NACIONAL (по умолчанию для всех клиентов).
TIPO_DOCUMENTO = INICIAL (первичная выдача карты).

Pack 36.1.4: после консультации с полицией заполняются ТОЛЬКО блоки:
  - SOLICITUD DE TARJETA DE IDENTIDAD DE EXTRANJERO (INICIAL)
  - SITUACIÓN EN ESPAÑA (INVESTIGADOR NACIONAL)
  - DATOS DEL EXTRANJERO/A
  - DIRIGIDO A: ... DE <город>
  - Дата подписи (fingerprint_date)

Блоки DATOS DEL REPRESENTANTE и DOMICILIO A EFECTOS DE NOTIFICACIONES
оставляем ПУСТЫМИ — полиция вписывает от руки при необходимости.

В конце pipeline — flatten_pdf_form() для корректного рендера на
iOS/Telegram preview (см. Инцидент 35 в PROJECT_STATE).
"""

import io
from datetime import date
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter

from app.models import Application, Applicant, Representative, SpainAddress
from .countries_es import country_es, month_es
from .flatten_form import flatten_pdf_form


from .submission_location import submission_city_province

def render_mi_tie(
    application: Application,
    applicant: Optional[Applicant],
    representative: Optional[Representative],
    spain_address: Optional[SpainAddress],
    template_path: Path,
) -> bytes:
    """Заполняет MI_TIE.pdf данными из заявки. Возвращает bytes готового PDF."""
    reader = PdfReader(str(template_path))
    writer = PdfWriter(clone_from=reader)

    fields = _build_mi_tie_fields(application, applicant, representative, spain_address)

    for page in writer.pages:
        writer.update_page_form_field_values(page, fields)

    buf = io.BytesIO()
    writer.write(buf)

    return flatten_pdf_form(buf.getvalue())


def _fmt_date_parts(d: Optional[date]) -> tuple[str, str, str]:
    if not d:
        return "", "", ""
    return f"{d.day:02d}", f"{d.month:02d}", str(d.year)


def _split_nie(nie: Optional[str]) -> tuple[str, str, str]:
    """
    NIE формат: 'Z3751311Q' → ('Z', '3751311', 'Q').
    Допускает пробелы и дефисы.
    """
    if not nie:
        return "", "", ""
    s = nie.replace(" ", "").replace("-", "").upper()
    if len(s) < 3:
        return s, "", ""
    return s[0], s[1:-1], s[-1]


def _build_mi_tie_fields(
    app: Application,
    applicant: Optional[Applicant],
    rep: Optional[Representative],
    addr: Optional[SpainAddress],
) -> dict:
    """Маппинг данных в имена полей PDF (MI-TIE)."""

    fields: dict = {}

    # ============ TIPO DE TARJETA ============
    fields["INICIAL"] = "/On"

    # ============ SITUACIÓN EN ESPAÑA ============
    fields["INVESTIGADOR NACIONAL"] = "/On"

    # ============ DATOS DEL EXTRANJERO/A ============
    if applicant:
        fields["PASAPORTE"] = applicant.passport_number or ""

        # NIE (буква-номер-буква)
        nie_letter, nie_number, nie_final = _split_nie(app.nie)
        fields["NIE"] = nie_letter
        fields["NIE_2"] = nie_number
        fields["NIE_3"] = nie_final

        fields["1er Apellido"] = (applicant.last_name_latin or "").upper()
        fields["2do Apellido"] = ""
        fields["Nombre"] = (applicant.first_name_latin or "").upper()

        # Sexo: H = Hombre, M = Mujer
        if applicant.sex == "H":
            fields["H"] = "/On"
        elif applicant.sex == "M":
            fields["M"] = "/On"

        # Estado civil: S/C/V/D/SP (SP UPPERCASE — см. Инцидент 35)
        ec_map = {
            "S":  "S",
            "C":  "C",
            "V":  "V",
            "D":  "D",
            "Sp": "SP",
        }
        if applicant.marital_status in ec_map:
            fields[ec_map[applicant.marital_status]] = "/On"

        # Дата рождения
        d, m, y = _fmt_date_parts(applicant.birth_date)
        fields["Día"] = d
        fields["Mes"] = m
        fields["Año"] = y

        fields["País"] = country_es(applicant.birth_country or applicant.nationality)
        fields["Nacionalidad"] = country_es(applicant.nationality)

        fields["Nombre del padre"] = (applicant.father_name_latin or "").upper()
        fields["Nombre de la madre"] = (applicant.mother_name_latin or "").upper()

        fields["Tf móvil"] = applicant.phone or ""
        fields["Email"] = (applicant.email or "").upper()

    # ============ Адрес заявителя в Испании ============
    if addr:
        fields["Domicilio en España"] = (addr.street or "").upper()
        fields["Numero"] = addr.number or ""
        fields["Piso"] = addr.floor or ""
        fields["Localidad"] = (addr.city or "").upper()
        fields["CP"] = addr.zip or ""
        fields["Provincia"] = (addr.province or "").upper()

    # ============ Pack 36.1.4: секции REPRESENTANTE и NOTIFICACIONES =========
    # Оставляем ПУСТЫМИ — после консультации с полицией решено что эти блоки
    # не нужны. Если потребуется — заполнят от руки.

    # ============ FOOTER: место + дата подписи ============
    sign_date = app.fingerprint_date or app.submission_date or date.today()
    _sub_city, _sub_prov = submission_city_province(app, addr)  # Pack 50.38-A2
    sign_city = _sub_city or "BARCELONA"

    fields["Provincia_4"] = sign_city.upper()
    fields["Día_1"] = f"{sign_date.day:02d}"
    fields["Mes_1"] = month_es(sign_date.month)
    fields["Año_1"] = str(sign_date.year)

    # Header (страница 1): DIRIGIDO A ... BRIGADA DE EXTRANJERÍA DE <город>
    fields["EXTRANJERÍA"] = sign_city.upper()

    return fields
