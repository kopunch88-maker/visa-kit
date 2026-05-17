"""
EX-17 form generator — заполнение AcroForm полей в шаблоне EX_17.pdf.

Pack 36.1: универсальная форма "Solicitud de Tarjeta de Identidad de
Extranjero" Министерства Внутренних Дел (LO 4/2000 y RD 557/2011).
70 полей, имена ужасные (Textfield-1, Textfield-2, CP, x, H, M, ...).

Подаётся параллельно с MI-TIE — оба варианта приносятся в комиссариат,
полиция сама решает какую принять (зависит от региона / комиссара).

Pack 36.1.1 hotfix: чекбоксы Sexo и Estado civil в шаблоне имеют ИМЕНА
СДВИНУТЫЕ на 1 позицию вправо относительно подписей. То есть имя
widget'а взято от соседней слева подписи. Эмпирически проверено
визуально с поочерёдным /On для каждого checkbox-поля:
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


# Pack 36.1.1 hotfix: маппинги с учётом сдвига имён виджетов на 1 вправо
# (см. docstring модуля).
_SEX_WIDGET_MAP = {
    "H": "M",       # Hombre на форме = widget T='M'
    "M": "ChkBox",  # Mujer на форме = widget T='ChkBox'
    # X-Indefinido = widget T='H' — не используем для DN-кейсов
}

_EC_WIDGET_MAP = {
    "S":  "C",         # Soltero на форме = widget T='C'
    "C":  "V",         # Casado на форме = widget T='V'
    "V":  "D",         # Viudo на форме = widget T='D'
    "D":  "Sp",        # Divorciado на форме = widget T='Sp'
    "Sp": "ChkBox-0",  # Separado на форме = widget T='ChkBox-0'
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

    # ============ DATOS DEL EXTRANJERO/A ============
    if applicant:
        fields["Textfield-1"] = applicant.passport_number or ""  # PASAPORTE

        # NIE по 3 полям
        nie_letter, nie_number, nie_final = _split_nie(app.nie)
        fields["Textfield-2"] = nie_letter   # NIE letra
        fields["Textfield-3"] = nie_number   # NIE número
        fields["Textfield-4"] = nie_final    # NIE letra final

        fields["CP"] = (applicant.last_name_latin or "").upper()  # 1er Apellido
        fields["x"] = ""                                            # 2º Apellido
        fields["Textfield-5"] = (applicant.first_name_latin or "").upper()  # Nombre

        # Sexo: H/M через сдвинутый маппинг (Pack 36.1.1)
        if applicant.sex in _SEX_WIDGET_MAP:
            fields[_SEX_WIDGET_MAP[applicant.sex]] = "/On"

        # Дата рождения (день/мес/год)
        d, m, y = _fmt_date_parts(applicant.birth_date)
        fields["Fecha de nacimientoz"] = d  # день
        fields["Texto-1"] = m                # месяц
        fields["Textfield-6"] = y            # год

        fields["Estado civil3 S"] = (applicant.birth_place_latin or "").upper()  # Lugar
        fields["Textfield-7"] = country_es(applicant.birth_country or applicant.nationality)
        fields["Textfield-8"] = country_es(applicant.nationality)

        # Estado civil через сдвинутый маппинг (Pack 36.1.1)
        if applicant.marital_status in _EC_WIDGET_MAP:
            fields[_EC_WIDGET_MAP[applicant.marital_status]] = "/On"

        fields["Textfield-10"] = (applicant.father_name_latin or "").upper()
        fields["N"] = (applicant.mother_name_latin or "").upper()  # Nombre madre

    # ============ Адрес заявителя ============
    if addr:
        fields["Provincia"] = (addr.street or "").upper()  # Domicilio (имя поля врёт)
        fields["Textfield-11"] = addr.number or ""          # Nº
        fields["Textfield-12"] = addr.floor or ""           # Piso
        fields["Textfield-13"] = (addr.city or "").upper()  # Localidad
        fields["Textfield-15"] = addr.zip or ""             # C.P.
        fields["Textfield-17"] = (addr.province or "").upper()  # Provincia

    # Контакты
    if applicant:
        fields["Textfield-18"] = applicant.phone or ""
        fields["DN IN IEPAS"] = (applicant.email or "").upper()  # имя поля очень врёт

    # ============ Секции 2 и 3 — обычно пустые для нашего use case ============
    if rep:
        # Pack 36.1: пока опционально, по умолчанию оставляем секцию пустой.
        pass

    # ============ Страница 2: TIPO DE DOCUMENTO ============
    # Pack 36.1: всегда TARJETA INICIAL (для DN-теletrabajador после одобрения)
    fields["TARJETA INICIAL"] = "/On"

    # Имя в шапке страницы 2
    if applicant:
        fields["Nombre y apellidos del titular"] = (
            f"{applicant.last_name_latin or ''}, {applicant.first_name_latin or ''}".upper()
        )

    # ============ Footer страницы 2: место + дата подписи ============
    # Pack 36.1: дата = fingerprint_date
    sign_date = app.fingerprint_date or app.submission_date or date.today()
    sign_city = (addr.city if addr else "BARCELONA") or "BARCELONA"

    fields["Textfield-55"] = sign_city.upper()       # ciudad
    fields["a"] = f"{sign_date.day:02d}"              # día
    fields["de"] = month_es(sign_date.month)          # mes (испанский UPPERCASE)
    fields["de-0"] = str(sign_date.year)              # año

    return fields
