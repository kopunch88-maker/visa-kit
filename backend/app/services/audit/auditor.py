# -*- coding: utf-8 -*-
"""
Pack 37.0-C — LLM auditor.

Главная функция run_audit(report_id) запускает в фоне:
1. Загружает AuditReport (создан в run_audit_endpoint со is_running=True)
2. Собирает context через build_audit_context()
3. Рендерит сгенерированные DOCX/PDF в памяти через build_full_package(),
   извлекает их тексты (это даёт LLM полное досье включая суммы, подписантов,
   чекбоксы MI-T и т.д.)
4. Зовёт LLM через get_llm_client().complete()
5. Парсит JSON-ответ, валидирует структуру
6. Сохраняет AuditFinding в БД
7. Обновляет AuditReport: verdict, summary_counts, is_running=False, токены, cost

Запускается через FastAPI BackgroundTasks — менеджер polling'ом проверяет
is_running каждые 2с.

При любой ошибке LLM/парсинга — AuditReport.error заполняется текстом,
verdict=WARN, is_running=False, findings нет. Менеджер видит на странице
«Ошибка: ...» и может перезапустить.
"""
import asyncio
import io
import json
import logging
import re
import zipfile
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session

log = logging.getLogger(__name__)


# ====================================================================
# Конфигурация моделей и цен
# ====================================================================

# Тарифы за 1M токенов для расчёта cost_usd
# Источник: https://openrouter.ai/anthropic/claude-sonnet-4-5
# Если LLM_MODEL изменится — можно добавить сюда.
MODEL_PRICING = {
    "anthropic/claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "anthropic/claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "anthropic/claude-opus-4": {"input": 15.00, "output": 75.00},
    "anthropic/claude-opus-4-1": {"input": 15.00, "output": 75.00},
    "anthropic/claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
}

# Max output: 50 findings × ~300 токенов на каждый = ~15k токенов.
# Pack 37.0-C.2: подняли с 8192 до 16384 — на старом лимите Sonnet 4.6
# не успевал закрыть JSON если находил больше 10 findings, и весь
# отчёт уходил в FAIL с error='Unterminated string'.
DEFAULT_MAX_TOKENS = 16384


# ====================================================================
# Парсинг JSON-ответа LLM
# ====================================================================

def _strip_markdown_fence(text: str) -> str:
    """Срезаем ```json ... ``` если LLM всё-таки обернул."""
    text = text.strip()
    if text.startswith("```"):
        # Срезаем первую строку ```json или ``` и закрывающий ```
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].rstrip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _repair_truncated_json(text: str) -> Optional[str]:
    """
    Pack 37.0-C.2 repair: если LLM упёрся в max_tokens и оборвал JSON
    на середине findings[N], пытаемся отрезать незакрытый элемент
    и заклеить структуру.

    Алгоритм:
    1. Находим последний полный finding object перед обрывом —
       символ '}' на минимально-вложенном уровне после '"findings": ['.
    2. Обрезаем всё что после него.
    3. Закрываем массив findings и сам root-объект.

    Возвращает recovered JSON-string или None если recovery невозможен.
    """
    # Ищем начало массива findings
    findings_start = text.find('"findings"')
    if findings_start < 0:
        return None
    array_start = text.find("[", findings_start)
    if array_start < 0:
        return None

    # Сканируем символы, отслеживая глубину { } и [ ], игнорируя строки.
    # Запоминаем позиции закрытия finding-объектов на глубине 1 от массива.
    depth_curly = 0
    depth_array = 1  # уже внутри [
    in_string = False
    escape_next = False
    last_complete_object_end = -1  # индекс ПОСЛЕ '}' закрытия finding'а

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
            # Если только что закрылся finding (depth_curly==0 внутри массива)
            if depth_curly == 0 and depth_array == 1:
                last_complete_object_end = i + 1
        elif ch == "[":
            depth_array += 1
        elif ch == "]":
            depth_array -= 1
            if depth_array == 0:
                # Массив закрыт корректно — нет нужды в repair
                return None
        i += 1

    if last_complete_object_end < 0:
        return None  # ни одного полного finding не нашли

    # Обрезаем до конца последнего finding'а, закрываем структуру
    repaired = text[:last_complete_object_end] + "\n  ]\n}"
    return repaired


def _parse_llm_response(text: str) -> Dict[str, Any]:
    """
    Парсит ответ LLM в structured dict.

    Pack 37.0-C.2: если первый парсинг падает, пробуем repair
    оборванного на max_tokens JSON (часть findings лучше чем ноль).
    """
    cleaned = _strip_markdown_fence(text)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Попытка 1: regex выкусить JSON если LLM добавил преамбулу
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                # удалось — идём дальше
            except json.JSONDecodeError:
                # Попытка 2 (Pack 37.0-C.2): repair оборванного JSON
                repaired = _repair_truncated_json(cleaned)
                if repaired:
                    try:
                        parsed = json.loads(repaired)
                        log.warning(
                            f"[auditor] JSON was truncated at {e}, recovered "
                            f"by trimming to last complete finding. "
                            f"Original size: {len(cleaned)} chars, recovered: {len(repaired)} chars."
                        )
                    except json.JSONDecodeError as e2:
                        raise ValueError(
                            f"LLM JSON truncated and unrecoverable: {e2}. "
                            f"Response head (300 chars): {cleaned[:300]!r}"
                        )
                else:
                    raise ValueError(
                        f"LLM returned invalid JSON (no recovery possible): {e}. "
                        f"Response head (300 chars): {cleaned[:300]!r}"
                    )
        else:
            # Нет ни одного '{' — точно не JSON
            repaired = _repair_truncated_json(cleaned)
            if repaired:
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    raise ValueError(
                        f"LLM returned non-JSON: {e}. "
                        f"Response head (300 chars): {cleaned[:300]!r}"
                    )
            else:
                raise ValueError(
                    f"LLM returned non-JSON: {e}. "
                    f"Response head (300 chars): {cleaned[:300]!r}"
                )

    if not isinstance(parsed, dict):
        raise ValueError(f"LLM returned non-object: {type(parsed).__name__}")

    # Валидация структуры
    verdict = parsed.get("verdict")
    if verdict not in ("PASS", "WARN", "FAIL"):
        raise ValueError(f"Invalid verdict: {verdict!r}, expected PASS|WARN|FAIL")

    findings = parsed.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError(f"findings must be a list, got {type(findings).__name__}")

    return parsed


def _validate_finding(raw: Dict[str, Any], idx: int) -> Optional[Dict[str, Any]]:
    """
    Валидирует один finding из ответа LLM. Возвращает нормализованный dict
    или None если finding некорректный (пропускаем).
    """
    if not isinstance(raw, dict):
        log.warning(f"[auditor] Finding #{idx} is not a dict: {type(raw).__name__}")
        return None

    category = raw.get("category")
    if category not in ("identity", "financial", "company", "education", "spain_pack", "formal"):
        log.warning(f"[auditor] Finding #{idx} has invalid category: {category!r}")
        return None

    severity = raw.get("severity")
    if severity not in ("critical", "warning", "info"):
        log.warning(f"[auditor] Finding #{idx} has invalid severity: {severity!r}")
        return None

    title = raw.get("title")
    if not title or not isinstance(title, str):
        log.warning(f"[auditor] Finding #{idx} has no title")
        return None

    # fix_action: либо в whitelist, либо None (тогда только manual fix доступен)
    from .fix_handlers import FIX_HANDLERS
    fix_action = raw.get("fix_action")
    if fix_action and fix_action not in FIX_HANDLERS:
        log.info(
            f"[auditor] Finding #{idx} has unknown fix_action '{fix_action}' — "
            f"will be saved without auto-apply"
        )
        # НЕ обнуляем — сохраняем как есть для прозрачности менеджеру

    return {
        "category": category,
        "severity": severity,
        "title": str(title)[:500],
        "description": (raw.get("description") or "")[:5000] or None,
        "evidence": (raw.get("evidence") or "")[:5000] or None,
        "field_path": (raw.get("field_path") or "")[:255] or None,
        "current_value": (
            str(raw.get("current_value"))[:1000] if raw.get("current_value") is not None else None
        ),
        "suggested_value": (
            str(raw.get("suggested_value"))[:1000] if raw.get("suggested_value") is not None else None
        ),
        "fix_action": fix_action,
        "fix_payload": raw.get("fix_payload") or {},
        "sort_order": int(raw.get("sort_order") or idx),
    }


# ====================================================================
# Извлечение текста из ZIP-пакета
# ====================================================================

def _extract_texts_from_zip(zip_bytes: bytes) -> Dict[str, str]:
    """
    build_full_package возвращает (zip_bytes, status_dict).
    Парсим ZIP в памяти, для каждого файла извлекаем текст (docx2txt / pypdf).
    """
    import docx2txt
    from pypdf import PdfReader

    result: Dict[str, str] = {}

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for name in zf.namelist():
                try:
                    file_bytes = zf.read(name)
                    lower = name.lower()

                    if lower.endswith(".docx"):
                        text = docx2txt.process(io.BytesIO(file_bytes)) or ""
                    elif lower.endswith(".pdf"):
                        reader = PdfReader(io.BytesIO(file_bytes))
                        parts = []
                        for page in reader.pages:
                            try:
                                parts.append(page.extract_text() or "")
                            except Exception:
                                continue
                        text = "\n\n".join(p for p in parts if p.strip())
                    else:
                        continue

                    # Чистка и обрезка
                    text = re.sub(r"[ \t\xa0]+", " ", text)
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                    if len(text) > 20000:
                        text = text[:20000] + "\n\n[... TRUNCATED ...]"

                    if text:
                        result[name] = text
                except Exception as e:
                    log.warning(f"[auditor:zip] Failed to extract {name}: {e}")
    except zipfile.BadZipFile as e:
        log.error(f"[auditor:zip] Bad ZIP file: {e}")
        return {}

    return result


# ====================================================================
# Рендер пакета для аудита
# ====================================================================

def _render_full_package_for_audit(application, session: Session) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Запускает build_full_package(), парсит ZIP, извлекает тексты.

    Возвращает (texts_dict, status_dict). При ошибке — пустые dict.
    """
    try:
        from app.services.rendering import build_full_package
    except ImportError as e:
        log.error(f"[auditor] build_full_package not available: {e}")
        return {}, {}

    try:
        zip_bytes, status = build_full_package(
            application,
            session,
            include_bank_statement=True,
            kind="all",
        )
    except Exception as e:
        log.exception(f"[auditor] build_full_package crashed: {e}")
        return {}, {"_error": str(e)}

    if not zip_bytes:
        log.warning(f"[auditor] build_full_package returned empty zip, status={status}")
        return {}, status

    texts = _extract_texts_from_zip(zip_bytes)
    log.info(
        f"[auditor] Rendered package: {len(texts)} files, "
        f"total {sum(len(t) for t in texts.values())} chars"
    )
    return texts, status


# ====================================================================
# Расчёт cost
# ====================================================================

def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> Optional[Decimal]:
    """USD за прогон по тарифам модели."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # Попробуем найти по prefix (если модель версионирована: claude-sonnet-4.6 vs claude-sonnet-4-5-20251201)
        for key, val in MODEL_PRICING.items():
            if model.startswith(key) or key.startswith(model.split(":")[0]):
                pricing = val
                break

    if not pricing:
        return None

    input_cost = Decimal(input_tokens) * Decimal(pricing["input"]) / Decimal(1_000_000)
    output_cost = Decimal(output_tokens) * Decimal(pricing["output"]) / Decimal(1_000_000)
    return (input_cost + output_cost).quantize(Decimal("0.0001"))


# ====================================================================
# Главная функция: вызывается из BackgroundTasks
# ====================================================================

def run_audit_in_background(report_id: int) -> None:
    """
    Sync wrapper для BackgroundTasks. Внутри запускает async _run_audit_async.

    BackgroundTasks вызывает sync функции, а LLMClient.complete — async,
    поэтому нужен asyncio.run().
    """
    log.info(f"[auditor] Starting audit for report {report_id}")
    try:
        asyncio.run(_run_audit_async(report_id))
    except Exception as e:
        log.exception(f"[auditor] Audit {report_id} crashed at top level: {e}")
        # Финальный fallback: пометить отчёт как failed
        _mark_report_failed(report_id, f"Top-level crash: {e}")


def _mark_report_failed(report_id: int, error_text: str) -> None:
    """Помечает AuditReport как failed (is_running=False, error=text)."""
    from app.db.session import engine
    from app.models import AuditReport, AuditVerdict

    try:
        with Session(engine) as session:
            report = session.get(AuditReport, report_id)
            if not report:
                log.error(f"[auditor] Cannot mark failed: report {report_id} not found")
                return
            report.is_running = False
            report.verdict = AuditVerdict.WARN
            report.error = error_text[:5000]
            report.finished_at = datetime.utcnow()
            if report.started_at:
                report.duration_ms = int((report.finished_at - report.started_at).total_seconds() * 1000)
            session.add(report)
            session.commit()
    except Exception as e:
        log.exception(f"[auditor] Cannot even mark report as failed: {e}")


async def _run_audit_async(report_id: int) -> None:
    """Главный цикл. Открывает свой Session чтобы не зависеть от request-context."""
    from app.db.session import engine
    from app.models import (
        AuditReport, AuditFinding, AuditVerdict, AuditCategory,
        AuditSeverity, Application,
    )
    from app.services.audit.context_builder import build_audit_context
    from app.services.audit.prompts import get_system_prompt, get_user_prompt
    from app.services.llm.factory import get_llm_client

    started = datetime.utcnow()

    with Session(engine) as session:
        report = session.get(AuditReport, report_id)
        if not report:
            log.error(f"[auditor] Report {report_id} not found")
            return

        # === 1. Загрузка Application ===
        application = session.get(Application, report.application_id)
        if not application:
            _mark_report_failed(report_id, f"Application {report.application_id} not found")
            return

        try:
            # === 2. Сборка context ===
            log.info(f"[auditor] Building context for application {application.id}")
            ctx = build_audit_context(
                application_id=application.id,
                session=session,
                include_generated_docs=False,  # генерируем сами ниже через build_full_package
            )

            # === 3. Рендер пакета в памяти (DOCX+PDF) ===
            log.info(f"[auditor] Rendering full package for audit...")
            texts, render_status = _render_full_package_for_audit(application, session)
            # Подмешиваем тексты в context (overwrite generated_documents_text)
            ctx.generated_documents_text = texts

            # === 4. Финализация context ===
            context_json = ctx.to_llm_json()
            context_hash = ctx.context_hash()
            report.context_hash = context_hash

            log.info(
                f"[auditor] Context ready: hash={context_hash[:12]} "
                f"size={len(context_json)} chars, {len(texts)} doc texts"
            )

            # === 5. LLM call ===
            llm = get_llm_client()
            system = get_system_prompt()
            user = get_user_prompt(context_json)

            # Модель — из env (используется default LLM)
            model_name = llm.default_model
            report.model_used = model_name
            session.add(report)
            session.commit()

            log.info(f"[auditor] Calling LLM {model_name}, input ~{len(system)+len(user)} chars")
            llm_response = await llm.complete(
                system=system,
                user=user,
                model=model_name,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=0.0,  # детерминированно, для воспроизводимости
            )

            log.info(f"[auditor] LLM responded: {len(llm_response)} chars")

            # === 6. Парсинг ответа ===
            try:
                parsed = _parse_llm_response(llm_response)
            except ValueError as e:
                _mark_report_failed(report_id, f"Failed to parse LLM response: {e}")
                return

            verdict_str = parsed["verdict"]
            findings_raw = parsed.get("findings", [])
            summary_text = parsed.get("summary", "")

            # === 7. Сохранение findings ===
            saved_findings = []
            for idx, raw in enumerate(findings_raw):
                normalized = _validate_finding(raw, idx)
                if not normalized:
                    continue

                f = AuditFinding(
                    report_id=report.id,
                    category=AuditCategory(normalized["category"]),
                    severity=AuditSeverity(normalized["severity"]),
                    title=normalized["title"],
                    description=normalized["description"],
                    evidence=normalized["evidence"],
                    field_path=normalized["field_path"],
                    current_value=normalized["current_value"],
                    suggested_value=normalized["suggested_value"],
                    fix_action=normalized["fix_action"],
                    fix_payload=normalized["fix_payload"],
                    sort_order=normalized["sort_order"],
                )
                session.add(f)
                saved_findings.append(f)

            session.commit()
            log.info(f"[auditor] Saved {len(saved_findings)} findings")

            # === 8. Подсчёт summary ===
            counts = {
                "critical": sum(1 for f in saved_findings if f.severity == AuditSeverity.CRITICAL),
                "warning": sum(1 for f in saved_findings if f.severity == AuditSeverity.WARNING),
                "info": sum(1 for f in saved_findings if f.severity == AuditSeverity.INFO),
                "total": len(saved_findings),
                "open": len(saved_findings),
                "accepted": 0,
                "dismissed": 0,
                "manually_fixed": 0,
            }

            # === 9. Финализация отчёта ===
            report.verdict = AuditVerdict(verdict_str)
            report.summary_counts = counts
            report.is_running = False
            report.finished_at = datetime.utcnow()
            report.duration_ms = int((report.finished_at - started).total_seconds() * 1000)

            # Токены и cost (если LLM вернёт usage — пока берём приблизительно)
            input_tokens_estimate = (len(system) + len(user)) // 4  # rough estimate
            output_tokens_estimate = len(llm_response) // 4
            report.input_tokens = input_tokens_estimate
            report.output_tokens = output_tokens_estimate
            report.cost_usd = _calculate_cost(model_name, input_tokens_estimate, output_tokens_estimate)

            # Summary — добавляем как комментарий в начало (можно отдельным полем потом)
            if summary_text and not report.error:
                # Сохраним summary в summary_counts._llm_summary как метаполе
                report.summary_counts = {**counts, "_llm_summary": summary_text[:1000]}

            session.add(report)
            session.commit()

            log.info(
                f"[auditor] Audit {report_id} complete: "
                f"verdict={verdict_str}, findings={len(saved_findings)} "
                f"(critical={counts['critical']}, warning={counts['warning']}, info={counts['info']}), "
                f"duration={report.duration_ms}ms, cost={report.cost_usd}"
            )

        except Exception as e:
            log.exception(f"[auditor] Audit {report_id} failed: {e}")
            _mark_report_failed(report_id, f"{type(e).__name__}: {e}")


# ====================================================================
# Smoke test (sync вариант для python -c)
# ====================================================================

def smoke_test_audit(application_id: int) -> None:
    """
    Синхронный smoke test — создаёт AuditReport и сразу прогоняет.

        python -c "from app.services.audit.auditor import smoke_test_audit; smoke_test_audit(26)"

    ВНИМАНИЕ: реально дёргает LLM, стоит ~$0.15.
    """
    from app.db.session import engine
    from app.models import AuditReport, AuditVerdict, Application

    with Session(engine) as session:
        application = session.get(Application, application_id)
        if not application:
            print(f"[ERR] Application {application_id} not found")
            return

        report = AuditReport(
            application_id=application_id,
            verdict=AuditVerdict.WARN,
            is_running=True,
            triggered_by="smoke_test",
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        print(f"Created report {report.id}, starting audit...")

    # Запускаем sync
    run_audit_in_background(report.id)

    # Перечитать результат
    with Session(engine) as session:
        report = session.get(AuditReport, report.id)
        print(f"\n=== Audit {report.id} done ===")
        print(f"Verdict:       {report.verdict}")
        print(f"Findings:      {report.summary_counts.get('total', 0)}")
        print(f"  critical:    {report.summary_counts.get('critical', 0)}")
        print(f"  warning:     {report.summary_counts.get('warning', 0)}")
        print(f"  info:        {report.summary_counts.get('info', 0)}")
        print(f"Duration:      {report.duration_ms} ms")
        print(f"Cost:          ${report.cost_usd}")
        print(f"Model:         {report.model_used}")
        if report.error:
            print(f"\nERROR:         {report.error}")
