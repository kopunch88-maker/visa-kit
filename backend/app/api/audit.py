# -*- coding: utf-8 -*-
"""
Pack 37.0-C — AI Document Audit API endpoints (full implementation).

Endpoints:
- POST /api/applications/{app_id}/audit/run                — запуск аудита через BackgroundTask
- GET  /api/applications/{app_id}/audit/reports            — список прогонов
- GET  /api/audit/reports/{report_id}                      — отчёт + findings
- POST /api/audit/findings/{finding_id}/accept             — применить fix через whitelist
- POST /api/audit/findings/{finding_id}/dismiss            — отклонить finding
- POST /api/audit/findings/{finding_id}/manual-fix         — ручное значение от менеджера

Pack 37.0-C — фикс НЕ перегенерирует пакет 16 файлов автоматически.
Менеджер пересобирает через отдельный endpoint render-package когда готов.
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select

from app.db import get_session
from app.models import (
    Application,
    AuditReport,
    AuditFinding,
    AuditVerdict,
    AuditCategory,
    AuditSeverity,
    AuditFindingStatus,
    AuditReportRead,
    AuditReportWithFindings,
    AuditFindingRead,
    AuditRunRequest,
    AuditRunResponse,
    AuditDismissRequest,
    AuditManualFixRequest,
    AuditAcceptResponse,
)
from app.services.audit.fix_handlers import (
    FIX_HANDLERS,
    apply_fix,
    APPLICANT_WRITABLE_FIELDS,
    COMPANY_WRITABLE_FIELDS,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["audit"])


# ====================================================================
# Helpers
# ====================================================================

def _finding_to_read(f: AuditFinding) -> AuditFindingRead:
    """SQLModel -> DTO с вычислением can_auto_apply."""
    return AuditFindingRead(
        id=f.id,
        report_id=f.report_id,
        category=f.category,
        severity=f.severity,
        title=f.title,
        description=f.description,
        evidence=f.evidence,
        field_path=f.field_path,
        current_value=f.current_value,
        suggested_value=f.suggested_value,
        fix_action=f.fix_action,
        fix_payload=f.fix_payload or {},
        can_auto_apply=(
            f.fix_action is not None
            and f.fix_action in FIX_HANDLERS
            and f.status == AuditFindingStatus.OPEN
        ),
        status=f.status,
        resolved_at=f.resolved_at,
        resolved_by=f.resolved_by,
        resolution_note=f.resolution_note,
        sort_order=f.sort_order,
    )


def _report_to_read(r: AuditReport) -> AuditReportRead:
    return AuditReportRead(
        id=r.id,
        application_id=r.application_id,
        verdict=r.verdict,
        model_used=r.model_used,
        input_tokens=r.input_tokens,
        output_tokens=r.output_tokens,
        cost_usd=r.cost_usd,
        started_at=r.started_at,
        finished_at=r.finished_at,
        duration_ms=r.duration_ms,
        is_running=r.is_running,
        error=r.error,
        triggered_by=r.triggered_by,
        summary_counts=r.summary_counts or {},
    )


# ====================================================================
# GET endpoints
# ====================================================================

@router.get(
    "/applications/{app_id}/audit/reports",
    response_model=List[AuditReportRead],
)
def list_reports(
    app_id: int,
    session: Session = Depends(get_session),
):
    """История прогонов аудита для заявки."""
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    reports = session.exec(
        select(AuditReport)
        .where(AuditReport.application_id == app_id)
        .order_by(AuditReport.started_at.desc())
    ).all()

    return [_report_to_read(r) for r in reports]


@router.get(
    "/audit/reports/{report_id}",
    response_model=AuditReportWithFindings,
)
def get_report(
    report_id: int,
    session: Session = Depends(get_session),
):
    """Один отчёт со всеми findings."""
    report = session.get(AuditReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    findings = session.exec(
        select(AuditFinding)
        .where(AuditFinding.report_id == report_id)
    ).all()

    severity_priority = {
        AuditSeverity.CRITICAL: 0,
        AuditSeverity.WARNING: 1,
        AuditSeverity.INFO: 2,
    }
    findings_sorted = sorted(
        findings,
        key=lambda f: (
            severity_priority.get(f.severity, 99),
            f.sort_order,
            f.id,
        ),
    )

    base = _report_to_read(report)
    return AuditReportWithFindings(
        **base.model_dump(),
        findings=[_finding_to_read(f) for f in findings_sorted],
    )


# ====================================================================
# POST endpoints
# ====================================================================

@router.post(
    "/applications/{app_id}/audit/run",
    response_model=AuditRunResponse,
)
def run_audit(
    app_id: int,
    body: AuditRunRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Запуск аудита. Создаёт AuditReport со is_running=True, запускает
    BackgroundTask с реальным LLM-вызовом. Фронт polling'ом проверяет
    is_running каждые 2с.

    Длительность: 30-90 секунд (рендер пакета + LLM call).
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Проверка: нет ли уже активного прогона
    running = session.exec(
        select(AuditReport)
        .where(AuditReport.application_id == app_id)
        .where(AuditReport.is_running == True)  # noqa: E712
    ).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Audit is already running (report {running.id}, "
                f"started at {running.started_at.isoformat()})"
            ),
        )

    # Создаём отчёт-заготовку
    report = AuditReport(
        application_id=app_id,
        verdict=AuditVerdict.WARN,  # placeholder, обновится в фоне
        is_running=True,
        triggered_by=body.triggered_by or "admin",
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    # Запускаем BackgroundTask
    from app.services.audit.auditor import run_audit_in_background
    background_tasks.add_task(run_audit_in_background, report.id)

    log.info(f"[audit:api] Started audit report {report.id} for app {app_id}")

    return AuditRunResponse(report_id=report.id, status="started")


@router.post(
    "/audit/findings/{finding_id}/accept",
    response_model=AuditAcceptResponse,
)
def accept_finding(
    finding_id: int,
    session: Session = Depends(get_session),
):
    """
    Применить fix через whitelist handler.

    Pack 37.0-C: фикс ТОЛЬКО обновляет БД. Пакет 16 файлов НЕ перегенерируется.
    Менеджер пересобирает пакет через отдельный endpoint когда готов.
    """
    finding = session.get(AuditFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.status != AuditFindingStatus.OPEN:
        raise HTTPException(
            status_code=409,
            detail=f"Finding is not open (current: {finding.status.value})",
        )

    if not finding.fix_action:
        raise HTTPException(
            status_code=400,
            detail="Finding has no fix_action — use manual-fix or dismiss",
        )

    if finding.fix_action not in FIX_HANDLERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"fix_action '{finding.fix_action}' is not whitelisted. "
                f"Supported: {sorted(FIX_HANDLERS.keys())}"
            ),
        )

    # Применяем
    result = apply_fix(finding, session)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Apply failed")

    # Обновляем статус finding
    finding.status = AuditFindingStatus.ACCEPTED
    finding.resolved_at = datetime.utcnow()
    finding.resolved_by = "manager"
    finding.resolution_note = f"Applied via {finding.fix_action}: {result.message}"
    session.add(finding)
    session.commit()

    # Пересчёт summary в отчёте
    _recompute_summary(session, finding.report_id)

    log.info(f"[audit:api] Accepted finding {finding_id}, diff={result.diff}")

    return AuditAcceptResponse(
        success=True,
        applied_changes=result.diff,
        message=result.message,
    )


@router.post(
    "/audit/findings/{finding_id}/dismiss",
    response_model=AuditFindingRead,
)
def dismiss_finding(
    finding_id: int,
    body: AuditDismissRequest,
    session: Session = Depends(get_session),
):
    """Отклонить finding без применения фикса."""
    finding = session.get(AuditFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.status != AuditFindingStatus.OPEN:
        raise HTTPException(
            status_code=409,
            detail=f"Finding is not open (current: {finding.status.value})",
        )

    finding.status = AuditFindingStatus.DISMISSED
    finding.resolved_at = datetime.utcnow()
    finding.resolution_note = body.note
    finding.resolved_by = "manager"

    session.add(finding)
    session.commit()
    session.refresh(finding)

    _recompute_summary(session, finding.report_id)

    log.info(f"[audit:api] Dismissed finding {finding_id}, note={body.note!r}")
    return _finding_to_read(finding)


@router.post(
    "/audit/findings/{finding_id}/manual-fix",
    response_model=AuditFindingRead,
)
def manual_fix_finding(
    finding_id: int,
    body: AuditManualFixRequest,
    session: Session = Depends(get_session),
):
    """
    Менеджер сам ввёл правильное значение. Идёт через тот же whitelist что и accept:
    field_path должен соответствовать APPLICANT/COMPANY whitelist полей.

    Pack 37.0-C: фикс ТОЛЬКО обновляет БД, пакет НЕ пересобирается автоматически.
    """
    finding = session.get(AuditFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.status != AuditFindingStatus.OPEN:
        raise HTTPException(
            status_code=409,
            detail=f"Finding is not open (current: {finding.status.value})",
        )

    # Определяем target по field_path
    # Формат: "applicant.last_name_native" или "company.tax_id_primary"
    field_path = (body.field_path or "").strip()
    if "." not in field_path:
        raise HTTPException(
            status_code=400,
            detail=f"field_path must be 'applicant.<field>' or 'company.<field>', got: {field_path!r}",
        )

    target, fname = field_path.split(".", 1)

    # Готовим payload для соответствующего handler
    if target == "applicant":
        if fname not in APPLICANT_WRITABLE_FIELDS:
            raise HTTPException(
                status_code=400,
                detail=f"Field 'applicant.{fname}' is not in whitelist",
            )
        # Маскируем finding под update_applicant_field action
        finding.fix_action = "update_applicant_field"
        finding.fix_payload = {"field": fname, "value": body.new_value}
    elif target == "company":
        if fname not in COMPANY_WRITABLE_FIELDS:
            raise HTTPException(
                status_code=400,
                detail=f"Field 'company.{fname}' is not in whitelist",
            )
        finding.fix_action = "update_company_field"
        finding.fix_payload = {"field": fname, "value": body.new_value}
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Target must be 'applicant' or 'company', got: {target!r}",
        )

    # Применяем
    result = apply_fix(finding, session)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Apply failed")

    finding.status = AuditFindingStatus.MANUALLY_FIXED
    finding.resolved_at = datetime.utcnow()
    finding.resolved_by = "manager"
    finding.resolution_note = (
        f"Manual fix: {field_path}='{body.new_value}'"
        + (f"\nNote: {body.note}" if body.note else "")
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    _recompute_summary(session, finding.report_id)

    log.info(
        f"[audit:api] Manual fix for finding {finding_id}: "
        f"{field_path}={body.new_value!r}, diff={result.diff}"
    )

    return _finding_to_read(finding)


# ====================================================================
# Pack 37.1 — DOCX export
# ====================================================================

from fastapi.responses import StreamingResponse
from urllib.parse import quote


@router.get("/audit/reports/{report_id}/export.docx")
def export_report_docx(
    report_id: int,
    session: Session = Depends(get_session),
):
    """
    Скачать отчёт аудита в формате DOCX.

    Содержит все findings (включая принятые/отклонённые) с цветной разметкой,
    статусами решений менеджера, обоснованиями ИИ и таблицами diff.
    """
    from app.services.audit.audit_export import build_audit_report_docx

    report = session.get(AuditReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if report.is_running:
        raise HTTPException(
            status_code=409,
            detail="Audit is still running — wait for completion before exporting",
        )

    try:
        docx_bytes, filename = build_audit_report_docx(report_id, session)
    except Exception as e:
        log.exception(f"[audit:api] DOCX export failed for report {report_id}")
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    # filename* per RFC 5987 — для не-ASCII (кириллица в ФИО)
    quoted_filename = quote(filename)
    return StreamingResponse(
        iter([docx_bytes]),
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8\'\'{quoted_filename}",
            "Content-Length": str(len(docx_bytes)),
        },
    )


# ====================================================================
# Internal: пересчёт summary
# ====================================================================

def _recompute_summary(session: Session, report_id: int) -> None:
    """После каждого accept/dismiss/manual-fix — пересчитываем агрегаты."""
    report = session.get(AuditReport, report_id)
    if not report:
        return

    findings = session.exec(
        select(AuditFinding).where(AuditFinding.report_id == report_id)
    ).all()

    counts = {
        "critical": 0,
        "warning": 0,
        "info": 0,
        "total": len(findings),
        "open": 0,
        "accepted": 0,
        "dismissed": 0,
        "manually_fixed": 0,
    }
    for f in findings:
        if f.severity == AuditSeverity.CRITICAL:
            counts["critical"] += 1
        elif f.severity == AuditSeverity.WARNING:
            counts["warning"] += 1
        else:
            counts["info"] += 1

        if f.status == AuditFindingStatus.OPEN:
            counts["open"] += 1
        elif f.status == AuditFindingStatus.ACCEPTED:
            counts["accepted"] += 1
        elif f.status == AuditFindingStatus.DISMISSED:
            counts["dismissed"] += 1
        elif f.status == AuditFindingStatus.MANUALLY_FIXED:
            counts["manually_fixed"] += 1

    # Сохраняем _llm_summary если был
    if report.summary_counts and "_llm_summary" in report.summary_counts:
        counts["_llm_summary"] = report.summary_counts["_llm_summary"]

    report.summary_counts = counts
    session.add(report)
    session.commit()
