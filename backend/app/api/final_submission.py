# -*- coding: utf-8 -*-
"""
Pack 39.0-B — Final Submission API router.

Endpoints для загрузки и управления физическими документами клиента
для финальной проверки перед подачей в консульство.

Все endpoints защищены через require_manager (router-level dependency).

Endpoints:
  POST   /admin/applicants/{id}/final-submission/upload
         Multipart upload N файлов. ZIP распаковываются рекурсивно.
         Дубли по SHA256 пропускаются, возвращаются в skipped_duplicates.

  GET    /admin/applicants/{id}/final-submission/documents
         Список документов. ?include_history=true показывает и неактивные.
         Каждый документ дополняется signed URL для скачивания.

  POST   /admin/applicants/{id}/final-submission/documents/{doc_id}/replace
         Заменить файл. Старый -> is_active=False, новый -> is_active=True
         с previous_version_id указывающим на старого. keep_category
         (default true) — копирует категорию старого.

  DELETE /admin/applicants/{id}/final-submission/documents/{doc_id}?hard=false
         Soft delete: is_active=False, replaced_at=NULL.
         hard=true: + удаление файла из R2.

  PATCH  /admin/applicants/{id}/final-submission/documents/{doc_id}/category
         Ручная коррекция категории документа (если AI ошибся).
"""
import logging
from typing import List, Optional

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Body,
    BackgroundTasks,  # Pack 39.0-C
)
from sqlmodel import Session, select

from app.db.session import get_session
from datetime import datetime  # Pack 39.0-D

from app.models import (
    Applicant,
    FinalSubmissionDocument,
    FinalSubmissionDocumentRead,
    FinalSubmissionUploadResponse,
    FinalSubmissionDocCategoryUpdateRequest,
    FinalSubmissionDocCategory,
    # Pack 39.0-D
    FinalSubmissionRunRequest,
    FinalSubmissionRunResponse,
    FinalSubmissionAuditReportRead,
    FinalSubmissionAuditReportWithFindings,
    FinalSubmissionFindingRead,
    FinalSubmissionAcknowledgeRequest,
    FinalSubmissionDismissRequest,
)
from app.services.storage import get_storage
from app.services.final_submission.upload_service import (
    save_one_file,
    extract_zip_recursive,
    validate_extension,
    MAX_TOTAL_UPLOAD_FS,
)
from app.services.final_submission.replace_service import replace_document

from .dependencies import require_manager, current_user_id


log = logging.getLogger(__name__)


router = APIRouter(
    prefix="/admin",
    tags=["final-submission"],
    dependencies=[Depends(require_manager)],
)


# ====================================================================
# Helpers
# ====================================================================

def _attach_download_url(
    doc: FinalSubmissionDocument,
    storage,
) -> FinalSubmissionDocumentRead:
    """
    SQLModel -> DTO + сгенерировать signed URL на лету.
    URL валиден 1 час.
    """
    download_url = None
    original_download_url = None
    try:
        if doc.storage_key:
            download_url = storage.get_url(doc.storage_key, expires_in=3600)
        if doc.original_storage_key:
            original_download_url = storage.get_url(
                doc.original_storage_key, expires_in=3600
            )
    except Exception as e:
        log.warning(f"Failed to generate signed URL for doc {doc.id}: {e}")

    return FinalSubmissionDocumentRead(
        id=doc.id,
        applicant_id=doc.applicant_id,
        application_id=doc.application_id,
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        file_size_bytes=doc.file_size_bytes,
        storage_key=doc.storage_key,
        original_storage_key=doc.original_storage_key,
        sha256=doc.sha256,
        doc_category=doc.doc_category,
        doc_category_confidence=doc.doc_category_confidence,
        doc_category_source=doc.doc_category_source,
        extraction_method=doc.extraction_method,
        page_count=doc.page_count,
        is_active=doc.is_active,
        previous_version_id=doc.previous_version_id,
        replaced_at=doc.replaced_at,
        uploaded_at=doc.uploaded_at,
        uploaded_by=doc.uploaded_by,
        download_url=download_url,
        original_download_url=original_download_url,
    )


def _ensure_applicant(session: Session, applicant_id: int) -> Applicant:
    """Получить applicant или 404."""
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail=f"Applicant {applicant_id} not found")
    return applicant


def _get_doc_or_404(
    session: Session,
    applicant_id: int,
    doc_id: int,
) -> FinalSubmissionDocument:
    """Получить документ по id, проверить что принадлежит applicant."""
    doc = session.get(FinalSubmissionDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    if doc.applicant_id != applicant_id:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id} does not belong to applicant {applicant_id}",
        )
    return doc


# ====================================================================
# POST /applicants/{id}/final-submission/upload
# ====================================================================

@router.post(
    "/applicants/{applicant_id}/final-submission/upload",
    response_model=FinalSubmissionUploadResponse,
)
async def upload_final_submission_documents(
    applicant_id: int,
    background_tasks: BackgroundTasks,  # Pack 39.0-C: extraction в фоне
    files: List[UploadFile] = File(...),
    application_id: Optional[int] = Form(default=None),
    session: Session = Depends(get_session),
    user_id: Optional[str] = Depends(current_user_id),
):
    """
    Загрузить N файлов для финальной проверки.

    ZIP-архивы распаковываются рекурсивно (до 2 уровней).
    Дубли по SHA256 (среди активных) пропускаются.

    Лимиты:
    - один файл: 200 МБ
    - сумма запроса: 400 МБ
    """
    _ensure_applicant(session, applicant_id)
    storage = get_storage()

    uploaded: List[FinalSubmissionDocumentRead] = []
    skipped_duplicates: List[str] = []
    errors: List[dict] = []

    total_size = 0

    # Сначала собираем все файлы (распаковываем ZIP), считая суммарный размер
    flat_files: List[tuple] = []  # (filename, content)

    for uf in files:
        try:
            content = await uf.read()
        except Exception as e:
            errors.append({"filename": uf.filename, "error": f"Read failed: {e}"})
            continue

        total_size += len(content)
        if total_size > MAX_TOTAL_UPLOAD_FS:
            errors.append({
                "filename": uf.filename,
                "error": f"Total upload size exceeds {MAX_TOTAL_UPLOAD_FS} bytes",
            })
            break

        # Проверка расширения — отсеиваем мусор сразу
        try:
            ext = validate_extension(uf.filename or "")
        except ValueError as e:
            errors.append({"filename": uf.filename, "error": str(e)})
            continue

        if ext == ".zip":
            # Распаковка
            try:
                inner_files = extract_zip_recursive(content)
                flat_files.extend(inner_files)
            except ValueError as e:
                errors.append({"filename": uf.filename, "error": str(e)})
        else:
            flat_files.append((uf.filename, content))

    # Теперь сохраняем каждый файл
    for filename, content in flat_files:
        doc, err = save_one_file(
            session=session,
            storage=storage,
            applicant_id=applicant_id,
            application_id=application_id,
            filename=filename,
            content=content,
            uploaded_by=str(user_id) if user_id is not None else None,
        )
        if err == "duplicate":
            skipped_duplicates.append(filename)
        elif err:
            errors.append({"filename": filename, "error": err})
        elif doc:
            uploaded.append(_attach_download_url(doc, storage))

    session.commit()

    # Pack 39.0-C: запускаем extraction pipeline в фоне для каждого загруженного документа
    from app.services.final_submission.extraction_pipeline import run_extraction_pipeline
    for doc_dto in uploaded:
        background_tasks.add_task(run_extraction_pipeline, doc_dto.id)

    return FinalSubmissionUploadResponse(
        uploaded=uploaded,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
    )


# ====================================================================
# GET /applicants/{id}/final-submission/documents
# ====================================================================

@router.get(
    "/applicants/{applicant_id}/final-submission/documents",
    response_model=List[FinalSubmissionDocumentRead],
)
def list_final_submission_documents(
    applicant_id: int,
    include_history: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    """
    Список документов клиента.

    По умолчанию — только активные (is_active=True).
    ?include_history=true — все, включая заменённые/удалённые.
    """
    _ensure_applicant(session, applicant_id)

    stmt = (
        select(FinalSubmissionDocument)
        .where(FinalSubmissionDocument.applicant_id == applicant_id)
    )
    if not include_history:
        stmt = stmt.where(FinalSubmissionDocument.is_active == True)  # noqa: E712
    stmt = stmt.order_by(FinalSubmissionDocument.uploaded_at.desc())

    docs = session.exec(stmt).all()
    storage = get_storage()

    return [_attach_download_url(d, storage) for d in docs]


# ====================================================================
# POST /applicants/{id}/final-submission/documents/{doc_id}/replace
# ====================================================================

@router.post(
    "/applicants/{applicant_id}/final-submission/documents/{doc_id}/replace",
    response_model=FinalSubmissionDocumentRead,
)
async def replace_final_submission_document(
    applicant_id: int,
    doc_id: int,
    background_tasks: BackgroundTasks,  # Pack 39.0-C
    file: UploadFile = File(...),
    keep_category: bool = Form(default=True),
    session: Session = Depends(get_session),
    user_id: Optional[str] = Depends(current_user_id),
):
    """
    Заменить документ новым файлом.

    Старая запись: is_active=False, replaced_at=NOW.
    Новая запись: previous_version_id=<id старой>, is_active=True.

    keep_category=true (default): doc_category копируется со старой.
    keep_category=false: новая запись с doc_category=NULL, потребует
    AI-классификации или ручной коррекции.
    """
    _ensure_applicant(session, applicant_id)
    old_doc = _get_doc_or_404(session, applicant_id, doc_id)

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Read failed: {e}")

    storage = get_storage()
    new_doc, err = replace_document(
        session=session,
        storage=storage,
        old_doc=old_doc,
        new_filename=file.filename or "unnamed",
        new_content=content,
        keep_category=keep_category,
        uploaded_by=str(user_id) if user_id is not None else None,
    )

    if err == "no_change":
        raise HTTPException(
            status_code=409,
            detail="New file is identical to old (SHA256 match), no replacement performed",
        )
    if err:
        raise HTTPException(status_code=400, detail=err)

    session.commit()
    session.refresh(new_doc)

    # Pack 39.0-C: extraction pipeline для нового файла
    from app.services.final_submission.extraction_pipeline import run_extraction_pipeline
    background_tasks.add_task(run_extraction_pipeline, new_doc.id)

    return _attach_download_url(new_doc, storage)


# ====================================================================
# DELETE /applicants/{id}/final-submission/documents/{doc_id}
# ====================================================================

@router.delete(
    "/applicants/{applicant_id}/final-submission/documents/{doc_id}",
)
def delete_final_submission_document(
    applicant_id: int,
    doc_id: int,
    hard: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    """
    Удалить документ.

    hard=false (default) — soft delete: is_active=False, replaced_at=NULL.
                            Файл в R2 НЕ удаляется, запись остаётся для истории.
    hard=true — permanent delete: запись удаляется из БД, файл из R2.
                Внимание: если есть последующая версия которая указывает
                на этот документ через previous_version_id, ссылка будет
                занулена (ON DELETE SET NULL).
    """
    _ensure_applicant(session, applicant_id)
    doc = _get_doc_or_404(session, applicant_id, doc_id)

    storage = get_storage()

    if hard:
        # Permanent delete
        if doc.storage_key:
            try:
                storage.delete(doc.storage_key)
            except Exception as e:
                log.warning(f"R2 delete failed for {doc.storage_key}: {e}")
        if doc.original_storage_key:
            try:
                storage.delete(doc.original_storage_key)
            except Exception as e:
                log.warning(f"R2 delete failed for {doc.original_storage_key}: {e}")
        session.delete(doc)
        session.commit()
        return {"deleted": True, "hard": True, "doc_id": doc_id}

    # Soft delete
    from datetime import datetime as _dt
    doc.is_active = False
    doc.replaced_at = None  # NULL означает «удалён», в отличие от «заменён»
    # Но для отслеживания момента нам всё равно нужна метка — используем uploaded_at для аудита.
    # NB: replaced_at=NULL семантически отличает delete от replace.
    session.add(doc)
    session.commit()
    return {"deleted": True, "hard": False, "doc_id": doc_id}


# ====================================================================
# PATCH /applicants/{id}/final-submission/documents/{doc_id}/category
# ====================================================================

@router.patch(
    "/applicants/{applicant_id}/final-submission/documents/{doc_id}/category",
    response_model=FinalSubmissionDocumentRead,
)
def update_final_submission_document_category(
    applicant_id: int,
    doc_id: int,
    payload: FinalSubmissionDocCategoryUpdateRequest,
    session: Session = Depends(get_session),
):
    """
    Менеджер вручную проставил/исправил категорию документа.
    doc_category_source автоматически становится 'manual'.
    """
    _ensure_applicant(session, applicant_id)
    doc = _get_doc_or_404(session, applicant_id, doc_id)

    doc.doc_category = payload.doc_category
    doc.doc_category_source = "manual"
    doc.doc_category_confidence = None  # ручная — без confidence

    session.add(doc)
    session.commit()
    session.refresh(doc)

    storage = get_storage()
    return _attach_download_url(doc, storage)


# ====================================================================
# Pack 39.0-D — Audit endpoints
# ====================================================================

@router.post(
    "/applicants/{applicant_id}/final-submission/audit/run",
    response_model=FinalSubmissionRunResponse,
)
def run_final_submission_audit(
    applicant_id: int,
    payload: FinalSubmissionRunRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user_id: Optional[str] = Depends(current_user_id),
):
    """
    Запустить финальный аудит пакета документов.

    Создаёт FinalSubmissionAuditReport со is_running=True, запускает
    BackgroundTask. Фронт polling'ом проверяет is_running каждые 2с.
    """
    from app.models import (
        FinalSubmissionAuditReport, FinalSubmissionVerdict,
    )
    from app.services.final_submission.audit_runner import (
        run_final_submission_audit_in_background,
    )

    _ensure_applicant(session, applicant_id)

    # Проверим что есть активные документы для аудита
    docs_count = session.exec(
        select(FinalSubmissionDocument)
        .where(FinalSubmissionDocument.applicant_id == applicant_id)
        .where(FinalSubmissionDocument.is_active == True)  # noqa: E712
    ).all()
    if not docs_count:
        raise HTTPException(
            status_code=400,
            detail="No active documents to audit. Upload documents first.",
        )

    report = FinalSubmissionAuditReport(
        application_id=payload.application_id,
        applicant_id=applicant_id,
        verdict=FinalSubmissionVerdict.WARN,
        is_running=True,
        triggered_by=payload.triggered_by or (str(user_id) if user_id is not None else None),
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    background_tasks.add_task(run_final_submission_audit_in_background, report.id)

    return FinalSubmissionRunResponse(report_id=report.id, status="started")


@router.get(
    "/applicants/{applicant_id}/final-submission/audit/reports",
    response_model=List[FinalSubmissionAuditReportRead],
)
def list_final_submission_audit_reports(
    applicant_id: int,
    session: Session = Depends(get_session),
):
    """Список всех прогонов аудита для клиента. Свежие сверху."""
    from app.models import FinalSubmissionAuditReport

    _ensure_applicant(session, applicant_id)

    stmt = (
        select(FinalSubmissionAuditReport)
        .where(FinalSubmissionAuditReport.applicant_id == applicant_id)
        .order_by(FinalSubmissionAuditReport.started_at.desc())
    )
    reports = session.exec(stmt).all()
    return [FinalSubmissionAuditReportRead.model_validate(r, from_attributes=True) for r in reports]


@router.get(
    "/final-submission/audit/reports/{report_id}",
    response_model=FinalSubmissionAuditReportWithFindings,
)
def get_final_submission_audit_report(
    report_id: int,
    session: Session = Depends(get_session),
):
    """Полный отчёт: report + findings + список документов которые в нём участвовали."""
    from app.models import (
        FinalSubmissionAuditReport, FinalSubmissionFinding,
    )

    report = session.get(FinalSubmissionAuditReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    # Findings
    findings_stmt = (
        select(FinalSubmissionFinding)
        .where(FinalSubmissionFinding.report_id == report_id)
        .order_by(FinalSubmissionFinding.sort_order, FinalSubmissionFinding.id)
    )
    findings = session.exec(findings_stmt).all()
    findings_dto = [FinalSubmissionFindingRead.model_validate(f, from_attributes=True) for f in findings]

    # Документы (по снэпшоту included_document_ids — если задан)
    documents_dto: List[FinalSubmissionDocumentRead] = []
    if report.included_document_ids:
        storage = get_storage()
        docs_stmt = (
            select(FinalSubmissionDocument)
            .where(FinalSubmissionDocument.id.in_(report.included_document_ids))
        )
        docs = session.exec(docs_stmt).all()
        documents_dto = [_attach_download_url(d, storage) for d in docs]

    base = FinalSubmissionAuditReportRead.model_validate(report, from_attributes=True)
    return FinalSubmissionAuditReportWithFindings(
        **base.model_dump(),
        findings=findings_dto,
        documents=documents_dto,
    )


@router.post(
    "/final-submission/findings/{finding_id}/acknowledge",
    response_model=FinalSubmissionFindingRead,
)
def acknowledge_final_submission_finding(
    finding_id: int,
    payload: FinalSubmissionAcknowledgeRequest,
    session: Session = Depends(get_session),
    user_id: Optional[str] = Depends(current_user_id),
):
    """Менеджер: «учёл, иду переделывать документ». Помечает finding как acknowledged."""
    from app.models import FinalSubmissionFinding, FinalSubmissionFindingStatus

    finding = session.get(FinalSubmissionFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")

    finding.status = FinalSubmissionFindingStatus.ACKNOWLEDGED
    finding.resolved_at = datetime.utcnow()
    finding.resolved_by = str(user_id) if user_id is not None else None
    finding.resolution_note = payload.note
    session.add(finding)
    session.commit()
    session.refresh(finding)

    return FinalSubmissionFindingRead.model_validate(finding, from_attributes=True)


@router.post(
    "/final-submission/findings/{finding_id}/dismiss",
    response_model=FinalSubmissionFindingRead,
)
def dismiss_final_submission_finding(
    finding_id: int,
    payload: FinalSubmissionDismissRequest,
    session: Session = Depends(get_session),
    user_id: Optional[str] = Depends(current_user_id),
):
    """Менеджер: «false positive» или «не критично». Помечает dismissed."""
    from app.models import FinalSubmissionFinding, FinalSubmissionFindingStatus

    finding = session.get(FinalSubmissionFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")

    finding.status = FinalSubmissionFindingStatus.DISMISSED
    finding.resolved_at = datetime.utcnow()
    finding.resolved_by = str(user_id) if user_id is not None else None
    finding.resolution_note = payload.note
    session.add(finding)
    session.commit()
    session.refresh(finding)

    return FinalSubmissionFindingRead.model_validate(finding, from_attributes=True)


