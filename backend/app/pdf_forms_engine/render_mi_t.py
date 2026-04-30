"""
MI-T form generator — заполнение AcroForm полей в шаблоне MI_T.pdf.

Поля формы (55 шт.) сгруппированы:
- TIPO_AUTORIZACION (4 чекбокса константы)
- DEX_*  — данные иностранца (24 поля)
- DEE_*  — данные испанской компании (16 полей, все пустые для DN)
- DR_*   — данные представителя (5 полей)
- NRC_TITULAR + FIR_*  — оплата и подпись
"""

import io
from datetime import date
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject

from app.models import Application, Applicant, Representative, SpainAddress
from .countries_es import country_es


def render_mi_t(
    application: Application,
    applicant: Optional[Applicant],
    representative: Optional[Representative],
    spain_address: Optional[SpainAddress],
    template_path: Path,
) -> bytes:
    """
    Заполняет MI-T.pdf данными из заявки. Возвращает bytes готового PDF.
    """
    reader = PdfReader(str(template_path))
    writer = PdfWriter(clone_from=reader)

    # Собираем все значения
    fields = _build_mi_t_fields(application, applicant, representative, spain_address)

    # Заполняем все страницы (обычно одна, но на всякий случай)
    for page in writer.pages:
        writer.update_page_form_field_values(page, fields)

    # Вытаскиваем bytes
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _fmt_date_parts(d: Optional[date]) -> tuple[str, str, str]:
    """date → ('09', '03', '1963'). Если None — пустые строки."""
    if not d:
        return "", "", ""
    return f"{d.day:02d}", f"{d.month:02d}", str(d.year)


def _build_mi_t_fields(
    app: Application,
    applicant: Optional[Applicant],
    rep: Optional[Representative],
    addr: Optional[SpainAddress],
) -> dict:
    """Маппинг данных в имена полей PDF."""

    fields: dict = {}

    # ============= TIPO DE AUTORIZACIÓN (константы для DN) =============
    # SA = Solicitud de Autorización: TCI = Teletrabajador Carácter Internacional
    # TA = Tipo de Autorización: INI = Inicial
    # SUB-тип: TAEE = Titular de Autorización de Estancia en España (типичный кейс)
    # Эти 4 значения — константы.
    fields["SA"] = "/SA_TCI"
    fields["SA_SUB"] = ""  # под-флаг для INVERSOR / I+D и т.д. — не для DN
    fields["TA"] = "/TA_INI"
    fields["TA_SUB"] = "/TA_INI_TAEE"

    # ============= DEX: Datos del extranjero =============
    if applicant:
        # Паспорт
        fields["DEX_PASA"] = applicant.passport_number or ""
        # NIE — для первичной подачи всегда пусто
        fields["DEX_NIE1"] = ""
        fields["DEX_NIE_2"] = ""
        fields["DEX_NIE_3"] = ""

        # ФИО (латиница, UPPERCASE)
        fields["DEX_APE1"] = (applicant.last_name_latin or "").upper()
        fields["DEX_NOMBRE"] = (applicant.first_name_latin or "").upper()

        # Место рождения и страна гражданства = страна рождения (упрощение)
        fields["DEX_LN"] = (applicant.birth_place_latin or "").upper()
        fields["DEX_PAIS"] = country_es(applicant.nationality)
        fields["DEX_NACION"] = country_es(applicant.nationality)

        # Пол: H = Hombre, M = Mujer
        if applicant.sex == "H":
            fields["DEX_SEXO"] = "/H"
        elif applicant.sex == "M":
            fields["DEX_SEXO"] = "/M"

        # Estado civil: S/C/V/D/Sp/Uh
        ec_map = {
            "S": "/S",   # Soltero
            "C": "/C",   # Casado
            "V": "/V",   # Viudo
            "D": "/D",   # Divorciado
            "Sp": "/Sp", # Separado
            "Uh": "/Uh", # Unión de hecho
        }
        if applicant.marital_status in ec_map:
            fields["DEX_EC"] = ec_map[applicant.marital_status]

        # Дата рождения по частям
        d, m, y = _fmt_date_parts(applicant.birth_date)
        fields["DEX_DIA_NAC"] = d
        fields["DEX_MES_NAC"] = m
        fields["DEX_ANYO_NAC"] = y

        # Имена родителей (латиница UPPERCASE)
        fields["DEX_NP"] = (applicant.father_name_latin or "").upper()
        fields["DEX_NM"] = (applicant.mother_name_latin or "").upper()

        # Контакты
        fields["DEX_TFNO"] = applicant.phone or ""
        fields["DEX_EMAIL"] = (applicant.email or "").upper()

    # ============= Адрес в Испании (берём из SpainAddress) =============
    if addr:
        fields["DEX_DOMIC"] = (addr.street or "").upper()
        fields["DEX_NUM"] = addr.number or ""
        fields["DEX_PISO"] = addr.floor or ""
        fields["DEX_LOCAL"] = (addr.city or "").upper()
        fields["DEX_CP"] = addr.zip or ""
        fields["DEX_PROV"] = (addr.province or "").upper()

    # País de residencia fuera de España — оставляем пустым
    # (заявитель уже находится в Испании по визе/стажировке)
    fields["DEX_PAISRES"] = ""

    # ============= DEE: Datos de la empresa en España =============
    # Для Teletrabajador (DN-визы) этот блок НЕ заполняется.
    # Все 16 полей оставляем пустыми по умолчанию (не задаём в dict).

    # ============= DR: Datos del representante =============
    if rep:
        fields["DR_APELLIDOS"] = (rep.last_name or "").upper()
        fields["DR_NOMBRE"] = (rep.first_name or "").upper()
        fields["DR_TFNO"] = rep.phone or ""
        fields["DR_EMAIL"] = (rep.email or "").upper()
        fields["DR_DNI"] = (rep.nie or "").upper()

    # ============= NRC и подпись =============
    # NRC — номер квитанции пошлины. Поле tasa_nrc уже есть в Application (Pack 1).
    fields["NRC_TITULAR"] = (app.tasa_nrc or "")

    # Место и дата подписи: используем submission_date или сегодня
    sign_date = app.submission_date or date.today()
    sign_city = (addr.city if addr else "BARCELONA") or "BARCELONA"

    fields["FIR_PROV"] = sign_city.upper()
    fields["FIR_DIA"] = f"{sign_date.day:02d}"
    # Месяц по-испански в верхнем регистре (как в образце: 'ABRIL')
    from .countries_es import month_es
    fields["FIR_MES"] = month_es(sign_date.month)
    fields["FIR_ANYO"] = str(sign_date.year)

    return fields
