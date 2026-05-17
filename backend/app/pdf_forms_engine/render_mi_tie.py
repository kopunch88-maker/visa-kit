"""
MI-TIE form generator — заполнение AcroForm полей в шаблоне MI_TIE.pdf.

Pack 36.1: новая форма "Solicitud de Tarjeta de Identidad de Extranjero" —
специальная версия от DIRECCIÓN GENERAL DE LA POLICÍA для Ley 14/2013
(Movilidad Internacional). 79 полей: 53 текстовых + 26 чекбоксов.

Заполняется когда у заявки есть NIE (получен после одобрения заявления MI-T)
и fingerprint_date (дата визита в комиссариат для снятия отпечатков).

SITUACIÓN EN ESPAÑA = INVESTIGADOR NACIONAL (по умолчанию для всех клиентов,
проверено на 2 реально сданных кейсах JASHARI и ZAMANLI).

TIPO_DOCUMENTO = INICIAL (первичная выдача карты).

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

    # ============ TIPO DE TARJETA (константа для DN-теletrabajador) ============
    # Pack 36.1: INICIAL — первичная выдача карты
    fields["INICIAL"] = "/On"

    # ============ SITUACIÓN EN ESPAÑA (константа INVESTIGADOR NACIONAL) ========
    # Pack 36.1: по умолчанию INVESTIGADOR NACIONAL (как в 2 реально сданных
    # образцах JASHARI и ZAMANLI). Менять руками в Acrobat при необходимости.
    fields["INVESTIGADOR NACIONAL"] = "/On"

    # ============ DATOS DEL EXTRANJERO/A ============
    if applicant:
        # Паспорт
        fields["PASAPORTE"] = applicant.passport_number or ""

        # NIE (буква-номер-буква)
        nie_letter, nie_number, nie_final = _split_nie(app.nie)
        fields["NIE"] = nie_letter
        fields["NIE_2"] = nie_number
        fields["NIE_3"] = nie_final

        # ФИО
        fields["1er Apellido"] = (applicant.last_name_latin or "").upper()
        fields["2do Apellido"] = ""  # 2-я фамилия для русских отсутствует
        fields["Nombre"] = (applicant.first_name_latin or "").upper()

        # Sexo: H = Hombre, M = Mujer
        if applicant.sex == "H":
            fields["H"] = "/On"
        elif applicant.sex == "M":
            fields["M"] = "/On"

        # Estado civil: S/C/V/D/SP (ВНИМАНИЕ: SP UPPERCASE, см. Инцидент 35)
        ec_map = {
            "S":  "S",   # Soltero
            "C":  "C",   # Casado
            "V":  "V",   # Viudo
            "D":  "D",   # Divorciado
            "Sp": "SP",  # Separado
            # Uh не поддерживается в MI-TIE шаблоне Минюста
        }
        if applicant.marital_status in ec_map:
            fields[ec_map[applicant.marital_status]] = "/On"

        # Дата рождения
        d, m, y = _fmt_date_parts(applicant.birth_date)
        fields["Día"] = d
        fields["Mes"] = m
        fields["Año"] = y

        # País nacimiento + Nacionalidad (Pack 18.10: birth_country отдельно)
        fields["País"] = country_es(applicant.birth_country or applicant.nationality)
        fields["Nacionalidad"] = country_es(applicant.nationality)

        # Имена родителей
        fields["Nombre del padre"] = (applicant.father_name_latin or "").upper()
        fields["Nombre de la madre"] = (applicant.mother_name_latin or "").upper()

        # Контакты
        fields["Tf móvil"] = applicant.phone or ""
        fields["Email"] = (applicant.email or "").upper()

    # ============ Адрес в Испании ============
    if addr:
        fields["Domicilio en España"] = (addr.street or "").upper()
        fields["Numero"] = addr.number or ""
        fields["Piso"] = addr.floor or ""
        fields["Localidad"] = (addr.city or "").upper()
        fields["CP"] = addr.zip or ""
        fields["Provincia"] = (addr.province or "").upper()

    # ============ DATOS DEL REPRESENTANTE A LOS EFECTOS DE PRESENTACIÓN ========
    # Для DN-кейсов представитель — это менеджер визового центра.
    # Заполняется только если есть representative.
    if rep:
        # Razón Social = имя представителя физлица (для юрлица — название компании)
        rep_full_name = f"{rep.first_name or ''} {rep.last_name or ''}".strip().upper()
        fields["NombreRazón Social"] = rep_full_name
        fields["DNI-NIE-PAS"] = (rep.nie or "").upper()

        # Адрес представителя (если есть в БД)
        if hasattr(rep, 'address_street'):
            fields["Domicilio ClPl"] = (getattr(rep, 'address_street', '') or "").upper()
            fields["Numero_2"] = getattr(rep, 'address_number', '') or ""
            fields["Piso_2"] = getattr(rep, 'address_floor', '') or ""
            fields["Localidad_2"] = (getattr(rep, 'address_city', '') or "").upper()
            fields["CP_2"] = getattr(rep, 'address_zip', '') or ""
            fields["Provincia_2"] = (getattr(rep, 'address_province', '') or "").upper()

        fields["Tf móvil_2"] = rep.phone or ""
        fields["Email_2"] = (rep.email or "").upper()

    # ============ DOMICILIO A EFECTOS DE NOTIFICACIONES/COMUNICACIONES ========
    # Для DN-кейсов = адрес в Испании (тот же что у заявителя)
    if addr:
        fields["NombreRazón Social_2"] = ""
        fields["DNI-NIE-PAS_3"] = ""
        fields["Domicilio en España_2"] = (addr.street or "").upper()
        fields["Numero_3"] = addr.number or ""
        fields["Piso_3"] = addr.floor or ""
        fields["Localidad_3"] = (addr.city or "").upper()
        fields["CP_3"] = addr.zip or ""
        fields["Provincia_3"] = (addr.province or "").upper()
        if applicant:
            fields["Tf móvil_3"] = applicant.phone or ""
            fields["Email_3"] = (applicant.email or "").upper()

    # ============ FOOTER: место + дата подписи ============
    # Pack 36.1: дата = fingerprint_date (дата визита в комиссариат)
    # — это и есть момент когда заявитель физически приносит/подписывает форму.
    sign_date = app.fingerprint_date or app.submission_date or date.today()
    sign_city = (addr.city if addr else "BARCELONA") or "BARCELONA"

    fields["Provincia_4"] = sign_city.upper()
    fields["Día_1"] = f"{sign_date.day:02d}"
    fields["Mes_1"] = month_es(sign_date.month)
    fields["Año_1"] = str(sign_date.year)

    # ============ Header (страница 1): DIRIGIDO A ============
    # "BRIGADA DE EXTRANJERÍA DE BARCELONA"
    fields["EXTRANJERÍA"] = sign_city.upper()

    return fields
