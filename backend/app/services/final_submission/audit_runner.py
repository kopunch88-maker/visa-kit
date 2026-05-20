# -*- coding: utf-8 -*-
"""
Pack 39.0-D — LLM auditor для финальной проверки.

Главная функция run_final_submission_audit_in_background(report_id) запускает в фоне:
1. Загружает FinalSubmissionAuditReport (создан в endpoint /audit/run)
2. Собирает context через build_final_audit_context()
3. Зовёт LLM (Sonnet-4.5) с промптом визового инспектора
4. Парсит JSON-ответ, валидирует findings (8 категорий A-H)
5. Сохраняет FinalSubmissionFinding в БД
6. Обновляет AuditReport: verdict, summary_counts, is_running=False, tokens, cost

Запускается через FastAPI BackgroundTasks. Менеджер polling'ом проверяет
is_running каждые 2с.

Скопировано из Pack 37.0 auditor.py с адаптацией категорий и без fix_action.
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlmodel import Session

log = logging.getLogger(__name__)


# ====================================================================
# Конфиг
# ====================================================================

MODEL_PRICING = {
    "anthropic/claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "anthropic/claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "anthropic/claude-opus-4": {"input": 15.00, "output": 75.00},
    "anthropic/claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
}

# Max output: 100 findings × ~300 токенов = ~30k токенов.
DEFAULT_MAX_TOKENS = 32768

VALID_CATEGORIES = {
    "A_identity", "B_numeric", "C_dates", "D_company",
    "E_translation", "F_completeness", "G_quality", "H_stale",
}
VALID_SEVERITIES = {"critical", "warning", "info"}
VALID_VERDICTS = {"PASS", "WARN", "FAIL"}


# ====================================================================
# JSON parsing с repair
# ====================================================================

def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].rstrip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _repair_truncated_json(text: str) -> Optional[str]:
    """
    Скопировано из Pack 37.0 auditor.py.
    Если LLM упёрся в max_tokens и оборвал findings[N] — обрезаем до последнего
    полного finding и закрываем структуру.
    """
    findings_start = text.find('"findings"')
    if findings_start < 0:
        return None
    array_start = text.find("[", findings_start)
    if array_start < 0:
        return None

    depth_curly = 0
    depth_array = 1
    in_string = False
    escape_next = False
    last_complete_object_end = -1

    i = array_start + 1
    while i < len(text):
        ch = text[i]
        if escape_next:
            escape_next = False
            i += 1
            continue
        if in_string:
            if ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth_curly += 1
        elif ch == "}":
            depth_curly -= 1
            if depth_curly == 0 and depth_array == 1:
                last_complete_object_end = i + 1
        elif ch == "[":
            depth_array += 1
        elif ch == "]":
            depth_array -= 1
            if depth_array == 0:
                return None
        i += 1

    if last_complete_object_end < 0:
        return None

    return text[:last_complete_object_end] + "\n  ]\n}"


def _parse_llm_response(text: str) -> Dict[str, Any]:
    cleaned = _strip_markdown_fence(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                repaired = _repair_truncated_json(cleaned)
                if repaired:
                    try:
                        parsed = json.loads(repaired)
                        log.warning(f"[final_audit] JSON truncated, repaired: {len(cleaned)}->{len(repaired)}")
                    except json.JSONDecodeError as e2:
                        raise ValueError(f"LLM JSON truncated and unrecoverable: {e2}")
                else:
                    raise ValueError(f"LLM returned invalid JSON: {e}. Head: {cleaned[:300]!r}")
        else:
            repaired = _repair_truncated_json(cleaned)
            if repaired:
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    raise ValueError(f"LLM returned non-JSON: {e}")
            else:
                raise ValueError(f"LLM returned non-JSON: {e}")

    if not isinstance(parsed, dict):
        raise ValueError(f"LLM returned non-object: {type(parsed).__name__}")

    verdict = parsed.get("verdict")
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"Invalid verdict: {verdict!r}")

    findings = parsed.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError(f"findings must be a list")

    return parsed


def _validate_finding(raw: Dict[str, Any], idx: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    category = raw.get("category")
    if category not in VALID_CATEGORIES:
        log.warning(f"[final_audit] Finding #{idx} invalid category: {category!r}")
        return None

    severity = raw.get("severity")
    if severity not in VALID_SEVERITIES:
        log.warning(f"[final_audit] Finding #{idx} invalid severity: {severity!r}")
        return None

    title = raw.get("title")
    if not title or not isinstance(title, str):
        return None

    return {
        "category": category,
        "severity": severity,
        "title": str(title)[:500],
        "description": (raw.get("description") or "")[:5000] or None,
        "recommendation": (raw.get("recommendation") or "")[:5000] or None,
        "affected_documents": raw.get("affected_documents") or [],
        "field_name": (raw.get("field_name") or "")[:128] or None,
        "values_found": raw.get("values_found") or {},
        "sort_order": int(raw.get("sort_order") or idx),
    }


# ====================================================================
# Cost
# ====================================================================

def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> Optional[Decimal]:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        for key, val in MODEL_PRICING.items():
            if model.startswith(key) or key.startswith(model.split(":")[0]):
                pricing = val
                break
    if not pricing:
        return None
    inp = Decimal(input_tokens) * Decimal(pricing["input"]) / Decimal(1_000_000)
    out = Decimal(output_tokens) * Decimal(pricing["output"]) / Decimal(1_000_000)
    return (inp + out).quantize(Decimal("0.0001"))


# ====================================================================
# Main entry point
# ====================================================================

def run_final_submission_audit_in_background(report_id: int) -> None:
    """Sync wrapper для BackgroundTasks."""
    log.info(f"[final_audit] Starting audit for report {report_id}")
    try:
        asyncio.run(_run_audit_async(report_id))
    except Exception as e:
        log.exception(f"[final_audit] Audit {report_id} crashed at top level: {e}")
        _mark_report_failed(report_id, f"Top-level crash: {e}")


def _mark_report_failed(report_id: int, error_text: str) -> None:
    from app.db.session import engine
    from app.models import FinalSubmissionAuditReport, FinalSubmissionVerdict
    try:
        with Session(engine) as session:
            report = session.get(FinalSubmissionAuditReport, report_id)
            if not report:
                return
            report.is_running = False
            report.verdict = FinalSubmissionVerdict.WARN
            report.error = error_text[:5000]
            report.finished_at = datetime.utcnow()
            if report.started_at:
                report.duration_ms = int((report.finished_at - report.started_at).total_seconds() * 1000)
            session.add(report)
            session.commit()
    except Exception as e:
        log.exception(f"[final_audit] Cannot even mark failed: {e}")


async def _run_audit_async(report_id: int) -> None:
    from app.db.session import engine
    from app.models import (
        FinalSubmissionAuditReport, FinalSubmissionFinding,
        FinalSubmissionVerdict, FinalSubmissionCategory,
        FinalSubmissionSeverity, FinalSubmissionFindingStatus,
        Applicant, Application,
    )
    from app.services.final_submission.audit_context_builder import build_final_audit_context
    from app.services.final_submission.audit_prompts import get_system_prompt, get_user_prompt
    from app.services.llm.factory import get_llm_client

    started = datetime.utcnow()

    with Session(engine) as session:
        report = session.get(FinalSubmissionAuditReport, report_id)
        if not report:
            log.error(f"[final_audit] Report {report_id} not found")
            return

        try:
            # === 1. Build context ===
            log.info(f"[final_audit] Building context: applicant={report.applicant_id}, application={report.application_id}")
            ctx = build_final_audit_context(
                applicant_id=report.applicant_id,
                application_id=report.application_id,
                session=session,
            )

            if not ctx.documents:
                _mark_report_failed(report_id, "No active documents to audit")
                return

            context_json = ctx.to_json()
            log.info(f"[final_audit] Context: {len(ctx.documents)} docs, {len(context_json)} chars")

            # Снэпшот included document_ids и categories
            report.included_document_ids = [d["id"] for d in ctx.documents]
            categories_snapshot = {}
            for d in ctx.documents:
                cat = d.get("doc_category") or "unknown"
                categories_snapshot[cat] = categories_snapshot.get(cat, 0) + 1
            report.document_categories_snapshot = categories_snapshot
            session.add(report)
            session.commit()

            # === 2. LLM call ===
            llm = get_llm_client()
            system = get_system_prompt()
            user = get_user_prompt(context_json)

            model_name = "anthropic/claude-sonnet-4-5"
            report.model_used = model_name
            report.prompt_version = "39.0-D-v1"
            session.add(report)
            session.commit()

            log.info(f"[final_audit] Calling LLM {model_name}, input ~{len(system)+len(user)} chars")
            llm_response = await llm.complete(
                system=system,
                user=user,
                model=model_name,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=0.0,
            )
            log.info(f"[final_audit] LLM responded: {len(llm_response)} chars")

            # === 3. Parse ===
            try:
                parsed = _parse_llm_response(llm_response)
            except ValueError as e:
                _mark_report_failed(report_id, f"Failed to parse LLM: {e}")
                return

            verdict_str = parsed["verdict"]
            findings_raw = parsed.get("findings", [])
            inspector_summary = parsed.get("inspector_summary", "")

            # === 4. Save findings ===
            saved = []
            for idx, raw in enumerate(findings_raw):
                normalized = _validate_finding(raw, idx)
                if not normalized:
                    continue
                f = FinalSubmissionFinding(
                    report_id=report.id,
                    category=FinalSubmissionCategory(normalized["category"]),
                    severity=FinalSubmissionSeverity(normalized["severity"]),
                    title=normalized["title"],
                    description=normalized["description"],
                    recommendation=normalized["recommendation"],
                    affected_documents=normalized["affected_documents"],
                    field_name=normalized["field_name"],
                    values_found=normalized["values_found"],
                    status=FinalSubmissionFindingStatus.OPEN,
                    sort_order=normalized["sort_order"],
                )
                session.add(f)
                saved.append(f)
            session.commit()
            log.info(f"[final_audit] Saved {len(saved)} findings")

            # === 5. Summary ===
            counts = {
                "critical": sum(1 for f in saved if f.severity == FinalSubmissionSeverity.CRITICAL),
                "warning": sum(1 for f in saved if f.severity == FinalSubmissionSeverity.WARNING),
                "info": sum(1 for f in saved if f.severity == FinalSubmissionSeverity.INFO),
                "total": len(saved),
                "open": len(saved),
            }

            # === 6. Finalize report ===
            report.verdict = FinalSubmissionVerdict(verdict_str)
            report.summary_counts = counts
            report.inspector_summary = inspector_summary[:1000] if inspector_summary else None
            report.is_running = False
            report.finished_at = datetime.utcnow()
            report.duration_ms = int((report.finished_at - started).total_seconds() * 1000)

            input_tok = (len(system) + len(user)) // 4
            output_tok = len(llm_response) // 4
            report.input_tokens = input_tok
            report.output_tokens = output_tok
            report.cost_usd = _calculate_cost(model_name, input_tok, output_tok)

            session.add(report)
            session.commit()

            log.info(
                f"[final_audit] Audit {report_id} complete: "
                f"verdict={verdict_str}, findings={len(saved)} "
                f"(crit={counts['critical']}, warn={counts['warning']}, info={counts['info']}), "
                f"duration={report.duration_ms}ms, cost=${report.cost_usd}"
            )

        except Exception as e:
            log.exception(f"[final_audit] Audit {report_id} failed: {e}")
            _mark_report_failed(report_id, f"{type(e).__name__}: {e}")
