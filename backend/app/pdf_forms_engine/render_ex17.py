"""
EX-17 form generator — заполнение AcroForm полей в шаблоне EX_17.pdf.

Pack 36.1: универсальная форма "Solicitud de Tarjeta de Identidad de
Extranjero" Министерства Внутренних Дел (LO 4/2000 y RD 557/2011).
70 полей, имена страшные (Textfield-1, CP, x, H, M, ChkBox, Provincia,
"DN IN IEPAS" и т.д.).

Подаётся параллельно с MI-TIE — оба варианта приносятся в комиссариат,
полиция сама решает какую принять (зависит от региона / комиссара).

Pack 36.1.1 hotfix: маппинг checkbox-полей Sexo и Estado civil СДВИНУТ
на 1 позицию ВПРАВО относительно подписей. Проверено визуально с
поочерёдным /On для каждого поля:
  Sexo:
    widget T='H'        стоит под подписью X* (Indefinido)
    widget T='M'        стоит под подписью H  (Hombre)
    widget T='ChkBox'   стоит под подписью M  (Mujer)
  Estado civil:
    widget T='C'        стоит под подписью S  (Soltero)
    widget T='V'        стоит под подписью C  (Casado)
    widget T='D'        стоит под подписью V  (Viudo)
    widget T='Sp'       стоит под подписью D  (Divorciado)
    widget T='ChkBox-0' стоит под подписью Sp (Separado)

Pack 36.1.2: добавлено заполнение секций 2 (DATOS DEL REPRESENTANTE) и
3 (DOMICILIO NOTIFICACIONES). Часть имён text-полей тоже сдвинута —
маппинг расшифрован через diagnostic-рендер с уникальными значениями.

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


def render_ex17(
    application: Application,
    applicant: Optional[Applicant],
    representative: Optional[Representative],
    spain_address: Optional[SpainAddress],
    template_path: Path,
) -> bytes:
    """Заполняет EX_17.pdf данными из заявки. Возвращает bytes готового PDF."""
    reader = PdfReader(str(template_path))
    writer = PdfWriter(clone_from=reader)

    fields = _build_ex17_fields(application, applicant, representative, spain_address)

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
    """NIE 'Z3751311Q' → ('Z', '3751311', 'Q')."""
    if not nie:
        return "", "", ""
    s = nie.replace(" ", "").replace("-", "").upper()
    if len(s) < 3:
        return s, "", ""
    return s[0], s[1:-1], s[-1]


# Pack 36.1.1 hotfix: маппинги с учётом сдвига checkbox-имён на 1 вправо
_SEX_WIDGET_MAP = {
    "H": "M",       # Hombre на форме = widget T='M'
    "M": "ChkBox",  # Mujer на форме = widget T='ChkBox'
}

_EC_WIDGET_MAP = {
    "S":  "C",
    "C":  "V",
    "V":  "D",
    "D":  "Sp",
    "Sp": "ChkBox-0",
}


def _build_ex17_fields(
    app: Application,
    applicant: Optional[Applicant],
    rep: Optional[Representative],
    addr: Optional[SpainAddress],
) -> dict:
    """
    Маппинг данных в имена полей PDF (EX-17).
    Имена полей в шаблоне странные — комментарии справа объясняют что есть что.
    """

    fields: dict = {}

    # ============ DATOS DEL EXTRANJERO/A (секция 1) ============
    if applicant:
        fields["Textfield-1"] = applicant.passport_number or ""  # PASAPORTE

        # NIE по 3 полям
        nie_letter, nie_number, nie_final = _split_nie(app.nie)
        fields["Textfield-2"] = nie_letter
        fields["Textfield-3"] = nie_number
        fields["Textfield-4"] = nie_final

        fields["CP"] = (applicant.last_name_latin or "").upper()  # 1er Apellido
        fields["x"] = ""                                            # 2º Apellido
        fields["Textfield-5"] = (applicant.first_name_latin or "").upper()  # Nombre

        # Sexo через сдвинутый маппинг
        if applicant.sex in _SEX_WIDGET_MAP:
            fields[_SEX_WIDGET_MAP[applicant.sex]] = "/On"

        # Дата рождения (день/мес/год)
        d, m, y = _fmt_date_parts(applicant.birth_date)
        fields["Fecha de nacimientoz"] = d
        fields["Texto-1"] = m
        fields["Textfield-6"] = y

        fields["Estado civil3 S"] = (applicant.birth_place_latin or "").upper()  # Lugar
        fields["Textfield-7"] = country_es(applicant.birth_country or applicant.nationality)
        fields["Textfield-8"] = country_es(applicant.nationality)

        # Estado civil через сдвинутый маппинг
        if applicant.marital_status in _EC_WIDGET_MAP:
            fields[_EC_WIDGET_MAP[applicant.marital_status]] = "/On"

        fields["Textfield-10"] = (applicant.father_name_latin or "").upper()
        fields["N"] = (applicant.mother_name_latin or "").upper()  # Nombre madre

    # Адрес заявителя (секция 1)
    if addr:
        fields["Provincia"] = (addr.street or "").upper()  # Domicilio (имя поля врёт)
        fields["Textfield-11"] = addr.number or ""          # Nº
        fields["Textfield-12"] = addr.floor or ""           # Piso
        fields["Textfield-13"] = (addr.city or "").upper()  # Localidad
        fields["Textfield-15"] = addr.zip or ""             # C.P.
        fields["Textfield-17"] = (addr.province or "").upper()  # Provincia

    # Контакты заявителя
    if applicant:
        fields["Textfield-18"] = applicant.phone or ""
        fields["DN IN IEPAS"] = (applicant.email or "").upper()  # имя поля очень врёт

    # ============ Секция 2: DATOS DEL REPRESENTANTE PRESENTACIÓN ============
    # Pack 36.1.2: заполняется когда есть representative.
    # Маппинг полей расшифрован через diagnostic-рендер (см. docstring).
    if rep:
        rep_full_name = f"{rep.first_name or ''} {rep.last_name or ''}".strip().upper()
        # Nombre/Razón Social — имя поля "D NIN IEPAS" (имя сдвинуто от соседней подписи)
        fields["D NIN IEPAS"] = rep_full_name
        # DNI/NIE/PAS — имя поля "Piso-0"
        fields["Piso-0"] = (rep.nie or "").upper()

        # Адрес представителя
        fields["Textfield-29"] = (rep.address_street or "").upper()  # Domicilio
        fields["Textfield-31"] = rep.address_number or ""             # Nº
        fields["Textfield-32"] = rep.address_floor or ""              # Piso
        fields["Email"] = (rep.address_city or "").upper()            # Localidad (имя сдвинуто)
        fields["Textfield-33"] = rep.address_zip or ""                # C.P.
        fields["Textfield-34"] = (rep.address_province or "").upper() # Provincia

        # Контакты представителя
        fields["Textfield-35"] = rep.phone or ""                      # Teléfono móvil
        fields["Titulo4"] = (rep.email or "").upper()                 # E-mail (имя сдвинуто)

        # Representante legal en su caso — для юрлица. Для физлица оставляем пусто.
        # fields["Textfield-39"] = ""
        # fields["Email-0"] = ""
        # fields["Textfield-40"] = ""

    # ============ Секция 3: DOMICILIO A EFECTOS DE NOTIFICACIONES ============
    # Pack 36.1.2: адрес заявителя в Испании (физическое место проживания клиента).
    if addr and applicant:
        applicant_full_name = (
            f"{applicant.last_name_latin or ''} {applicant.first_name_latin or ''}"
        ).strip().upper()
        # Nombre/Razón Social — имя поля Textfield-41
        fields["Textfield-41"] = applicant_full_name
        # DNI/NIE/PAS — имя поля "N Piso" (сдвинуто)
        fields["N Piso"] = app.nie or ""

        # Адрес
        fields["Textfield-43"] = (addr.street or "").upper()  # Domicilio
        fields["Textfield-44"] = addr.number or ""             # Nº
        fields["Textfield-45"] = addr.floor or ""              # Piso
        fields["Textfield-46"] = (addr.city or "").upper()     # Localidad
        fields["Textfield-47"] = addr.zip or ""                # C.P.
        fields["Textfield-49"] = (addr.province or "").upper() # Provincia

        # Контакты
        fields["Textfield-50"] = applicant.phone or ""              # Tel móvil
        fields["Textfield-52"] = (applicant.email or "").upper()    # E-mail

    # ============ Страница 2: TIPO DE DOCUMENTO ============
    fields["TARJETA INICIAL"] = "/On"

    # Имя в шапке страницы 2
    if applicant:
        fields["Nombre y apellidos del titular"] = (
            f"{applicant.last_name_latin or ''}, {applicant.first_name_latin or ''}".upper()
        )

    # ============ Footer страницы 2: место + дата подписи ============
    sign_date = app.fingerprint_date or app.submission_date or date.today()
    sign_city = (addr.city if addr else "BARCELONA") or "BARCELONA"

    fields["Textfield-55"] = sign_city.upper()       # ciudad
    fields["a"] = f"{sign_date.day:02d}"              # día
    fields["de"] = month_es(sign_date.month)          # mes
    fields["de-0"] = str(sign_date.year)              # año

    return fields
