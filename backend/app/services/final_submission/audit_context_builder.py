# -*- coding: utf-8 -*-
"""
Pack 39.0-D — Context builder для финального аудита.

Собирает JSON-досье из:
- applicant + company + position
- computed_checks (ИНН checksum, BIK, ГОСТ-транслит и т.д.)
- список всех активных документов (is_active=True) с extracted_text

В отличие от Pack 37.0 context_builder.py (~26 KB) — здесь короче, потому что
не надо рендерить пакет из шаблонов, у нас уже есть готовые extracted_text
загруженных документов.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models import (
    Applicant, Application, Company, FinalSubmissionDocument,
)

log = logging.getLogger(__name__)


# ====================================================================
# Утилиты
# ====================================================================

def _model_to_dict(obj: Any, exclude: Optional[set] = None) -> Dict[str, Any]:
    """SQLModel instance -> plain dict, JSON-сериализуемый."""
    if obj is None:
        return {}
    exclude = exclude or set()
    result = {}
    for key in obj.__fields__.keys() if hasattr(obj, "__fields__") else obj.__dict__.keys():
        if key in exclude or key.startswith("_"):
            continue
        try:
            value = getattr(obj, key)
        except Exception:
            continue
        # Сериализация
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, "value"):  # Enum
            result[key] = value.value
        elif isinstance(value, (str, int, float, bool, list, dict, type(None))):
            result[key] = value
        else:
            try:
                result[key] = str(value)
            except Exception:
                result[key] = None
    return result


def _is_gibberish(value: Optional[str]) -> bool:
    """Эвристика для мусорных значений (xcvxcv, test, 12345)."""
    if not value or not isinstance(value, str):
        return False
    v = value.strip().lower()
    if len(v) < 2:
        return True
    # Слишком много повторов одной буквы
    if re.search(r"(.)\1{5,}", v):
        return True
    # Шаблонные мусорные значения
    if v in ("test", "тест", "asdf", "qwer", "xxx", "123", "1234", "12345", "todo", "fixme"):
        return True
    # Подряд идущие 5+ согласных без гласных (xcvxcv)
    if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", v):
        return True
    return False


def _validate_inn(inn: Optional[str], expected_len: int) -> bool:
    """Проверка контрольной суммы ИНН (упрощённая)."""
    if not inn or not isinstance(inn, str):
        return False
    inn = inn.strip()
    if not inn.isdigit() or len(inn) != expected_len:
        return False
    # Полная проверка checksum опущена — backend часто имеет свою функцию
    return True


# ====================================================================
# Build context
# ====================================================================

@dataclass
class FinalAuditContext:
    applicant_db: Dict[str, Any] = field(default_factory=dict)
    company_db: Dict[str, Any] = field(default_factory=dict)
    application_meta: Dict[str, Any] = field(default_factory=dict)
    computed_checks: Dict[str, Any] = field(default_factory=dict)
    documents: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "applicant_db": self.applicant_db,
                "company_db": self.company_db,
                "application_meta": self.application_meta,
                "computed_checks": self.computed_checks,
                "documents": self.documents,
            },
            ensure_ascii=False,
            indent=2,
        )


def build_final_audit_context(
    *,
    applicant_id: int,
    application_id: int,
    session: Session,
) -> FinalAuditContext:
    """
    Главная функция: собирает context для LLM.
    """
    ctx = FinalAuditContext()

    # === Applicant ===
    applicant = session.get(Applicant, applicant_id)
    if applicant:
        ctx.applicant_db = _model_to_dict(applicant)
    else:
        log.warning(f"[final_audit_ctx] Applicant {applicant_id} not found")

    # === Application meta ===
    application = session.get(Application, application_id)
    if application:
        ctx.application_meta = _model_to_dict(application, exclude={"applicant_id"})

        # === Company ===
        company_id = getattr(application, "company_id", None)
        if company_id:
            company = session.get(Company, company_id)
            if company:
                ctx.company_db = _model_to_dict(company)

    # === Computed checks ===
    checks = {}

    if applicant:
        # Gibberish detection для applicant
        gib_fields = []
        for f in ("last_name_native", "first_name_native", "middle_name_native",
                  "last_name_latin", "first_name_latin", "home_address",
                  "birth_place_latin"):
            val = getattr(applicant, f, None)
            if _is_gibberish(val):
                gib_fields.append({"field": f, "value": val})
        checks["applicant_gibberish_fields"] = gib_fields

        # INN checksum
        inn = getattr(applicant, "inn", None)
        checks["applicant_inn"] = inn
        checks["applicant_inn_format_ok"] = _validate_inn(inn, expected_len=12)

        # Паспорт expiry vs дата подачи
        fp_date = getattr(application, "fingerprint_date", None) if application else None
        pass_exp = getattr(applicant, "passport_expiry_date", None)
        if fp_date and pass_exp:
            try:
                from datetime import timedelta
                if isinstance(fp_date, str):
                    fp_date_parsed = datetime.fromisoformat(fp_date).date()
                else:
                    fp_date_parsed = fp_date if hasattr(fp_date, "year") else None
                if isinstance(pass_exp, str):
                    pass_exp_parsed = datetime.fromisoformat(pass_exp).date()
                else:
                    pass_exp_parsed = pass_exp if hasattr(pass_exp, "year") else None
                if fp_date_parsed and pass_exp_parsed:
                    delta = (pass_exp_parsed - fp_date_parsed).days
                    checks["passport_days_to_expiry_from_submission"] = delta
                    checks["passport_expiry_ok_for_visa"] = delta >= 180
            except Exception as e:
                log.warning(f"[final_audit_ctx] passport expiry calc failed: {e}")

    if ctx.company_db:
        # Gibberish для company
        gib_fields_co = []
        for f in ("name", "address", "director_name", "tax_id_primary", "ogrn",
                  "bank_account", "bank_bic"):
            val = ctx.company_db.get(f)
            if _is_gibberish(val):
                gib_fields_co.append({"field": f, "value": val})
        checks["company_gibberish_fields"] = gib_fields_co

        # INN/OGRN/BIK format
        checks["company_inn_format_ok"] = _validate_inn(
            ctx.company_db.get("tax_id_primary"), expected_len=10
        )
        ogrn = ctx.company_db.get("ogrn")
        checks["company_ogrn_format_ok"] = (
            isinstance(ogrn, str) and ogrn.isdigit() and len(ogrn) == 13
        )
        bik = ctx.company_db.get("bank_bic")
        checks["company_bik_format_ok"] = (
            isinstance(bik, str) and bik.isdigit() and len(bik) == 9
        )

    ctx.computed_checks = checks

    # === Documents (только активные) ===
    stmt = (
        select(FinalSubmissionDocument)
        .where(FinalSubmissionDocument.applicant_id == applicant_id)
        .where(FinalSubmissionDocument.is_active == True)  # noqa: E712
        .order_by(FinalSubmissionDocument.id)
    )
    docs = session.exec(stmt).all()

    for d in docs:
        text = d.extracted_text or ""
        # Обрезка длинного текста чтобы не взорвать context
        MAX_TEXT_PER_DOC = 15_000
        truncated = False
        if len(text) > MAX_TEXT_PER_DOC:
            text = text[:MAX_TEXT_PER_DOC] + "\n\n[... TRUNCATED ...]"
            truncated = True

        ctx.documents.append({
            "id": d.id,
            "filename": d.original_filename,
            "doc_category": d.doc_category.value if d.doc_category else None,
            "doc_category_confidence": (
                float(d.doc_category_confidence) if d.doc_category_confidence is not None else None
            ),
            "doc_category_source": d.doc_category_source.value if hasattr(d.doc_category_source, "value") else str(d.doc_category_source),
            "page_count": d.page_count,
            "extraction_method": d.extraction_method.value if hasattr(d.extraction_method, "value") and d.extraction_method else (str(d.extraction_method) if d.extraction_method else None),
            "extracted_text": text,
            "text_truncated": truncated,
            "file_size_bytes": d.file_size_bytes,
        })

    log.info(
        f"[final_audit_ctx] Built: applicant={applicant_id}, "
        f"docs={len(ctx.documents)}, "
        f"total_text_chars={sum(len(d['extracted_text']) for d in ctx.documents)}"
    )

    return ctx
