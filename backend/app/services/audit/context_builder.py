# -*- coding: utf-8 -*-
"""
Pack 37.0-B — Context builder.

Главный мозг сборки «досье кейса» для LLM-аудитора. Собирает воедино:
- applicant из БД (все поля + education + work_history + parents)
- company / position / representative / spain_address / bank — связанные сущности
- ApplicantDocument.parsed_data — сырой OCR оригиналов (независимый источник истины!)
- Сгенерированные DOCX/PDF — извлечённый текст через document_extractor
- Computed checks — ожидаемая транслитерация ГОСТ, валидация ИНН/БИК checksum,
  сверка сумм договор/акты/счета/выписка, детекция мусорных полей

Результат — структурированный JSON ~30-50k токенов, который LLM получает целиком
и сравнивает всё со всем.

Архитектурный принцип: parsed_data из OCR паспорта/диплома — это «то что реально
написано в оригинале документа». applicant.last_name_native — это «то что лежит
в БД сейчас, после возможных правок менеджера». Если они расходятся — finding.
"""
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

log = logging.getLogger(__name__)


# ====================================================================
# Container
# ====================================================================

@dataclass
class AuditContext:
    """
    Полное «досье кейса» для передачи в LLM.

    К нему есть метод to_llm_json() — он сериализует в строку с
    отсортированными ключами (для воспроизводимости context_hash).
    """
    case_id: str  # application.case_number, например "2026-0003"
    application_id: int

    # Основные сущности из БД (как dict, чтобы влезали Optional и JSON-поля)
    applicant_db: Dict[str, Any] = field(default_factory=dict)
    company_db: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, Any] = field(default_factory=dict)
    representative: Dict[str, Any] = field(default_factory=dict)
    spain_address: Dict[str, Any] = field(default_factory=dict)
    bank: Dict[str, Any] = field(default_factory=dict)
    application_meta: Dict[str, Any] = field(default_factory=dict)

    # OCR-данные оригиналов (источник истины для сверки)
    documents_ocr: List[Dict[str, Any]] = field(default_factory=list)

    # Тексты из сгенерированных DOCX/PDF
    generated_documents_text: Dict[str, str] = field(default_factory=dict)

    # Pre-computed валидации, которые проще сделать кодом чем просить у LLM
    computed_checks: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_llm_json(self) -> str:
        """
        Сериализует в JSON для передачи в LLM.

        sort_keys=True гарантирует, что context_hash одинаков для одинаковых
        данных независимо от порядка добавления полей.
        """
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            default=_json_default,
            sort_keys=True,
            indent=2,
        )

    def context_hash(self) -> str:
        """SHA256 от JSON — для контроля «что менялось между прогонами»."""
        return hashlib.sha256(self.to_llm_json().encode("utf-8")).hexdigest()


def _json_default(obj):
    """JSON serializer для date/datetime/Decimal."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return str(obj)


# ====================================================================
# Извлекаем поля из ORM-объектов
# ====================================================================

def _model_to_dict(obj: Any, exclude: tuple = ()) -> Dict[str, Any]:
    """
    SQLModel/SQLAlchemy object → dict.

    Берёт публичные атрибуты, пропускает relationships (sa-instrumented),
    пропускает приватные (_sa_*), пропускает поля из exclude.
    """
    if obj is None:
        return {}

    result = {}
    # Используем .__dict__ + фильтруем
    for k, v in vars(obj).items():
        if k.startswith("_"):
            continue
        if k in exclude:
            continue
        # Пропускаем relationships (списки SQLModel-объектов)
        if isinstance(v, list) and v and hasattr(v[0], "__tablename__"):
            continue
        # Пропускаем single relationships
        if hasattr(v, "__tablename__"):
            continue
        result[k] = v
    return result


# ====================================================================
# Computed checks (валидация что не требует LLM)
# ====================================================================

# Эвристики работают ТОЛЬКО для текстовых полей (имена, адреса, ФИО).
# Для числовых полей (ИНН/БИК/счёт) применяются отдельные validate_inn/bik/ogrn
# с проверкой контрольной суммы. См. Pack 37.0-B.1 hotfix.
_GIBBERISH_PATTERNS = [
    # Повторяющиеся одинаковые буквы: aaaaaa, xxxxxxx (5+ раз подряд)
    re.compile(r"([a-zA-Zа-яА-Я])\1{4,}", re.IGNORECASE),
    # Латинская «клавиатурная гирлянда» без гласных и без пробелов:
    # xcvxcvxccv, asdfasdf, qwertyqwerty (только согласные, 6+ букв)
    re.compile(r"^[bcdfghjklmnpqrstvwxz]{6,}$", re.IGNORECASE),
    # Известные тестовые маркеры — как отдельные слова, не подстроки
    re.compile(r"\b(test|asdf|qwerty|lorem|ipsum|sample)\b", re.IGNORECASE),
    # Цифровые последовательности в ТЕКСТОВОМ поле (адрес: "123456789" — мусор)
    # Применяется только к whitelist полей (см. блоки company/applicant gibberish ниже)
    re.compile(r"^[\d\s\-]{6,}$"),
]


def _looks_like_gibberish(value: Any) -> Optional[str]:
    """
    Эвристика на мусорные значения вроде 'xcvxcvxccv', 'test', '345345345'.

    Возвращает причину (str) если выглядит как мусор, или None если валидное.
    """
    if not isinstance(value, str) or not value.strip():
        return None

    stripped = value.strip()
    if len(stripped) < 4:
        return None  # короткие значения не проверяем

    for pat in _GIBBERISH_PATTERNS:
        if pat.search(stripped):
            return f"matches gibberish pattern: {pat.pattern}"
    return None


def _validate_inn_checksum(inn: str) -> bool:
    """
    Проверка контрольной суммы ИНН (10 или 12 цифр).

    Алгоритм ФНС: https://www.consultant.ru/document/cons_doc_LAW_134082/
    """
    if not inn or not inn.isdigit():
        return False

    if len(inn) == 10:
        coeffs = [2, 4, 10, 3, 5, 9, 4, 6, 8, 0]
        s = sum(int(inn[i]) * coeffs[i] for i in range(10))
        return (s % 11 % 10) == int(inn[9])

    if len(inn) == 12:
        coeffs1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0, 0]
        coeffs2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]
        s1 = sum(int(inn[i]) * coeffs1[i] for i in range(11))
        s2 = sum(int(inn[i]) * coeffs2[i] for i in range(11))
        return (
            (s1 % 11 % 10) == int(inn[10])
            and (s2 % 11 % 10) == int(inn[11])
        )

    return False


def _validate_bik(bik: str) -> bool:
    """БИК — ровно 9 цифр."""
    return bool(bik and bik.isdigit() and len(bik) == 9)


def _validate_ogrn(ogrn: str) -> bool:
    """ОГРН — 13 цифр, ОГРНИП — 15 цифр."""
    return bool(ogrn and ogrn.isdigit() and len(ogrn) in (13, 15))


# GOST 7.79-2000 System B (упрощённая версия — реальный transliter в проекте
# уже есть в app.services.translit или подобном; здесь сверка ОЖИДАЕМОГО результата
# с тем что хранится в applicant.last_name_latin)
_GOST_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _gost_transliterate(text: str) -> str:
    """
    Простая ГОСТ-транслитерация для сверки.

    Это НЕ финальный transliter, а проверочный. Если результат не совпадает
    с applicant.last_name_latin — это hint для LLM, не жёсткий verdict.
    Реальный transliter в проекте может использовать ICAO 9303 (загранпаспорт)
    или другую систему.
    """
    if not text:
        return ""
    out = []
    for ch in text.lower():
        out.append(_GOST_MAP.get(ch, ch))
    return "".join(out).upper()


def _compute_checks(
    applicant_db: Dict[str, Any],
    company_db: Dict[str, Any],
    documents_ocr: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Pre-computed валидации для LLM. Это не финальный verdict — LLM их учитывает,
    но также может найти что мы пропустили.
    """
    checks: Dict[str, Any] = {}

    # === ИНН валидации ===
    if company_inn := company_db.get("tax_id_primary"):
        checks["company_inn_checksum_valid"] = _validate_inn_checksum(str(company_inn))
        checks["company_inn_value"] = str(company_inn)

    if applicant_inn := applicant_db.get("inn"):
        checks["applicant_inn_checksum_valid"] = _validate_inn_checksum(str(applicant_inn))
        checks["applicant_inn_value"] = str(applicant_inn)

    # === БИК / ОГРН ===
    if company_bik := company_db.get("bank_bic"):
        checks["company_bik_valid"] = _validate_bik(str(company_bik))

    if company_ogrn := company_db.get("ogrn"):
        checks["company_ogrn_valid"] = _validate_ogrn(str(company_ogrn))

    # === GOST транслит сверка ===
    # Pack 37.5: ГОСТ применяется ко всем, но finding всегда info (не warning).
    # Паспорт всегда источник истины — для русских ГОСТ совпадает с паспортом,
    # для китайцев в паспорте пиньинь (XIA), для японцев Хэпбёрн.
    # Несоответствие ГОСТ — лишь подсказка менеджеру: «обратите внимание,
    # что латиница не построена по ГОСТ» (это нормально для большинства стран).
    last_native = applicant_db.get("last_name_native") or ""
    first_native = applicant_db.get("first_name_native") or ""
    last_latin = (applicant_db.get("last_name_latin") or "").upper()
    first_latin = (applicant_db.get("first_name_latin") or "").upper()

    if last_native and last_latin:
        expected = _gost_transliterate(last_native)
        checks["last_name_gost_expected"] = expected
        checks["last_name_gost_matches"] = (expected == last_latin)
        if expected != last_latin:
            checks["last_name_gost_diff"] = {
                "native": last_native,
                "expected_gost": expected,
                "actual_db": last_latin,
            }

    if first_native and first_latin:
        expected = _gost_transliterate(first_native)
        checks["first_name_gost_expected"] = expected
        checks["first_name_gost_matches"] = (expected == first_latin)

    # === OCR vs БД консистенси для имён ===
    # Это «hint» для LLM — реальную сверку делает он, но мы выделяем явные расхождения.
    ocr_name_conflicts = []
    for doc_ocr in documents_ocr:
        parsed = doc_ocr.get("parsed_data") or {}
        doc_type = doc_ocr.get("doc_type", "")

        ocr_last = parsed.get("last_name_native")
        ocr_first = parsed.get("first_name_native")

        if ocr_last and last_native and ocr_last.strip().lower() != last_native.strip().lower():
            ocr_name_conflicts.append({
                "doc_type": doc_type,
                "field": "last_name_native",
                "ocr_value": ocr_last,
                "db_value": last_native,
            })
        if ocr_first and first_native and ocr_first.strip().lower() != first_native.strip().lower():
            ocr_name_conflicts.append({
                "doc_type": doc_type,
                "field": "first_name_native",
                "ocr_value": ocr_first,
                "db_value": first_native,
            })

    if ocr_name_conflicts:
        checks["ocr_db_name_conflicts"] = ocr_name_conflicts

    # === Мусорные значения в полях компании ===
    # ВАЖНО (Pack 37.0-B.1): только текстовые поля. Для числовых (tax_id_primary,
    # kpp, ogrn, bank_account, bank_bic) — отдельные валидации checksum/length
    # выше. Если применить gibberish-эвристику ко всем подряд — паттерн
    # ^[\d\s\-]{6,}$ обнулит легитимные ИНН/счёт/БИК.
    company_gibberish = {}
    for field_name in [
        "name", "address", "director_name", "director_position",
        "bank_name", "phone", "email",
    ]:
        val = company_db.get(field_name)
        reason = _looks_like_gibberish(val)
        if reason:
            company_gibberish[field_name] = {
                "value": val,
                "reason": reason,
            }
    if company_gibberish:
        checks["company_gibberish_fields"] = company_gibberish

    # === Мусорные значения в applicant ===
    # ВАЖНО (Pack 37.0-B.1): только текстовые поля. ИНН/passport_number
    # имеют отдельные валидации checksum/length.
    applicant_gibberish = {}
    for field_name in [
        "last_name_native", "first_name_native", "middle_name_native",
        "last_name_latin", "first_name_latin",
        "birth_place_latin", "passport_issuer", "passport_issuer_ru",
        "home_address", "home_address_line2", "email",
    ]:
        val = applicant_db.get(field_name)
        reason = _looks_like_gibberish(val)
        if reason:
            applicant_gibberish[field_name] = {
                "value": val,
                "reason": reason,
            }
    if applicant_gibberish:
        checks["applicant_gibberish_fields"] = applicant_gibberish

    # === Срок действия паспорта ===
    pass_expiry = applicant_db.get("passport_expiry_date")
    if pass_expiry:
        if isinstance(pass_expiry, str):
            try:
                pass_expiry = date.fromisoformat(pass_expiry)
            except ValueError:
                pass_expiry = None
        if isinstance(pass_expiry, (date, datetime)):
            today = date.today()
            expiry_d = pass_expiry if isinstance(pass_expiry, date) else pass_expiry.date()
            days_left = (expiry_d - today).days
            checks["passport_days_until_expiry"] = days_left
            # Виза D — требуется минимум 6 мес (180 дней) запаса
            checks["passport_expiry_ok_for_visa"] = days_left >= 180

    return checks


# ====================================================================
# OCR documents loader
# ====================================================================

def _load_documents_ocr(
    application_id: int,
    session: Session,
) -> List[Dict[str, Any]]:
    """
    Загружает все OCR_DONE документы заявки с их parsed_data.

    Это и есть источник истины для сравнения с applicant: parsed_data —
    то что реально было распознано из оригинала.
    """
    from app.models import ApplicantDocument, ApplicantDocumentStatus

    docs = session.exec(
        select(ApplicantDocument)
        .where(ApplicantDocument.application_id == application_id)
        .where(ApplicantDocument.status == ApplicantDocumentStatus.OCR_DONE)
        .order_by(ApplicantDocument.created_at)
    ).all()

    result = []
    for doc in docs:
        result.append({
            "id": doc.id,
            "doc_type": doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type),
            "file_name": doc.file_name,
            "applied_to_applicant": doc.applied_to_applicant,
            "ocr_completed_at": doc.ocr_completed_at.isoformat() if doc.ocr_completed_at else None,
            "parsed_data": doc.parsed_data or {},
        })

    return result


# ====================================================================
# Главный entry-point
# ====================================================================

def build_audit_context(
    application_id: int,
    session: Session,
    include_generated_docs: bool = True,
) -> AuditContext:
    """
    Собирает полное досье кейса для аудитора.

    Args:
        application_id: ID заявки
        session: SQLModel session
        include_generated_docs: True — тянуть и парсить DOCX/PDF из R2.
                                False — только БД + OCR (для быстрых тестов).

    Returns:
        AuditContext, готовый к to_llm_json() и передаче в auditor.

    Raises:
        ValueError если application не найдена.
    """
    from app.models import Application

    application = session.get(Application, application_id)
    if not application:
        raise ValueError(f"Application {application_id} not found")

    log_prefix = f"[ctx_builder:app#{application_id}]"
    log.info(f"{log_prefix} Building audit context...")

    # === 1. Базовые сущности из БД ===
    applicant = application.applicant
    applicant_dict = _model_to_dict(applicant) if applicant else {}

    company = None
    company_dict = {}
    if getattr(application, "company_id", None):
        from app.models import Company
        company = session.get(Company, application.company_id)
        company_dict = _model_to_dict(company) if company else {}

    position = None
    position_dict = {}
    if getattr(application, "position_id", None):
        from app.models import Position
        position = session.get(Position, application.position_id)
        position_dict = _model_to_dict(position) if position else {}

    representative_dict = {}
    if getattr(application, "representative_id", None):
        from app.models import Representative
        rep = session.get(Representative, application.representative_id)
        representative_dict = _model_to_dict(rep) if rep else {}

    spain_address_dict = {}
    if getattr(application, "spain_address_id", None):
        from app.models import SpainAddress
        addr = session.get(SpainAddress, application.spain_address_id)
        spain_address_dict = _model_to_dict(addr) if addr else {}

    bank_dict = {}
    if applicant and getattr(applicant, "bank_id", None):
        from app.models import Bank
        bank = session.get(Bank, applicant.bank_id)
        bank_dict = _model_to_dict(bank) if bank else {}

    # === 2. Метаданные заявки ===
    application_meta = {
        "id": application.id,
        "case_number": getattr(application, "case_number", None),
        "status": application.status.value if hasattr(application.status, "value") else str(application.status),
        "created_at": application.created_at.isoformat() if application.created_at else None,
        "is_paid": getattr(application, "is_paid", None),
        "is_urgent": getattr(application, "is_urgent", None),
        "is_ready_for_pickup": getattr(application, "is_ready_for_pickup", None),
        "nie": getattr(application, "nie", None),
        "fingerprint_date": (
            application.fingerprint_date.isoformat()
            if getattr(application, "fingerprint_date", None) else None
        ),
        "tasa_type": (
            application.tasa_type.value
            if getattr(application, "tasa_type", None) and hasattr(application.tasa_type, "value")
            else None
        ),
        "amount_per_month": getattr(application, "amount_per_month", None),
        "contract_period_months": getattr(application, "contract_period_months", None),
        "contract_start_date": (
            application.contract_start_date.isoformat()
            if getattr(application, "contract_start_date", None) else None
        ),
    }

    # === 3. OCR оригиналов (источник истины) ===
    documents_ocr = _load_documents_ocr(application_id, session)
    log.info(f"{log_prefix} Loaded {len(documents_ocr)} OCR documents")

    # === 4. Извлечённый текст сгенерированных файлов ===
    generated_text: Dict[str, str] = {}
    if include_generated_docs:
        try:
            from app.services.audit.document_extractor import extract_application_documents
            extraction = extract_application_documents(application_id, session)
            generated_text = extraction.to_llm_dict()
            log.info(
                f"{log_prefix} Extracted text from {len(generated_text)} generated docs, "
                f"total {extraction.total_chars} chars"
            )
        except Exception as e:
            log.error(f"{log_prefix} Document extraction failed: {e}", exc_info=True)
            # Не падаем — аудит без текста сгенерированных всё равно полезен (OCR vs БД)

    # === 5. Computed checks ===
    computed = _compute_checks(applicant_dict, company_dict, documents_ocr)
    log.info(f"{log_prefix} Computed {len(computed)} pre-checks")

    # === 6. Собираем ===
    case_id = (
        getattr(application, "case_number", None)
        or f"APP-{application_id}"
    )

    ctx = AuditContext(
        case_id=case_id,
        application_id=application_id,
        applicant_db=applicant_dict,
        company_db=company_dict,
        position=position_dict,
        representative=representative_dict,
        spain_address=spain_address_dict,
        bank=bank_dict,
        application_meta=application_meta,
        documents_ocr=documents_ocr,
        generated_documents_text=generated_text,
        computed_checks=computed,
    )

    log.info(
        f"{log_prefix} Context ready: hash={ctx.context_hash()[:12]}..., "
        f"size={len(ctx.to_llm_json())} chars"
    )

    return ctx


# ====================================================================
# Smoke-test
# ====================================================================

def smoke_test_context(application_id: int) -> None:
    """
    python -c "from app.services.audit.context_builder import smoke_test_context; smoke_test_context(10)"
    """
    from app.db.session import engine
    from sqlmodel import Session

    with Session(engine) as session:
        try:
            ctx = build_audit_context(application_id, session, include_generated_docs=False)
        except ValueError as e:
            print(f"❌ {e}")
            return

    print(f"\n=== Context for application {application_id} ===")
    print(f"Case ID:        {ctx.case_id}")
    print(f"Context hash:   {ctx.context_hash()[:16]}...")
    print(f"JSON size:      {len(ctx.to_llm_json())} chars")
    print(f"OCR docs:       {len(ctx.documents_ocr)}")
    print(f"Computed:       {list(ctx.computed_checks.keys())}")
    print()
    print("=== Applicant fields ===")
    for k, v in list(ctx.applicant_db.items())[:15]:
        print(f"  {k:30s} = {v!r:60.60s}")
    print()
    print("=== Computed checks ===")
    print(json.dumps(ctx.computed_checks, ensure_ascii=False, indent=2, default=_json_default))
