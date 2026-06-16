"""
Applicants admin endpoints — для админки чтобы получать и редактировать данные клиента.
Pack 8: эндпоинты возвращают dict (без валидации Pydantic), как в client_portal.
Pack 14 finishing: добавлены PATCH endpoint и /transliterate для иностранцев.
Pack 16.1: добавлены банковские поля (bank_id, bank_account, ...) в whitelist
для редактирования через ApplicantDrawer.
Pack 18.5: _enrich теперь делает join с self_employed_registry чтобы вернуть
npd_check_status и npd_last_check_at — фронт показывает значок «Проверен ФНС» /
«Не действителен» / «Не проверен» рядом с полем ИНН в ApplicantDrawer.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_session
from app.models import Applicant, Application
from app.models.self_employed_registry import SelfEmployedRegistry
from app.services.transliteration import transliterate_lat_to_ru, normalize_russian_case
from .dependencies import require_manager
# Pack 46.0 — диплом для хурадо
from fastapi.responses import Response as _Pack46Response
from app.services.diploma_pdf_renderer import render_diploma_pdf
from app.services.diploma_field_generator import (
    DiplomaFieldsInput,
    generate_diploma_fields,
)

router = APIRouter(prefix="/admin/applicants", tags=["applicants"])


def _compute_npd_check_status(
    applicant: Applicant, session: Session
) -> tuple[str, Optional[datetime]]:
    """
    Pack 18.5: вычисляет статус проверки ИНН через ФНС API на основе
    данных в self_employed_registry.

    Возвращает (status, last_check_at):
      - 'no_inn' — у applicant'а нет ИНН (значок не показывается)
      - 'verified' — last_npd_check_at установлен, is_invalid=False (зелёный ✓)
      - 'invalid' — is_invalid=True (красный ✗) — ФНС подтвердил отзыв статуса
      - 'not_checked' — есть ИНН, но проверка не выполнялась (серый —)
                       (например, ИНН выдан до Pack 18.2 или ФНС был недоступен)
    """
    if not applicant.inn:
        return "no_inn", None

    cand = session.get(SelfEmployedRegistry, applicant.inn)
    if not cand:
        # ИНН в applicant'е есть, но в реестре его нет — странная ситуация
        return "not_checked", None

    if cand.is_invalid:
        return "invalid", cand.last_npd_check_at

    if cand.last_npd_check_at is not None:
        return "verified", cand.last_npd_check_at

    return "not_checked", None


def _enrich(applicant: Applicant, session: Session) -> dict:
    """
    Pack 18.5: добавлен параметр session чтобы можно было подгрузить запись
    из self_employed_registry для вычисления npd_check_status.
    """
    parts = [applicant.last_name_native, applicant.first_name_native]
    if applicant.middle_name_native:
        parts.append(applicant.middle_name_native)
    full_name = " ".join(p for p in parts if p)

    initials = ""
    if applicant.last_name_native and applicant.first_name_native:
        initials = f"{applicant.last_name_native} {applicant.first_name_native[0]}."
        if applicant.middle_name_native:
            initials += f"{applicant.middle_name_native[0]}."

    data = applicant.model_dump()
    data["full_name_native"] = full_name
    data["initials_native"] = initials

    # Pack 18.5: статус проверки НПД через ФНС API
    npd_status, npd_last_check = _compute_npd_check_status(applicant, session)
    data["npd_check_status"] = npd_status
    data["npd_last_check_at"] = npd_last_check.isoformat() if npd_last_check else None

    return data


@router.get("/{applicant_id}")
def get_applicant(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, "Applicant not found")
    return _enrich(applicant, session)


# ============================================================================
# Pack 14 finishing — PATCH endpoint
# ============================================================================

# Поля которые менеджер может редактировать через ApplicantDrawer.
# Pack 16.1: добавлены bank_* поля.
_PATCHABLE_FIELDS = {
    "last_name_native", "first_name_native", "middle_name_native",
    "last_name_latin", "first_name_latin",
    "full_name_accusative",  # Pack 50.7-C-prep — винительный падеж для Т-9
    # Pack 50.41 — родительный + творительный падеж ФИО (письмо работодателя, найм)
    "full_name_genitive", "full_name_instrumental",
    "full_name_dative",  # Pack 50.42 — дательный падеж (разрешает кому?)
    "birth_date", "birth_place_latin",
    "birth_country",  # Pack 18.10
    "nationality", "sex", "marital_status",
    "passport_number", "passport_issue_date", "passport_expiry_date", "passport_issuer",
    # Pack 35.3: русифицированный вариант органа выдачи для русских документов
    "passport_issuer_ru",
    "inn",
    # Pack 17 — INN auto-generation поля
    "inn_registration_date",
    "inn_source",
    "inn_kladr_code",
    # Pack 50.1-F2 — СНИЛС работника (Трудовой договор)
    "snils",
    "home_address", "home_address_line1", "home_address_line2",
    "home_country",
    "email", "phone", "phone_ru",  # Pack 50.15-A
    # Pack 56.0 — поля окна «Ситы» (отдельные от контактов клиента)
    "cita_fill_type", "cita_cert_owner", "cita_email", "cita_phone",
    # Pack 16.1 — банковские поля
    "bank_id",
    "bank_account",
    "bank_name",
    "bank_bic",
    "bank_correspondent_account",
    # Имена родителей для анкеты MI-T (Nombre del padre / Nombre de la madre)
    "father_name_latin",
    "mother_name_latin",
    # Pack 18.9 — переопределение подписанта апостиля (если null — backend
    # подставляет дефолт «Байрамов Н.А.» / стандартная должность Минюста)
    "apostille_signer_short",
    "apostille_signer_signature",
    "apostille_signer_position",
    # Pack 19.0 — JSON-поля анкеты (education[], work_history[], languages[])
    "education",
    "work_history",
    "languages",
    # Pack 41.0 — two-passport split
    "passports",
    "passport_id_for_ru_docs",
    # Pack 41.0-M — ручное наименование ИФНС для НПД-справки
    "npd_ifns_name",
}

# Поля русского ФИО — к ним применяется normalize_russian_case при сохранении
_NATIVE_NAME_FIELDS = {"last_name_native", "first_name_native", "middle_name_native"}

# Поля латинского ФИО — оставляем uppercase как в паспорте
_LATIN_NAME_FIELDS = {"last_name_latin", "first_name_latin"}

# Pack 16.1: целочисленные поля — приводим к int
_INT_FIELDS = {"bank_id"}


# Pack 37.7 — sync DN work_history в БД когда менеджер сохраняет Drawer
from app.services.work_history_sync import sync_dn_work_record_safe
from app.services.applicant_passports import reconcile_applicant_passports  # Pack 41.0-B


@router.patch("/{applicant_id}")
def update_applicant(
    applicant_id: int,
    patch: dict = Body(...),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    """
    Обновляет данные кандидата от имени менеджера.

    Pack 14 finishing: позволяет менеджеру вписать русские ФИО для иностранцев,
    исправить гражданство и т.д.
    Pack 16.1: + банковские поля (bank_id, bank_account, ...).

    Применяет нормализацию:
    - Русские ФИО → Title Case (Иванов, не ИВАНОВ)
    - Латинские ФИО → как есть, но trim (паспорт обычно UPPERCASE — оставляем)
    - bank_id → приводим к int (frontend может прислать строкой "1")

    Body — dict с любыми полями из _PATCHABLE_FIELDS.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, "Applicant not found")

    if not isinstance(patch, dict):
        raise HTTPException(400, "Body must be a JSON object")

    # Валидация — только разрешённые поля
    unknown = set(patch.keys()) - _PATCHABLE_FIELDS
    if unknown:
        raise HTTPException(400, f"Unknown fields: {sorted(unknown)}")

    # Применяем изменения
    for field, value in patch.items():
        if value is None or value == "":
            # Пустое значение → null (для опциональных полей)
            # КРОМЕ обязательных
            if field in ("last_name_native", "first_name_native",
                          "last_name_latin", "first_name_latin"):
                # Не позволяем затирать обязательные поля
                continue
            setattr(applicant, field, None)
            continue

        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue

            # Нормализация русских ФИО
            if field in _NATIVE_NAME_FIELDS:
                value = normalize_russian_case(value)

            # Pack 16.1: bank_id может прийти как строка — приводим к int
            if field in _INT_FIELDS:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    raise HTTPException(400, f"Field {field} must be an integer")

            # Латинские ФИО — оставляем как менеджер ввёл, только trim
            # (обычно UPPERCASE, как в паспорте)

        # Pack 16.1: bank_id может прийти как число напрямую — это ок
        setattr(applicant, field, value)

    # Pack 41.0-B — пересчёт primary паспорта и sync скалярных passport_* полей
    reconcile_applicant_passports(applicant)

    session.add(applicant)
    session.commit()
    session.refresh(applicant)

    # Pack 37.7: если менеджер сохранил work_history (через ручное редактирование
    # или после "Сгенерировать опыт работы"), пробуем синкнуть с DN-employer-ом.
    # Безопасно — sync_dn_work_record_safe вернёт False если данных не хватает
    # (нет company/position/contract_sign_date в attached application).
    if "work_history" in patch:
        from app.models import Application
        from sqlmodel import select
        # У applicant может быть несколько applications — берём ту что с company.
        # На практике обычно одна Application на Applicant.
        applications = session.exec(
            select(Application).where(Application.applicant_id == applicant.id)
        ).all()
        for app in applications:
            if app.company_id and app.contract_sign_date:
                sync_dn_work_record_safe(app, session)
                # Перечитаем applicant — sync мог его обновить
                session.refresh(applicant)
                break  # одной заявки достаточно

    return _enrich(applicant, session)


# ============================================================================
# Pack 14 finishing — Транслитерация Latin → русский (черновик для менеджера)
# ============================================================================

@router.post("/transliterate")
def transliterate(
    body: dict = Body(...),
    _user=Depends(require_manager),
) -> dict:
    """
    Транслитерирует латинское ФИО в русский черновик с учётом языка.
    """
    last_lat = (body.get("last_name_latin") or "").strip()
    first_lat = (body.get("first_name_latin") or "").strip()
    nationality = (body.get("nationality") or "").strip().upper() or None

    if not last_lat or not first_lat:
        raise HTTPException(400, "Both last_name_latin and first_name_latin are required")

    last_ru = transliterate_lat_to_ru(last_lat, nationality)
    first_ru = transliterate_lat_to_ru(first_lat, nationality)

    return {
        "last_name_native": last_ru,
        "first_name_native": first_ru,
        "warning": "Автоматический черновик транслитерации. Проверьте и поправьте если нужно.",
    }


# ============================================================================
# Pack 32.0 — POST /for-application/{app_id}
# ============================================================================
# Создаёт пустого Applicant'а с placeholder ФИО «—» и привязывает к указанной
# Application. Используется когда менеджер хочет начать редактировать карточку
# кандидата СРАЗУ после создания пустой заявки, не дожидаясь пока клиент
# заполнит анкету через свой кабинет.
#
# Если у application уже есть applicant_id — возвращает существующего (идемпотентно).
# Placeholder'ы тот же приём что в import_package.py:_auto_apply_ocr_to_applicant
# (NOT NULL constraint на имена, но реальные данные пока неизвестны).

@router.post("/for-application/{app_id}", status_code=201)
def create_empty_applicant_for_application(
    app_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    """
    Создать пустого Applicant'а для заявки если у неё ещё нет applicant_id.

    Возвращает _enrich(applicant) — тот же формат, что GET /admin/applicants/{id},
    чтобы фронт мог сразу подсунуть результат в стейт без дополнительного
    refetch'а.
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    # Идемпотентность — если applicant уже привязан, вернём его.
    if application.applicant_id:
        existing = session.get(Applicant, application.applicant_id)
        if existing:
            return _enrich(existing, session)
        # applicant_id указывает на удалённую запись — отвяжем и пересоздадим.
        application.applicant_id = None

    # Placeholder'ы для NOT NULL имён. Менеджер потом перезапишет через
    # PATCH /admin/applicants/{id} (тот же ApplicantDrawer).
    applicant = Applicant(
        last_name_native="—",
        first_name_native="—",
        last_name_latin="—",
        first_name_latin="—",
    )
    session.add(applicant)
    session.flush()
    session.refresh(applicant)

    application.applicant_id = applicant.id
    session.add(application)

    session.commit()
    session.refresh(applicant)

    return _enrich(applicant, session)




# ============================================================================
# Pack 35.3 — resolve passport_issuer_ru endpoint
# ============================================================================

@router.post("/resolve-passport-issuer-ru")
def resolve_passport_issuer_ru_endpoint(
    payload: dict = Body(...),
    _user=Depends(require_manager),
) -> dict:
    """
    Pack 35.3: возвращает русифицированное название органа выдачи паспорта.

    Не сохраняет ничего в БД — просто резолвит и возвращает результат.
    Менеджер видит результат в поле, может поправить, потом сохраняет
    через PATCH /api/admin/applicants/{id} с полем passport_issuer_ru.

    Body:
      {"issuer": "EMBASSY OF P.R.CHINA IN RUSSIA", "nationality": "CHN"}
    Returns:
      {"resolved": "посольством КНР в России"}
      или {"resolved": null} если issuer пустой.
    """
    from app.services.passport_issuer_ru import resolve_passport_issuer_ru

    issuer = (payload.get("issuer") or "").strip()
    nationality = (payload.get("nationality") or "").strip().upper() or None

    resolved = resolve_passport_issuer_ru(issuer, nationality)
    return {"resolved": resolved}

# ============================================================================
# Pack 46.0 — Диплом для хурадо
# ============================================================================
# Документ-аналог титульного листа диплома (БЕЗ гербовых элементов и печатей),
# для передачи присяжному переводчику в Испании как source для перевода + апостиля.
# Не в общем ZIP — отдельная кнопка в разделе Образование.


@router.post("/{applicant_id}/education/{idx}/generate-fields")
async def generate_diploma_fields_endpoint(
    applicant_id: int,
    idx: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    """Pack 46.0: LLM генерит 6 полей диплома по institution+specialty+year.

    Возвращает dict — фронт сам сохраняет через PATCH education.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, f"Applicant id={applicant_id} not found")

    education = applicant.education or []
    if idx < 0 or idx >= len(education):
        raise HTTPException(
            404, f"Education[{idx}] not found (applicant has {len(education)} records)"
        )

    edu = education[idx]
    institution = (edu.get("institution") or "").strip()
    specialty = (edu.get("specialty") or "").strip()
    graduation_year = edu.get("graduation_year")
    degree = (edu.get("degree") or "").strip() or None

    if not institution or not specialty or not graduation_year:
        raise HTTPException(
            422,
            "Для генерации нужны institution, specialty и graduation_year. "
            f"Сейчас: institution={institution!r}, specialty={specialty!r}, year={graduation_year!r}",
        )

    # ФИО для контекста промпта
    full_name_parts = [
        (applicant.first_name_native or "").strip(),
        (applicant.last_name_native or "").strip(),
    ]
    full_name = " ".join(p for p in full_name_parts if p) or None

    try:
        inp = DiplomaFieldsInput(
            institution=institution,
            specialty=specialty,
            graduation_year=int(graduation_year),
            degree=degree,
            full_name_native=full_name,
        )
        result = await generate_diploma_fields(inp)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(500, f"LLM service error: {e}")

    return result


@router.get("/{applicant_id}/education/{idx}/diploma.pdf")
async def get_diploma_pdf_endpoint(
    applicant_id: int,
    idx: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """Pack 46.0: рендерит PDF диплома для хурадо. Открывается inline в браузере."""
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(404, f"Applicant id={applicant_id} not found")

    education = applicant.education or []
    if idx < 0 or idx >= len(education):
        raise HTTPException(
            404, f"Education[{idx}] not found (applicant has {len(education)} records)"
        )

    edu = education[idx]

    # Собираем ФИО на русском (фамилия + имя + отчество если есть)
    parts = [
        (applicant.last_name_native or "").strip(),
        (applicant.first_name_native or "").strip(),
    ]
    middle = (getattr(applicant, "middle_name_native", "") or "").strip()
    if middle:
        parts.append(middle)
    full_name = " ".join(p for p in parts if p)

    if not full_name:
        raise HTTPException(422, "У applicant пустое ФИО — не могу собрать диплом")

    try:
        pdf_bytes = render_diploma_pdf(
            full_name_native=full_name,
            education=edu,
        )
    except Exception as e:
        raise HTTPException(500, f"Ошибка рендера PDF: {e}")

    # ASCII-safe filename + RFC 5987 для кириллицы (Правило 61)
    from urllib.parse import quote
    safe_last = (applicant.last_name_native or f"applicant_{applicant_id}").strip()
    pretty_name = f"Диплом_{safe_last}.pdf"
    ascii_fallback = f"diploma_{applicant_id}_{idx}.pdf"

    return _Pack46Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{quote(pretty_name)}"
            ),
        },
    )


# ============================================================================
# Pack 50.1-F2 — генерация правдоподобного СНИЛС с правильной контрольной суммой
# ============================================================================
#
# Алгоритм контрольной суммы СНИЛС (Постановление ПФР):
# 1. 9 цифр номера слева направо.
# 2. Каждая цифра умножается на свою позицию СПРАВА НАЛЕВО (9, 8, 7, ..., 1).
# 3. Сумма произведений делится на 101 → остаток.
# 4. Если остаток ≤ 99 → контрольная сумма = остаток (2 цифры с ведущим 0).
# 5. Если остаток = 100 или 101 → контрольная сумма = "00".
#
# Пример: 117-170-507 → 1·9+1·8+7·7+1·6+7·5+0·4+5·3+0·2+7·1 = 129
#   129 % 101 = 28 → "117-170-507 28" ✓

import random as _random_snils


def _snils_checksum(digits9: str) -> str:
    """Вычисляет 2-значную контрольную сумму СНИЛС по 9 цифрам номера."""
    if len(digits9) != 9 or not digits9.isdigit():
        raise ValueError(f"SNILS digits9 must be 9 digits, got: {digits9!r}")
    total = sum(int(d) * (9 - i) for i, d in enumerate(digits9))
    rem = total % 101
    if rem >= 100:
        return "00"
    return f"{rem:02d}"


def _generate_random_snils() -> str:
    """Генерирует правдоподобный СНИЛС: XXX-XXX-XXX XX.

    9 случайных цифр номера + контрольная сумма по алгоритму ПФР.
    Первая цифра ≠ 0 чтобы избежать вырожденных номеров вроде 000-001-002.
    """
    # Первая цифра 1-9 (не 0)
    first = str(_random_snils.randint(1, 9))
    # Остальные 8 — случайные 0-9
    rest = "".join(str(_random_snils.randint(0, 9)) for _ in range(8))
    digits9 = first + rest
    checksum = _snils_checksum(digits9)
    return f"{digits9[:3]}-{digits9[3:6]}-{digits9[6:9]} {checksum}"


@router.post("/generate-snils")
def generate_snils_endpoint(
    _user=Depends(require_manager),
) -> dict:
    """Pack 50.1-F2 — генерирует правдоподобный СНИЛС с правильной контрольной суммой.

    Не привязан к конкретному applicant — клиент после получения значения сам
    сохраняет его через PATCH /admin/applicants/{id} с полем snils.
    """
    return {"snils": _generate_random_snils()}
