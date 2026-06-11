"""
Applications router — Pack 8.7 — добавлен PATCH endpoint для partial-update.

Изменения по сравнению с Pack 8.5:
- Новый endpoint PATCH /admin/applications/{id} — частичное обновление
  любых полей заявки, в т.ч. данных распределения. Не требует чтобы все
  поля были заполнены сразу.
- Старый POST /assign оставлен для обратной совместимости.

Pack 20.0 (04.05.2026):
- Снята валидация `position.company_id != company.id` в PATCH и legacy POST /assign
  endpoints. Position теперь не имеет company_id (отвязан от Company).
"""

import asyncio  # Pack 57.0 — lock per app_id для auto-translate
import io
import secrets
from datetime import date, datetime, timedelta, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import (
    Application, ApplicationCreate, ApplicationAssign, ApplicationStatusUpdate,
    ApplicationStatus,
    ApplicationType,  # Pack 50.0-B
    Applicant, Company, Position, Representative, SpainAddress,
    TimelineEvent,
)
from app.services import recommendation
from app.services.rendering import build_full_package
from app.templates_engine import (
    render_contract, render_act, render_invoice,
    render_employer_letter, render_cv, render_bank_statement,
    render_employer_letter_naim,  # Pack 50.11-B
    render_npd_certificate, 
    render_npd_certificate_lkn,  # Pack 18.3.3
    render_apostille,  # Pack 18.9
    render_tech_opinion,  # Pack 40.0-G
    render_business_trip_order,  # Pack 50.7-C
    render_employment_contract,  # Pack 50.1-C
    render_ndfl_2,  # Pack 50.8-B
    render_stdr,  # Pack 50.9-B
    render_soo,  # Pack 50.12-D
    render_apostille_sfr,  # Pack 50.20
    render_payslip,  # Pack 50.10-B
)
from app.pdf_forms_engine import build_pdf_forms
from .dependencies import require_manager, current_user_id
# Pack 37.2 — sync work_history with DN employer after assignment
from app.services.work_history_sync import sync_dn_work_record_safe

router = APIRouter(prefix="/admin/applications", tags=["applications"])


def _enrich(app: Application, session: Session) -> dict:
    family_size = len(app.family_members) if app.family_members else 0
    data = app.model_dump(exclude={
        "family_members", "uploaded_files",
        "generated_documents", "previous_residences",
    })
    data["has_family"] = family_size > 0
    data["family_size"] = family_size
    data["business_rule_problems"] = app.validate_business_rules()
    # Pack 10: вычисляемое поле — можно ли архивировать
    data["can_be_archived"] = app.can_be_archived()
    # Pack 30.0
    data["is_urgent"] = bool(getattr(app, "is_urgent", False))
    data["is_paid"] = bool(getattr(app, "is_paid", False))
    data["is_filed"] = bool(getattr(app, "is_filed", False))

    # Pack 10.1: подгружаем имя заявителя для отображения в списках
    # (на странице архива и потенциально в других списках)
    data["applicant_name_native"] = None
    data["applicant_name_latin"] = None
    if app.applicant_id:
        applicant = session.get(Applicant, app.applicant_id)
        if applicant:
            # Русское ФИО
            parts_native = [
                getattr(applicant, "last_name_native", None),
                getattr(applicant, "first_name_native", None),
            ]
            full_native = " ".join(p for p in parts_native if p).strip()
            data["applicant_name_native"] = full_native or None

            # Латинское ФИО (UPPERCASE как в шапке заявки)
            parts_latin = [
                getattr(applicant, "last_name_latin", None),
                getattr(applicant, "first_name_latin", None),
            ]
            full_latin = " ".join(p for p in parts_latin if p).strip()
            data["applicant_name_latin"] = full_latin.upper() if full_latin else None

    return data


def _json_safe(obj):
    """Конвертирует date/datetime/Decimal в строки для JSON-сериализации."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    # Decimal и прочее — в строку
    if hasattr(obj, "__class__") and obj.__class__.__name__ == "Decimal":
        return str(obj)
    return obj


# Pack 50.8-fix2 — лимит summary в TimelineEvent.summary = VARCHAR(256).
# Без этого PATCH с большим update_data ломается через _log_event:
#   psycopg2.errors.StringDataRightTruncation: value too long for type character varying(256)
_SUMMARY_MAX = 250  # запас на "..." и любые приколы кодировки


def _truncate_summary(summary: str) -> str:
    """Усекает summary до лимита VARCHAR(256) с маркером '...'."""
    if not summary:
        return summary
    if len(summary) <= _SUMMARY_MAX:
        return summary
    return summary[:_SUMMARY_MAX - 3].rstrip(", ") + "..."


def _log_event(
    session: Session, application_id: int, actor_type: str, actor_id: Optional[int],
    event_type: str, summary: str, payload: Optional[dict] = None,
) -> None:
    event = TimelineEvent(
        application_id=application_id, actor_type=actor_type, actor_id=actor_id,
        event_type=event_type, summary=_truncate_summary(summary), payload=_json_safe(payload or {}),
    )
    session.add(event)
    session.flush()


# ============================================================================
# CRUD
# ============================================================================

@router.get("")
def list_applications(
    status: Optional[ApplicationStatus] = None,
    archived: bool = Query(False, description="Pack 10: показать архивные (по умолчанию false — только активные)"),
    trash: bool = Query(False, description="Pack 27.0: показать удалённые (корзина) с lazy cleanup старше 7 дней"),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[dict]:
    # Pack 27.0 — Корзина. Если trash=True, делаем lazy cleanup и возвращаем только удалённые.
    if trash:
        # Lazy cleanup: удаляем permanently записи в корзине старше 7 дней
        cutoff = datetime.utcnow() - timedelta(days=7)
        old_trashed = session.exec(
            select(Application).where(
                Application.deleted_at.is_not(None),
                Application.deleted_at < cutoff,
            )
        ).all()
        for old_app in old_trashed:
            _permanent_delete_application(session, old_app)
        if old_trashed:
            session.commit()

        query = select(Application).where(Application.deleted_at.is_not(None))
    else:
        query = select(Application).where(
            Application.is_archived == archived,
            Application.deleted_at.is_(None),
        )
    # Pack 30.0 + Pack 34.2: трёхуровневая приоритетная сортировка
    # Группа A: is_urgent=True (с чемоданом или без) — самый верх
    # Группа B: is_urgent=False, is_ready_for_pickup=True — ниже
    # Группа C: ни того ни другого — внизу
    # Внутри A и B — алфавит по applicant_name_native (case-insensitive).
    # Внутри C — created_at DESC (свежие выше).
    query = query.order_by(
        Application.is_urgent.desc(),
        Application.is_ready_for_pickup.desc(),
        Application.created_at.desc(),
    )
    if status:
        query = query.where(Application.status == status)
    enriched = [_enrich(a, session) for a in session.exec(query).all()]
    urgent = [d for d in enriched if d.get("is_urgent")]
    ready  = [d for d in enriched if not d.get("is_urgent") and d.get("is_ready_for_pickup")]
    rest   = [d for d in enriched if not d.get("is_urgent") and not d.get("is_ready_for_pickup")]
    urgent.sort(key=lambda d: (d.get("applicant_name_native") or "").casefold())
    ready.sort(key=lambda d: (d.get("applicant_name_native") or "").casefold())
    return urgent + ready + rest


@router.get("/{app_id}")
def get_application(
    app_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> dict:
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    return _enrich(app, session)


# Pack 50.38-B — парсинг текста менеджера в поля заявки (предпросмотр)
class ManagerTextPayload(BaseModel):
    text: str


@router.post("/parse-manager-text")
async def parse_manager_text_endpoint(
    payload: ManagerTextPayload,
    user_id: int = Depends(current_user_id),
) -> dict:
    """Извлекает поля заявки из свободного текста менеджера (LLM).
    Возвращает структурированный JSON для предпросмотра/заполнения.
    Раскладка по дроверам — на стороне фронта / следующего пака."""
    from app.services.manager_text import parse_manager_text, ManagerTextParseError
    try:
        result = await parse_manager_text(payload.text)
    except ManagerTextParseError as e:
        raise HTTPException(422, f"Не удалось распарсить текст: {e}")
    return result


@router.post("/{app_id}/apply-manager-text-existing")
async def apply_manager_text_existing(
    app_id: int,
    payload: ManagerTextPayload,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """Pack 50.38-D3-2: дозакинуть текст менеджера в СУЩЕСТВУЮЩУЮ заявку.
    Парсит текст и применяет (apply_parsed) — заполняет пустые поля,
    привязывает справочники, пишет заметки. Скан-данные не трогаются."""
    from app.services.manager_text import (
        parse_manager_text as _parse, apply_parsed_to_application as _apply,
        determine_application_type as _dettype, ManagerTextParseError as _err,
    )
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    try:
        parsed = await _parse(payload.text)
        parsed["_raw_text"] = payload.text
    except _err as e:
        raise HTTPException(422, f"Не удалось распарсить текст: {e}")
    _det = _dettype(parsed)
    if _det is not None:
        app.application_type = _det
    report = _apply(session, app, parsed)
    session.commit()
    return {"ok": True, "report": report}


@router.post("", status_code=201)
def create_application(
    payload: ApplicationCreate,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    today = date.today()
    year = today.year
    last = session.exec(
        select(Application)
        .where(Application.reference.like(f"{year}-%"))
        .order_by(Application.reference.desc())
    ).first()
    next_num = 1 if not last else int(last.reference.split("-")[1]) + 1
    reference = f"{year}-{next_num:04d}"

    # Pack 50.0-B: если передан application_type — применяем,
    # иначе default из модели (SELF_EMPLOYED).
    _app_kwargs = dict(
        reference=reference,
        client_access_token=secrets.token_urlsafe(32),
        status=ApplicationStatus.AWAITING_DATA,
        assigned_manager_id=user_id,
        internal_notes=payload.notes,
        submission_date=payload.submission_date,
    )
    if getattr(payload, "application_type", None) is not None:
        _app_kwargs["application_type"] = payload.application_type
    app = Application(**_app_kwargs)
    session.add(app)
    session.flush()
    session.refresh(app)
    _log_event(
        session, app.id, "manager", user_id, "application_created",
        f"Application {reference} created",
        {"applicant_email": payload.applicant_email or ""},
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


# ============================================================================
# PATCH partial-update — Pack 8.7
# ============================================================================

class ApplicationPatch(BaseModel):
    """
    Любое поле заявки можно обновить частично. Все опциональные.
    Используется в drawers Pack 8.6+ когда нужно сохранить только
    Подачу или только Компанию/Договор.
    """
    company_id: Optional[int] = None
    position_id: Optional[int] = None
    representative_id: Optional[int] = None
    spain_address_id: Optional[int] = None
    contract_number: Optional[str] = None
    contract_sign_date: Optional[date] = None
    contract_sign_city: Optional[str] = None
    contract_end_date: Optional[date] = None
    salary_rub: Optional[float] = None
    submission_date: Optional[date] = None
    # Pack 50.38-A — город/провинция подачи
    submission_city: Optional[str] = None
    submission_province: Optional[str] = None
    payments_period_months: Optional[int] = None
    internal_notes: Optional[str] = None
    # Pack 9: NRC квитанции пошлины (для PDF-форм MI-T)
    tasa_nrc: Optional[str] = None
    # Pack 26.0: реквизиты письма от компании (Исх. № и дата)
    employer_letter_number: Optional[str] = None
    employer_letter_date: Optional[date] = None
    # Pack 36.1: TIE поля (заполняются после одобрения и получения NIE)
    nie: Optional[str] = None
    fingerprint_date: Optional[date] = None
    # Pack 50.0-B: тип заявки (самозанятый/найм)
    application_type: Optional[ApplicationType] = None
    # Pack 50.7-A: Приказ Т-9 о командировке (найм)
    business_trip_order_number: Optional[str] = None
    business_trip_order_date: Optional[date] = None
    business_trip_start_date: Optional[date] = None
    business_trip_end_date: Optional[date] = None
    business_trip_purpose_override: Optional[str] = None
    business_trip_duration_words: Optional[str] = None
    business_trip_duration_unit: Optional[str] = None
    business_trip_place_short: Optional[bool] = None
    employee_tab_number: Optional[str] = None
    # Pack 50.12-A — Свидетельство об отъезде (СОО)
    soo_number: Optional[str] = None
    soo_date: Optional[date] = None
    # Pack 50.8-B — Справка 2-НДФЛ (найм)
    ndfl_2_year: Optional[int] = None
    ndfl_2_period_from: Optional[int] = None
    ndfl_2_period_to: Optional[int] = None
    ndfl_2_issue_date: Optional[date] = None
    # Pack 50.9-A — Справка СТД-Р (найм)
    stdr_issue_date: Optional[date] = None
    stdr_records_override: Optional[List[dict]] = None


@router.patch("/{app_id}")
def patch_application(
    app_id: int,
    payload: ApplicationPatch,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """
    Pack 8.7: частичное обновление заявки.

    Принимает любой набор полей. Незаданные поля не трогает.
    Валидирует foreign keys только для тех связей которые передаются.
    Автоматически переводит статус в ASSIGNED если все 4 связи готовы.

    Pack 20.0: убрана валидация связи Position-Company (Position больше
    не привязан к Company; Company и Position на Application выбираются
    независимо).
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Валидация foreign keys только для тех что передаются
    if "company_id" in update_data and update_data["company_id"] is not None:
        company = session.get(Company, update_data["company_id"])
        if not company or not company.is_active:
            raise HTTPException(422, "Company not found or inactive")

    if "position_id" in update_data and update_data["position_id"] is not None:
        position = session.get(Position, update_data["position_id"])
        if not position:
            raise HTTPException(422, "Position not found")
        # Pack 20.0: убрана проверка position.company_id == app.company_id —
        # Position больше не привязан к Company.

    if "representative_id" in update_data and update_data["representative_id"] is not None:
        rep = session.get(Representative, update_data["representative_id"])
        if not rep or not rep.is_active:
            raise HTTPException(422, "Representative not found or inactive")

    if "spain_address_id" in update_data and update_data["spain_address_id"] is not None:
        addr = session.get(SpainAddress, update_data["spain_address_id"])
        if not addr or not addr.is_active:
            raise HTTPException(422, "Spain address not found or inactive")

    # Применяем изменения
    for field, value in update_data.items():
        setattr(app, field, value)

    # Auto-transition в ASSIGNED если все связи готовы
    has_full_assignment = (
        app.company_id and app.position_id and
        app.representative_id and app.spain_address_id and
        app.contract_number and app.contract_sign_date and
        app.contract_sign_city and app.salary_rub
    )
    if has_full_assignment and app.status in (
        ApplicationStatus.READY_TO_ASSIGN, ApplicationStatus.AWAITING_DATA
    ):
        app.status = ApplicationStatus.ASSIGNED

    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_patched",
        f"Updated fields: {', '.join(update_data.keys())}",
        update_data,
    )
    session.commit()
    session.refresh(app)

    # Pack 37.2: если изменились company/position/contract_sign_date — синк work_history.
    # Это держит applicant.work_history[0] = DN-employer (Pack 25.7 на уровне БД,
    # а не только в CV-рендерере). Безопасно — sync делает no-op если данных не хватает.
    _wh_trigger_fields = {"company_id", "position_id", "contract_sign_date"}
    if _wh_trigger_fields & set(update_data.keys()):
        sync_dn_work_record_safe(app, session)
        session.refresh(app)

    return _enrich(app, session)


# ============================================================================
# Recommendation
# ============================================================================

@router.post("/{app_id}/recommendation")
async def request_recommendation(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    if not app.applicant_id:
        raise HTTPException(422, "Applicant data not yet filled")

    applicant = session.get(Applicant, app.applicant_id)
    positions = session.exec(
        select(Position).where(Position.is_active == True)  # noqa: E712
    ).all()
    if not positions:
        raise HTTPException(422, "No active positions to recommend from")

    result = await recommendation.recommend_position(applicant, positions)
    app.recommendation_snapshot = result
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "recommendation_requested",
        f"LLM recommendation generated", result,
    )
    session.commit()
    return result


# ============================================================================
# Assignment (legacy POST /assign — оставлен для обратной совместимости)
# ============================================================================

@router.post("/{app_id}/assign")
def assign_application(
    app_id: int,
    payload: ApplicationAssign,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """
    Старый endpoint — требует все поля сразу. Для частичного обновления
    используйте PATCH /admin/applications/{id}.

    Pack 20.0: убрана проверка `position.company_id != company.id`.
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    company = session.get(Company, payload.company_id)
    if not company or not company.is_active:
        raise HTTPException(422, "Company not found or inactive")
    position = session.get(Position, payload.position_id)
    # Pack 20.0: position больше не имеет company_id, проверяем только наличие
    if not position:
        raise HTTPException(422, "Position not found")
    rep = session.get(Representative, payload.representative_id)
    if not rep or not rep.is_active:
        raise HTTPException(422, "Representative not found or inactive")
    addr = session.get(SpainAddress, payload.spain_address_id)
    if not addr or not addr.is_active:
        raise HTTPException(422, "Spain address not found or inactive")

    app.company_id = payload.company_id
    app.position_id = payload.position_id
    app.representative_id = payload.representative_id
    app.spain_address_id = payload.spain_address_id
    app.contract_number = payload.contract_number
    app.contract_sign_date = payload.contract_sign_date
    app.contract_sign_city = payload.contract_sign_city
    app.contract_end_date = payload.contract_end_date
    app.salary_rub = payload.salary_rub
    if payload.submission_date:
        app.submission_date = payload.submission_date
    if payload.payments_period_months:
        app.payments_period_months = payload.payments_period_months
    # Pack 36.1: TIE поля — обнулять можно явной пустой строкой/None через PATCH
    if payload.nie is not None:
        app.nie = payload.nie or None
    if payload.fingerprint_date is not None:
        app.fingerprint_date = payload.fingerprint_date

    if app.status in (ApplicationStatus.READY_TO_ASSIGN, ApplicationStatus.AWAITING_DATA):
        app.status = ApplicationStatus.ASSIGNED

    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_assigned",
        f"Assigned: {company.short_name} / {position.title_ru}",
    )
    session.commit()
    session.refresh(app)

    # Pack 37.2: sync applicant.work_history с DN-employer-ом
    sync_dn_work_record_safe(app, session)
    session.refresh(app)

    return _enrich(app, session)


# ============================================================================
# Status — liberal (без strict status_machine)
# ============================================================================

@router.post("/{app_id}/status")
def update_status(
    app_id: int,
    payload: ApplicationStatusUpdate,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    old_status = app.status
    app.status = payload.new_status
    if payload.notes:
        app.status_notes = payload.notes
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "status_changed",
        f"Status: {old_status.value if hasattr(old_status, 'value') else old_status} > {payload.new_status.value}",
        {"old": str(old_status), "new": payload.new_status.value, "notes": payload.notes},
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


# ============================================================================
# Document generation
# ============================================================================

# ----------------------------------------------------------------------------
# Pack 57.0 — helpers для auto-translate выписки на download
# ----------------------------------------------------------------------------

# Locks per app_id, чтобы параллельные download'ы одной заявки не запускали
# два независимых LLM-перевода. Module-level dict; OK для single-worker Railway.
_BANK_TRANSLATE_LOCKS: dict[int, asyncio.Lock] = {}


async def _ensure_bank_statement_translation(app, session) -> bytes | None:
    """
    Pack 57.0 — гарантирует наличие перевода выписки для v2 заявки.

    Возвращает:
      None — если v1 (legacy), перевод не нужен/невозможен.
      bytes (ES docx из R2) — если есть существующий перевод ИЛИ только что сделан.

    Кеш: если Application.bank_statement_translation_storage_key уже стоит —
    читаем R2 БЕЗ LLM-вызова. Если нет — выполняем полный pipeline
    (render_bank_statement_for_translation → translate_docx → save R2 → update DB).

    Параллельные вызовы для одного app_id сериализуются через asyncio.Lock.
    Второй и последующие клиенты ждут первого и получают тот же кешированный
    результат — без повторных LLM-запросов.

    Перегенерация (свежий LLM при существующем переводе) — ТОЛЬКО через
    отдельный endpoint /bank-statement/translate (кнопка «Перевести выписку»).
    """
    if bool(getattr(app, "bank_template_legacy_v1", True)):
        return None

    app_id = app.id
    lock = _BANK_TRANSLATE_LOCKS.setdefault(app_id, asyncio.Lock())

    async with lock:
        # Re-check после захвата лока: за время ожидания другой вызов мог
        # успешно завершить перевод и обновить translation_storage_key.
        session.refresh(app)
        existing_key = getattr(app, "bank_statement_translation_storage_key", None)

        from app.services.storage import get_storage
        storage = get_storage()

        if existing_key:
            try:
                return storage.read(existing_key)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Pack 57.0: translation_storage_key=%s missing in R2, will re-translate: %s",
                    existing_key, e,
                )
                # fallthrough → перевод заново

        # Нет перевода (или R2-файл потерян) — выполняем полный pipeline
        import time
        from app.templates_engine.docx_renderer import render_bank_statement_for_translation
        from app.services.translation import translate_docx, build_substitution_dict
        from app.models import Applicant as _Applicant, Company as _Company

        ru_docx_bytes = render_bank_statement_for_translation(app, session)

        applicant = session.get(_Applicant, app.applicant_id) if app.applicant_id else None
        company = session.get(_Company, app.company_id) if app.company_id else None
        substitutions = None
        if applicant or company:
            substitutions = build_substitution_dict(app, applicant, company)

        es_docx_bytes = await translate_docx(ru_docx_bytes, substitutions=substitutions)

        new_key = f"translations/bank_statement_{app_id}_{int(time.time())}.docx"
        storage.save(
            new_key,
            es_docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        old_key = existing_key
        app.bank_statement_translation_storage_key = new_key
        session.add(app)
        session.commit()

        if old_key and old_key != new_key:
            try:
                storage.delete(old_key)
            except Exception:
                pass

        return es_docx_bytes


def _replace_in_zip(
    zip_bytes: bytes, *, old_filename: str, new_filename: str, new_content: bytes
) -> bytes:
    """
    Pack 57.0 — заменяет файл в ZIP-архиве (для замены DOCX выписки на PDF
    для v2 банков в render_package). Если old_filename отсутствует — просто
    добавляет new_filename с новым content (degraded-safe).
    """
    import zipfile
    src = io.BytesIO(zip_bytes)
    dst = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            if name == old_filename:
                continue
            zout.writestr(name, zin.read(name))
        zout.writestr(new_filename, new_content)
    return dst.getvalue()


# ----------------------------------------------------------------------------

@router.post("/{app_id}/render-package")
async def render_package(  # Pack 57.0: def → async (для await _ensure_...)
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    problems = app.validate_business_rules()
    if problems:
        raise HTTPException(422, detail={"problems": problems})

    # Pack 57.0: для v2 банков заранее гарантируем перевод (если ещё не было)
    # ПЕРЕД сборкой ZIP. Это может занять ~30-60 сек на свежем LLM-запросе.
    # Если перевод уже есть — мгновенно вернётся cached bytes.
    is_v2 = not bool(getattr(app, "bank_template_legacy_v1", True))
    es_docx_bytes = None
    if is_v2:
        try:
            es_docx_bytes = await _ensure_bank_statement_translation(app, session)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(
                "Pack 57.0: bank statement auto-translate for ZIP failed: %s", e
            )
            # degraded: ZIP уйдёт с RU only, не падаем

    zip_bytes, status = build_full_package(app, session, include_bank_statement=True)

    # Pack 57.0: для v2 банков заменяем DOCX выписки на PDF в архиве.
    # build_full_package кладёт «10_Выписка_по_счету.docx» — для v2 нам нужен
    # «10_Выписка.pdf» (combined RU+ES если есть перевод, иначе RU only).
    if is_v2:
        try:
            from app.templates_engine.docx_renderer import (
                render_bank_statement_to_pdf,
                render_bank_statement_combined_to_pdf,
            )
            if es_docx_bytes:
                pdf_bytes = render_bank_statement_combined_to_pdf(app, session, es_docx_bytes)
                status["bank_statement"] = "ok (PDF combined)"
            else:
                pdf_bytes = render_bank_statement_to_pdf(app, session)
                status["bank_statement"] = "ok (PDF RU only)"
            zip_bytes = _replace_in_zip(
                zip_bytes,
                old_filename="10_Выписка_по_счету.docx",
                new_filename="10_Выписка.pdf",
                new_content=pdf_bytes,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(
                "Pack 57.0: failed to replace bank_statement DOCX → PDF in ZIP: %s", e
            )
            # ZIP уйдёт с DOCX выпиской — degraded-safe

    # Pack 42.0 — авто-выставление статуса DRAFTS_GENERATED убрано.
    # Менеджер вручную через dropdown выставляет "Документы готовы"
    # после того как САМ проверил все документы.
    _log_event(
        session, app.id, "manager", user_id, "package_generated",
        f"Generated package with {sum(1 for v in status.values() if v == 'ok')} docs",
        status,
    )
    session.commit()

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="package_{app.reference}.zip"'},
    )


# ============================================================================
# Pack 9.1: скачивание одного файла из пакета
# ============================================================================

# Маппинг идентификатора файла > (тип, генератор)
# id используется в URL чтобы не передавать русские/испанские имена с пробелами
_DOWNLOAD_FILES = {
    # DOCX (рендерятся через templates_engine)
    "contract":         {"name": "01_Договор.docx",            "kind": "docx", "fn": render_contract,     "args": ()},
    "act_1":            {"name": "02_Акт_1.docx",              "kind": "docx", "fn": render_act,          "args": (1,)},
    "act_2":            {"name": "03_Акт_2.docx",              "kind": "docx", "fn": render_act,          "args": (2,)},
    "act_3":            {"name": "04_Акт_3.docx",              "kind": "docx", "fn": render_act,          "args": (3,)},
    "invoice_1":        {"name": "05_Счёт_1.docx",             "kind": "docx", "fn": render_invoice,      "args": (1,)},
    "invoice_2":        {"name": "06_Счёт_2.docx",             "kind": "docx", "fn": render_invoice,      "args": (2,)},
    "invoice_3":        {"name": "07_Счёт_3.docx",             "kind": "docx", "fn": render_invoice,      "args": (3,)},
    "employer_letter":  {"name": "08_Письмо.docx",             "kind": "docx", "fn": render_employer_letter, "args": ()},
    "cv":               {"name": "09_Резюме.docx",             "kind": "docx", "fn": render_cv,           "args": ()},
    "bank_statement":   {"name": "10_Выписка.docx",            "kind": "docx", "fn": render_bank_statement, "args": ()},
    # PDF (рендерятся через pdf_forms_engine, имена соответствуют ключам в build_pdf_forms)
    "mi_t":             {"name": "11_MI-T.pdf",                                 "kind": "pdf", "pdf_key": "11_MI-T.pdf"},
    "designacion":      {"name": "12_Designacion_representante.pdf",            "kind": "pdf", "pdf_key": "12_Designacion_representante.pdf"},
    "compromiso":       {"name": "13_Compromiso_RETA.pdf",                      "kind": "pdf", "pdf_key": "13_Compromiso_RETA.pdf"},
    "declaracion":      {"name": "14_Declaracion_antecedentes.pdf",             "kind": "pdf", "pdf_key": "14_Declaracion_antecedentes.pdf"},
    # Pack 36.1: TIE формы (генерятся только если application.nie + fingerprint_date заполнены)
    "mi_tie":           {"name": "15_MI-TIE.pdf",                                "kind": "pdf", "pdf_key": "15_MI-TIE.pdf"},
    "ex17":             {"name": "16_EX-17.pdf",                                 "kind": "pdf", "pdf_key": "16_EX-17.pdf"},
       # Pack 18.3 — справка о постановке на учёт самозанятого (КНД 1122035)
    "npd_certificate":  {"name": "15_Справка_НПД.docx",        "kind": "docx", "fn": render_npd_certificate, "args": ()},  # < ДОБАВИТЬ 
    # Pack 18.3.3 — тот же документ в формате ЛКН (электронная подпись ФНС внизу, без блока МФЦ)
    "npd_certificate_lkn": {"name": "15b_Справка_НПД_ЛКН.docx", "kind": "docx", "fn": render_npd_certificate_lkn, "args": ()},
    # Pack 18.9 — апостиль к справке НПД
    "apostille":           {"name": "16_Апостиль.docx",         "kind": "docx", "fn": render_apostille,         "args": ()},
    # Pack 40.0-G — Техническое заключение
    "tech_opinion":        {"name": "17_Техническое_заключение.docx", "kind": "docx", "fn": render_tech_opinion, "args": ()},
    # Pack 50.7-C — Приказ Т-9 о командировке (только для EMPLOYMENT)
    "business_trip_order": {"name": "17_Приказ_на_командировку.docx", "kind": "docx", "fn": render_business_trip_order, "args": ()},
    # Pack 50.1-C — Трудовой договор (только для EMPLOYMENT)
    "employment_contract":  {"name": "01_Трудовой_договор.docx", "kind": "docx", "fn": render_employment_contract, "args": ()},
    # Pack 50.8-B — Справка 2-НДФЛ (только для EMPLOYMENT)
    "ndfl_2":               {"name": "18_2-НДФЛ.docx", "kind": "docx", "fn": render_ndfl_2, "args": ()},
    # Pack 50.9-B — Справка СТД-Р (только для EMPLOYMENT)
    "stdr":                 {"name": "19_СТД-Р.docx", "kind": "docx", "fn": render_stdr, "args": ()},
    # Pack 50.10-B — Расчётный листок ×3 (только для EMPLOYMENT)
    "payslip_1":            {"name": "20_Расчётный_листок_1.docx", "kind": "docx", "fn": render_payslip, "args": (0,)},
    "payslip_2":            {"name": "21_Расчётный_листок_2.docx", "kind": "docx", "fn": render_payslip, "args": (1,)},
    "payslip_3":            {"name": "22_Расчётный_листок_3.docx", "kind": "docx", "fn": render_payslip, "args": (2,)},
    # Pack 50.11-B — Письмо работодателя (найм)
    "employer_letter_naim": {"name": "23_Письмо_работодателя.docx", "kind": "docx", "fn": render_employer_letter_naim, "args": ()},
    # Pack 50.12-D — Свидетельство об отъезде (СОО)
    "soo":                  {"name": "24_Свидетельство_об_отъезде.docx", "kind": "docx", "fn": render_soo, "args": ()},
    # Pack 50.20 — Апостиль Минфина/СФР (найм)
    "apostille_sfr":        {"name": "25_Апостиль_СФР.docx", "kind": "docx", "fn": render_apostille_sfr, "args": ()},
}


@router.get("/{app_id}/download-file/{file_id}")
async def download_single_file(  # Pack 57.0: def → async (для await _ensure_...)
    app_id: int,
    file_id: str,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Pack 9.1: скачать один файл (DOCX или PDF) на лету.

    Используется в DocumentsGrid — клик по карточке скачивает файл.
    Не сохраняет файл на диск — генерирует и стримит.

    Pack 57.0: для bank_statement v2 без существующего перевода — автоматически
    запускает LLM-перевод (~30-60 сек) и возвращает combined PDF одним response-ом.
    Если перевод уже есть (translation_storage_key) — отдаёт без LLM-вызова.
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    if file_id not in _DOWNLOAD_FILES:
        raise HTTPException(404, f"Unknown file: {file_id}")

    spec = _DOWNLOAD_FILES[file_id]
    filename = spec["name"]

    # Pack 52 PDF: bank_statement для v2 → PDF (v1 legacy → DOCX через старый путь ниже).
    # Pack 53: если есть перевод → combined PDF (RU + ES).
    # Pack 57.0: если v2 + нет перевода → автоматически переводим перед отдачей.
    if file_id == "bank_statement" and not bool(getattr(app, "bank_template_legacy_v1", True)):
        try:
            from app.templates_engine.docx_renderer import (
                render_bank_statement_to_pdf,
                render_bank_statement_combined_to_pdf,
            )
            # Pack 57.0: auto-translate если ещё не было; cached если уже было.
            # Параллельные клики сериализуются через asyncio.Lock per app_id.
            es_docx_bytes = await _ensure_bank_statement_translation(app, session)
            if es_docx_bytes is not None:
                content = render_bank_statement_combined_to_pdf(app, session, es_docx_bytes)
            else:
                # Safety net — для v2 не должно срабатывать (ensure возвращает None
                # только для v1). На всякий случай оставляем fallback на RU only.
                content = render_bank_statement_to_pdf(app, session)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Pack 52/53/57: failed to render bank_statement PDF")
            raise HTTPException(
                500,
                f"Failed to render bank_statement PDF: {type(e).__name__}: {e}",
            )
        filename = "10_Выписка.pdf"
        from urllib.parse import quote
        safe_name = quote(filename)
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
        )

    try:
        if spec["kind"] == "docx":
            content = spec["fn"](app, session, *spec["args"])
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif spec["kind"] == "pdf":
            # Пути берутся из rendering.py — те же что для ZIP
            templates_root = Path(__file__).resolve().parent.parent.parent.parent / "templates"
            pdf_forms = build_pdf_forms(app, session, templates_root)
            content = pdf_forms.get(spec["pdf_key"])
            if content is None:
                raise HTTPException(500, f"Failed to generate PDF: {file_id}")
            media_type = "application/pdf"
        else:
            raise HTTPException(500, f"Unknown kind: {spec['kind']}")
    except HTTPException:
        raise
    except Exception as e:
        # Pack 35.6: логируем traceback чтобы Railway Deploy Logs показал точную строку
        import logging
        logging.getLogger(__name__).exception(f"Failed to render {file_id}")
        raise HTTPException(500, f"Failed to render {file_id}: {type(e).__name__}: {e}")

    # encode имя файла для Content-Disposition (русские буквы)
    from urllib.parse import quote
    safe_name = quote(filename)

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}",
        },
    )


# ============================================================================
# Pack 10: архивирование завершённых заявок
# ============================================================================

@router.post("/{app_id}/archive")
def archive_application(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """
    Архивирует завершённую заявку.

    Доступно только для финальных статусов: APPROVED, REJECTED, CANCELLED.
    Заявка пропадает из основного списка /admin, появляется в /admin/archive.
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    if app.is_archived:
        raise HTTPException(409, "Application is already archived")
    if not app.can_be_archived():
        raise HTTPException(
            422,
            f"Cannot archive: status is '{app.status}'. "
            f"Only approved/rejected/cancelled applications can be archived.",
        )

    app.is_archived = True
    app.archived_at = datetime.utcnow()
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_archived",
        f"Заявка перенесена в архив (статус: {app.status})",
        {"status_at_archive": str(app.status)},
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


# ============================================================================
# Pack 30.0 — флаг "срочно" (toggle)
# ============================================================================

@router.post("/{app_id}/toggle-paid")
def toggle_paid(
    app_id: int,
    session: Session = Depends(get_session),
    _: str = Depends(require_manager),
):
    """Переключает флаг is_paid (Оплачен)."""
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Not found")
    new_value = not bool(getattr(app, "is_paid", False))
    app.is_paid = new_value
    session.add(app)
    session.commit()
    session.refresh(app)
    return {"is_paid": new_value}


@router.post("/{app_id}/toggle-urgent")
def toggle_urgent(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """Переключает флаг is_urgent. Срочные заявки выходят на верх списка
    в /admin (внутри urgent-группы — по алфавиту ФИО)."""
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    new_value = not bool(getattr(app, "is_urgent", False))
    app.is_urgent = new_value
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id,
        "application_urgent_toggled",
        f"is_urgent set to {new_value}",
        {"is_urgent": new_value},
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


# ============================================================================
# Pack 36.0 — флаг «Подан» (toggle)

@router.post("/{app_id}/toggle-filed")
def toggle_filed(
    app_id: int,
    db: Session = Depends(get_session),
    _: str = Depends(require_manager),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.is_filed = not bool(app.is_filed)
    db.commit()
    db.refresh(app)
    db.refresh(app)
    return _enrich(app, db)


# Pack 34.2 — флаг "Готово, можно забирать" (toggle)
# ============================================================================

@router.post("/{app_id}/toggle-ready")
def toggle_ready_for_pickup(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """Переключает флаг is_ready_for_pickup. Заявки с готовыми документами
    показываются ниже срочных (приоритет огня), но выше обычных.
    Внутри ready-группы — алфавит ФИО."""
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    new_value = not bool(getattr(app, "is_ready_for_pickup", False))
    app.is_ready_for_pickup = new_value
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id,
        "application_ready_for_pickup_toggled",
        f"is_ready_for_pickup set to {new_value}",
        {"is_ready_for_pickup": new_value},
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


@router.post("/{app_id}/unarchive")
def unarchive_application(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """
    Возвращает заявку из архива в основной список.
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    if not app.is_archived:
        raise HTTPException(409, "Application is not archived")

    app.is_archived = False
    app.archived_at = None
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_unarchived",
        "Заявка возвращена из архива",
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


# ============================================================================
# Pack 27.0 - орзина (soft-delete с автоудалением через 7 дней)
# ============================================================================


def _permanent_delete_application(session: Session, app: Application) -> None:
    """Pack 27.0 - Permanent delete: R2 файлы + 7 связанных таблиц + сама application."""
    from app.services.storage import get_storage
    from sqlalchemy import text as sql_text
    storage = get_storage()
    keys_to_delete = []

    rows = session.connection().execute(
        sql_text("SELECT storage_key, original_storage_key FROM applicant_document WHERE application_id = :aid"),
        {"aid": app.id}
    ).fetchall()
    for sk, osk in rows:
        if sk: keys_to_delete.append(sk)
        if osk: keys_to_delete.append(osk)

    rows = session.connection().execute(
        sql_text("SELECT s3_key FROM generated_document WHERE application_id = :aid"),
        {"aid": app.id}
    ).fetchall()
    for (sk,) in rows:
        if sk: keys_to_delete.append(sk)

    rows = session.connection().execute(
        sql_text("SELECT s3_key FROM uploaded_file WHERE application_id = :aid"),
        {"aid": app.id}
    ).fetchall()
    for (sk,) in rows:
        if sk: keys_to_delete.append(sk)

    import logging
    log = logging.getLogger(__name__)
    deleted_count = 0
    for key in keys_to_delete:
        try:
            if hasattr(storage, "delete"):
                storage.delete(key)
            elif hasattr(storage, "delete_object"):
                storage.delete_object(key)
            elif hasattr(storage, "client") and hasattr(storage, "bucket_name"):
                storage.client.delete_object(Bucket=storage.bucket_name, Key=key)
            deleted_count += 1
        except Exception as e:
            log.warning(f"Pack 27.0: failed to delete R2 key {key}: {e}")

    log.info(f"Pack 27.0: permanent delete app {app.id}, R2 deleted {deleted_count}/{len(keys_to_delete)}")

    for tbl in ("applicant_document", "generated_document", "uploaded_file",
                "family_member", "previous_residence", "timeline_event", "translation"):
        session.connection().execute(
            sql_text(f"DELETE FROM {tbl} WHERE application_id = :aid"),
            {"aid": app.id}
        )

    session.delete(app)


@router.delete("/{app_id}", status_code=200)
def soft_delete_application(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """Pack 27.0 - Soft-delete (в корзину). з любого статуса. сли в архиве - выводит и удаляет."""
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    if app.deleted_at is not None:
        raise HTTPException(409, "Application is already in trash")

    was_archived = app.is_archived
    if was_archived:
        app.is_archived = False
        app.archived_at = None
    app.deleted_at = datetime.utcnow()
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_deleted",
        f"аявка перемещена в корзину (статус: {app.status}{'; была в архиве' if was_archived else ''})",
        {"status_at_delete": str(app.status), "was_archived": was_archived},
    )
    session.commit()
    session.refresh(app)
    return {"id": app.id, "deleted_at": app.deleted_at.isoformat()}


@router.post("/{app_id}/restore", status_code=200)
def restore_application(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """Pack 27.0 - осстановить заявку из корзины."""
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    if app.deleted_at is None:
        raise HTTPException(409, "Application is not in trash")
    app.deleted_at = None
    session.add(app)
    _log_event(session, app.id, "manager", user_id, "application_restored",
               "аявка восстановлена из корзины")
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


@router.delete("/{app_id}/permanent", status_code=200)
def permanent_delete_application_endpoint(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """Pack 27.0 - Permanent delete: R2 + связанные таблицы + application.  Т."""
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    ref = app.reference
    _log_event(session, app.id, "manager", user_id, "application_permanently_deleted",
               f"аявка удалена навсегда (reference: {ref})",
               {"reference": ref, "status": str(app.status)})
    _permanent_delete_application(session, app)
    session.commit()
    return {"deleted": True, "reference": ref}




# ============================================================================
# Pack 50.0-B — смена типа заявки (Самозанятый / Найм)
# ============================================================================

class ApplicationChangeTypeRequest(BaseModel):
    """Pack 50.0-B — payload для смены типа заявки."""
    application_type: ApplicationType
    # Не требуется confirm=true в payload — двойное window.confirm() делается
    # на фронтенде (UX-решение из обсуждения Pack 50.0).


@router.post("/{app_id}/change-type")
def change_application_type(
    app_id: int,
    payload: ApplicationChangeTypeRequest,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """Pack 50.0-B — сменить тип заявки.

    При смене типа выполняется КАСКАД:
    1. Удаляются все сгенерированные документы (generated_document) — R2 + БД.
       (Не трогаем applicant_document — сканы клиента не зависят от типа;
        не трогаем uploaded_file — импортный сырой материал.)
    2. Сбрасываются поля, специфичные для типа заявки:
       company_id, position_id, contract_*, salary_rub, employer_letter_*,
       outgoing_*, tech_opinion_override_text, recommendation_snapshot,
       bank_* поля (выписка перегенерируется в другом режиме), tasa_nrc,
       monthly_documents_override, eur_rate_override.
    3. Статус сбрасывается в AWAITING_DATA (потому что critical поля очищены).
    4. Сам тип меняется на payload.application_type.

    Это безвозвратное действие — на фронте уже было два window.confirm().
    """
    from app.services.storage import get_storage
    from sqlalchemy import text as sql_text
    import logging
    log = logging.getLogger(__name__)

    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    old_type = app.application_type
    new_type = payload.application_type

    if old_type == new_type:
        # No-op, но возвращаем актуальное состояние без перетряски документов.
        return _enrich(app, session)

    # 1. Удаляем generated_document из R2 + БД.
    storage = get_storage()
    rows = session.connection().execute(
        sql_text("SELECT s3_key FROM generated_document WHERE application_id = :aid"),
        {"aid": app.id},
    ).fetchall()
    r2_keys = [sk for (sk,) in rows if sk]

    deleted_count = 0
    for key in r2_keys:
        try:
            if hasattr(storage, "delete"):
                storage.delete(key)
            elif hasattr(storage, "delete_object"):
                storage.delete_object(key)
            elif hasattr(storage, "client") and hasattr(storage, "bucket_name"):
                storage.client.delete_object(Bucket=storage.bucket_name, Key=key)
            deleted_count += 1
        except Exception as e:
            log.warning(f"Pack 50.0-B: failed to delete R2 key {key}: {e}")

    log.info(
        f"Pack 50.0-B: change-type app {app.id} {old_type} -> {new_type}, "
        f"R2 deleted {deleted_count}/{len(r2_keys)}"
    )

    # Удаляем записи в БД
    session.connection().execute(
        sql_text("DELETE FROM generated_document WHERE application_id = :aid"),
        {"aid": app.id},
    )

    # 2. Сбрасываем type-specific поля.
    _fields_to_reset = [
        # связи
        "company_id", "position_id",
        # договор
        "contract_number", "contract_sign_date", "contract_sign_city",
        "contract_end_date", "salary_rub",
        # письмо работодателя
        "employer_letter_number", "employer_letter_date",
        "outgoing_number", "outgoing_date",
        # tech opinion
        "tech_opinion_override_text",
        # recommendation snapshot (она для конкретного типа специальности/уровня)
        "recommendation_snapshot",
        # банковская выписка — для найма режим другой (SALARY_ONLY mode в Pack 50.8)
        "bank_transactions_override",
        "bank_statement_date",
        "bank_period_start", "bank_period_end",
        "bank_opening_balance",
        "bank_npd_rate", "bank_monthly_fee",
        # ежемесячные акты/счета (для DN — список месяцев)
        "monthly_documents_override",
        "eur_rate_override",
        # пошлина
        "tasa_nrc",
    ]
    for field in _fields_to_reset:
        if hasattr(app, field):
            setattr(app, field, None)

    # 3. Статус сбрасываем — поля очищены, заявка снова в "ждём данных".
    app.status = ApplicationStatus.AWAITING_DATA

    # 4. Меняем тип.
    app.application_type = new_type

    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_type_changed",
        f"Changed type {old_type} -> {new_type}, "
        f"reset type-specific fields, deleted {deleted_count} generated docs",
        {
            "old_type": str(old_type),
            "new_type": str(new_type),
            "deleted_generated_documents": deleted_count,
        },
    )
    session.commit()
    session.refresh(app)

    return _enrich(app, session)



# ============================================================================
# Pack 53 — Перевод банковской выписки (отдельный flow от orchestrator)
# ============================================================================

@router.post("/{app_id}/bank-statement/translate")
async def translate_bank_statement(
    app_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Pack 53: переводит банковскую выписку на испанский и сохраняет в R2.

    Каждое нажатие — новый LLM-запрос (~30-60 сек). Результат:
    - Application.bank_statement_translation_storage_key обновляется на новый key
    - старый R2-файл (если был) удаляется
    - последующие /download-file/bank_statement будут отдавать combined PDF (RU+ES)

    Возвращает: {"status": "done", "storage_key": "..."}.
    При ошибке: 500 с сообщением.

    Endpoint async — translate_docx тоже async, дёргаем напрямую через await.
    Frontend ждёт ~60 сек на одном fetch().
    """
    import time

    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    if bool(getattr(app, "bank_template_legacy_v1", True)):
        raise HTTPException(
            400,
            "Перевод доступен только для v2-выписок (bank_template_legacy_v1=False).",
        )

    # Этап 1: render RU docx без печатей (но с лейблами для перевода)
    try:
        from app.templates_engine.docx_renderer import render_bank_statement_for_translation
        ru_docx_bytes = render_bank_statement_for_translation(app, session)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Pack 53: render_bank_statement_for_translation failed")
        raise HTTPException(500, f"Render failed: {type(e).__name__}: {e}")

    # Этап 2: build substitutions + translate через LLM
    try:
        from app.services.translation import translate_docx, build_substitution_dict
        from app.models import Applicant as _Applicant, Company as _Company

        applicant = session.get(_Applicant, app.applicant_id) if app.applicant_id else None
        company = session.get(_Company, app.company_id) if app.company_id else None

        substitutions = None
        if applicant or company:
            substitutions = build_substitution_dict(app, applicant, company)

        es_docx_bytes = await translate_docx(ru_docx_bytes, substitutions=substitutions)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Pack 53: translate_docx failed")
        raise HTTPException(500, f"Translation failed: {type(e).__name__}: {e}")

    # Этап 3: save to R2 (новый key, потом удалим старый)
    from app.services.storage import get_storage
    storage = get_storage()
    old_key = getattr(app, "bank_statement_translation_storage_key", None)
    new_key = f"translations/bank_statement_{app_id}_{int(time.time())}.docx"

    try:
        storage.save(
            new_key,
            es_docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Pack 53: R2 save failed")
        raise HTTPException(500, f"Storage save failed: {type(e).__name__}: {e}")

    # Этап 4: update Application + remove old R2 key
    app.bank_statement_translation_storage_key = new_key
    session.add(app)
    session.commit()

    if old_key and old_key != new_key:
        try:
            storage.delete(old_key)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Pack 53: failed to delete old key {old_key}: {e}")

    return {"status": "done", "storage_key": new_key}

