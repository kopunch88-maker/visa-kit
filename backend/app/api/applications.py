"""
Applications router — Pack 8.7 — добавлен PATCH endpoint для partial-update.

Изменения по сравнению с Pack 8.5:
- Новый endpoint PATCH /admin/applications/{id} — частичное обновление
  любых полей заявки, в т.ч. данных распределения. Не требует чтобы все
  поля были заполнены сразу.
- Старый POST /assign оставлен для обратной совместимости.
"""

import io
import secrets
from datetime import date, datetime
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
    Applicant, Company, Position, Representative, SpainAddress,
    TimelineEvent,
)
from app.services import recommendation
from app.services.rendering import build_full_package
from app.templates_engine import (
    render_contract, render_act, render_invoice,
    render_employer_letter, render_cv, render_bank_statement,
)
from app.pdf_forms_engine import build_pdf_forms
from .dependencies import require_manager, current_user_id

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


def _log_event(
    session: Session, application_id: int, actor_type: str, actor_id: Optional[int],
    event_type: str, summary: str, payload: Optional[dict] = None,
) -> None:
    event = TimelineEvent(
        application_id=application_id, actor_type=actor_type, actor_id=actor_id,
        event_type=event_type, summary=summary, payload=_json_safe(payload or {}),
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
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> List[dict]:
    query = select(Application).where(Application.is_archived == archived)
    query = query.order_by(Application.created_at.desc())
    if status:
        query = query.where(Application.status == status)
    return [_enrich(a, session) for a in session.exec(query).all()]


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

    app = Application(
        reference=reference,
        client_access_token=secrets.token_urlsafe(32),
        status=ApplicationStatus.AWAITING_DATA,
        assigned_manager_id=user_id,
        internal_notes=payload.notes,
        submission_date=payload.submission_date,
    )
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
    payments_period_months: Optional[int] = None
    internal_notes: Optional[str] = None
    # Pack 9: NRC квитанции пошлины (для PDF-форм MI-T)
    tasa_nrc: Optional[str] = None


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
        # Если меняется только position но не company — проверяем что position принадлежит текущей компании
        target_company_id = update_data.get("company_id", app.company_id)
        if target_company_id and position.company_id != target_company_id:
            raise HTTPException(422, "Position doesn't belong to selected company")

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
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    company = session.get(Company, payload.company_id)
    if not company or not company.is_active:
        raise HTTPException(422, "Company not found or inactive")
    position = session.get(Position, payload.position_id)
    if not position or position.company_id != company.id:
        raise HTTPException(422, "Position not found or doesn't belong to company")
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

    if app.status in (ApplicationStatus.READY_TO_ASSIGN, ApplicationStatus.AWAITING_DATA):
        app.status = ApplicationStatus.ASSIGNED

    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_assigned",
        f"Assigned: {company.short_name} / {position.title_ru}",
    )
    session.commit()
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
        f"Status: {old_status.value if hasattr(old_status, 'value') else old_status} → {payload.new_status.value}",
        {"old": str(old_status), "new": payload.new_status.value, "notes": payload.notes},
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


# ============================================================================
# Document generation
# ============================================================================

@router.post("/{app_id}/render-package")
def render_package(
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

    zip_bytes, status = build_full_package(app, session, include_bank_statement=True)
    if app.status == ApplicationStatus.ASSIGNED:
        app.status = ApplicationStatus.DRAFTS_GENERATED
        session.add(app)
        session.commit()
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

# Маппинг идентификатора файла → (тип, генератор)
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
}


@router.get("/{app_id}/download-file/{file_id}")
def download_single_file(
    app_id: int,
    file_id: str,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Pack 9.1: скачать один файл (DOCX или PDF) на лету.

    Используется в DocumentsGrid — клик по карточке скачивает файл.
    Не сохраняет файл на диск — генерирует и стримит.
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    if file_id not in _DOWNLOAD_FILES:
        raise HTTPException(404, f"Unknown file: {file_id}")

    spec = _DOWNLOAD_FILES[file_id]
    filename = spec["name"]

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
