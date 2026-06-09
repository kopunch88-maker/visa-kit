"""
Bank transactions endpoints — менеджер управляет транзакциями выписки.

Эти эндпоинты работают ДАЖЕ если шаблон выписки ещё не готов —
они только редактируют JSON в Application.bank_transactions_override.

Когда шаблон будет готов, эти данные автоматически подхватятся при рендере.

Эндпоинты:
    POST   /api/admin/applications/{id}/bank-transactions/generate  — создать черновик
    GET    /api/admin/applications/{id}/bank-transactions           — получить текущие
    PUT    /api/admin/applications/{id}/bank-transactions           — заменить весь список
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.models import Application, Applicant, Company
from app.services.bank_statement_generator import (
    generate_default_transactions,
    serialize_for_storage,
    deserialize_from_storage,
    DEFAULT_NPD_RATE,
    DEFAULT_BANK_FEE_PER_MONTH,
)
from .dependencies import require_manager

router = APIRouter(prefix="/admin/applications", tags=["bank-transactions"])


# ============================================================================
# Schemas
# ============================================================================

class BankTransactionItem(BaseModel):
    transaction_date: date
    code: str
    description: str
    amount: Decimal
    currency: str = "RUR"
    # Pack 47.2: category — мульти-банк поле для отображения в шаблонах,
    # которые делят строку транзакции на "категория + описание" (Сбер).
    # Альфа игнорирует. Опционально для back-compat со старыми tx в БД.
    category: Optional[str] = None


class BankStatementData(BaseModel):
    period_start: date
    period_end: date
    opening_balance: Decimal
    transactions: List[BankTransactionItem]


class BankStatementResponse(BaseModel):
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    total_income: Decimal
    total_expense: Decimal
    transactions: List[BankTransactionItem]
    is_generated_default: bool  # True if not yet edited by manager
    transaction_count: int


# Pack 51 — append-режим: добавить транзакции за [period_from, period_to]
# без перезаписи существующих. См. POST /bank-transactions/append.
class AppendPeriodPayload(BaseModel):
    period_from: date
    period_to: date


# ============================================================================
# Helpers
# ============================================================================

def _build_response(application: Application, session: Session) -> BankStatementResponse:
    """Собирает ответ — либо из сохранённых данных, либо генерирует на лету."""
    if application.bank_transactions_override:
        try:
            data = deserialize_from_storage(application.bank_transactions_override)
            transactions = data["transactions"]
            opening = data["opening_balance"]
            period_start = data["period_start"]
            period_end = data["period_end"]
            is_default = False
        except (KeyError, ValueError):
            data = _generate_for_app(application, session)
            transactions = data["transactions"]
            opening = data["opening_balance"]
            period_start = data["period_start"]
            period_end = data["period_end"]
            is_default = True
    else:
        data = _generate_for_app(application, session)
        if data is None:
            raise HTTPException(
                422,
                "Cannot generate transactions: application missing salary, "
                "submission_date, contract or company data",
            )
        transactions = data["transactions"]
        opening = data["opening_balance"]
        period_start = data["period_start"]
        period_end = data["period_end"]
        is_default = True

    total_income = sum(
        (t["amount"] for t in transactions if t["amount"] > 0),
        Decimal("0"),
    )
    total_expense = sum(
        (-t["amount"] for t in transactions if t["amount"] < 0),
        Decimal("0"),
    )
    closing = opening + total_income - total_expense

    return BankStatementResponse(
        period_start=period_start,
        period_end=period_end,
        opening_balance=opening,
        closing_balance=closing,
        total_income=total_income,
        total_expense=total_expense,
        transactions=[BankTransactionItem(**t) for t in transactions],
        is_generated_default=is_default,
        transaction_count=len(transactions),
    )


def _generate_for_app(application: Application, session: Session) -> Optional[dict]:
    """Генерирует свежий черновик для заявки. None если не хватает данных."""
    if not all([
        application.submission_date,
        application.salary_rub,
        application.contract_number,
        application.contract_sign_date,
        application.company_id,
    ]):
        return None

    company = session.get(Company, application.company_id)
    if not company:
        return None

    npd_rate = application.bank_npd_rate or DEFAULT_NPD_RATE
    monthly_fee = application.bank_monthly_fee or DEFAULT_BANK_FEE_PER_MONTH

    # Pack 35.5: достаём applicant для СБП-переводов (имя получателя + телефон РФ).
    # Без этого форматтер получит None → СБП-получатель станет «Получатель» вместо «Инь С.».
    _applicant_full_name_ru = None
    _applicant_phone = None
    if application.applicant_id:
        _applicant = session.get(Applicant, application.applicant_id)
        if _applicant is not None:
            _first = (_applicant.first_name_native or "").strip()
            _last = (_applicant.last_name_native or "").strip()
            _full = f"{_first} {_last}".strip()
            if not _full:
                # Fallback на латинские поля (для иностранцев без транслитерации)
                _first_l = (_applicant.first_name_latin or "").strip()
                _last_l = (_applicant.last_name_latin or "").strip()
                _full = f"{_first_l} {_last_l}".strip()
            _applicant_full_name_ru = _full or None
           
            _applicant_phone = _applicant.phone

    return generate_default_transactions(
        submission_date=application.submission_date,
        salary_rub=application.salary_rub,
        contract_number=application.contract_number,
        contract_sign_date=application.contract_sign_date,
        company_full_name=company.full_name_ru,
        company_inn=company.tax_id_primary,
        company_bank_account=company.bank_account,
        company_bank_bic=company.bank_bic,
        npd_rate=npd_rate,
        bank_fee=monthly_fee,
        seed=application.id,
        # Pack 35.5: пробрасываем applicant в генератор
        applicant_full_name_ru=_applicant_full_name_ru,
        applicant_phone=_applicant_phone,
        
        statement_date_override=getattr(application, "bank_statement_date", None),
        # Pack 50.31 — найм: аванс+зарплата по трудовому договору
        is_employment=str(getattr(application.application_type, "value", application.application_type)) == "EMPLOYMENT",
    )


def _append_for_app(
    application: Application,
    session: Session,
    period_from: date,
    period_to: date,
) -> Optional[dict]:
    """
    Pack 51 — дополнить существующий bank_transactions_override транзакциями
    за [period_from, period_to] БЕЗ изменения уже сохранённых данных.

    Возвращает dict в формате generate_default_transactions (готов для
    serialize_for_storage), или None если:
    - bank_transactions_override отсутствует или битый
    - не хватает обязательных полей заявки

    Логика:
    1. Генерируем новые tx ТОЛЬКО для [period_from, period_to] (с другим seed,
       чтобы не получить копию транзакций основной выписки).
    2. Дедуп против существующих по (date, code) — на случай overlap.
    3. Merge: existing + new_filtered, без сортировки (Sber/TBank
       postprocessors сами отсортируют при рендере; Альфа использует
       порядок-as-is).
    4. Расширяем period_start (min) и period_end (max) если новый период
       выходит за границы существующего.
    5. opening_balance ПЕРЕСЧИТЫВАЕТСЯ если period расширен НАЗАД:
       new_opening = old_opening - net_flow_of_prepended_slice.
       Это сохраняет точку непрерывности баланса — closing на старом
       period_end остаётся неизменным.
    """
    if not application.bank_transactions_override:
        return None

    if not all([
        application.submission_date,
        application.salary_rub,
        application.contract_number,
        application.contract_sign_date,
        application.company_id,
    ]):
        return None

    company = session.get(Company, application.company_id)
    if not company:
        return None

    npd_rate = application.bank_npd_rate or DEFAULT_NPD_RATE
    monthly_fee = application.bank_monthly_fee or DEFAULT_BANK_FEE_PER_MONTH

    _applicant_full_name_ru = None
    _applicant_phone = None
    if application.applicant_id:
        _applicant = session.get(Applicant, application.applicant_id)
        if _applicant is not None:
            _first = (_applicant.first_name_native or "").strip()
            _last = (_applicant.last_name_native or "").strip()
            _full = f"{_first} {_last}".strip()
            if not _full:
                _first_l = (_applicant.first_name_latin or "").strip()
                _last_l = (_applicant.last_name_latin or "").strip()
                _full = f"{_first_l} {_last_l}".strip()
            _applicant_full_name_ru = _full or None
            _applicant_phone = _applicant.phone

    # Деривативный seed чтобы не получить ту же RNG-последовательность
    # что и в основной выписке. Детерминированно по (app_id, period).
    import hashlib as _hashlib
    _seed_str = f"{application.id}|append|{period_from.isoformat()}|{period_to.isoformat()}"
    _seed = int(_hashlib.sha1(_seed_str.encode()).hexdigest()[:8], 16)

    new_data = generate_default_transactions(
        submission_date=application.submission_date,
        salary_rub=application.salary_rub,
        contract_number=application.contract_number,
        contract_sign_date=application.contract_sign_date,
        company_full_name=company.full_name_ru,
        company_inn=company.tax_id_primary,
        company_bank_account=company.bank_account,
        company_bank_bic=company.bank_bic,
        npd_rate=npd_rate,
        bank_fee=monthly_fee,
        seed=_seed,
        applicant_full_name_ru=_applicant_full_name_ru,
        applicant_phone=_applicant_phone,
        statement_date_override=getattr(application, "bank_statement_date", None),
        is_employment=str(getattr(application.application_type, "value", application.application_type)) == "EMPLOYMENT",
        # Pack 51 — явный период
        period_start_override=period_from,
        period_end_override=period_to,
    )

    # Загружаем существующее
    try:
        existing = deserialize_from_storage(application.bank_transactions_override)
    except (KeyError, ValueError):
        # Битый override — отказываемся, чтобы не затереть случайно
        return None

    # Дедуп новых против существующих по (date, code).
    existing_keys = {
        (t["transaction_date"].isoformat(), t["code"])
        for t in existing["transactions"]
    }
    new_tx_filtered = [
        t for t in new_data["transactions"]
        if (t["transaction_date"].isoformat(), t["code"]) not in existing_keys
    ]

    # Merge без сортировки — постпроцессоры сами разберутся
    merged_tx = list(existing["transactions"]) + new_tx_filtered

    # Расширение границ периода
    merged_period_start = min(existing["period_start"], period_from)
    merged_period_end = max(existing["period_end"], period_to)

    # Pack 51 — пересчёт opening_balance.
    # opening_balance = баланс на начало period_start. Если новый период
    # расширяется НАЗАД (period_from < existing.period_start) — новый
    # opening = старый - чистый поток tx из "prepended" слайса
    # [period_from, existing.period_start). Так closing на старом
    # period_end остаётся неизменным (точка непрерывности баланса):
    #   closing_new = opening_new + total_net
    #              = (opening_old - prepended_net) + (prepended_net + existing_net + after_net)
    #              = opening_old + existing_net + after_net
    # Если период расширяется ТОЛЬКО ВПЕРЁД (после) — prepended_slice пуст,
    # opening не меняется.
    prepended_slice = [
        t for t in new_tx_filtered
        if t["transaction_date"] < existing["period_start"]
    ]
    prepended_income = sum(
        (t["amount"] for t in prepended_slice if t["amount"] > 0),
        Decimal("0"),
    )
    prepended_expense = sum(
        (-t["amount"] for t in prepended_slice if t["amount"] < 0),
        Decimal("0"),
    )
    prepended_net = prepended_income - prepended_expense  # signed
    new_opening_balance = existing["opening_balance"] - prepended_net

    return {
        "statement_date": existing.get("statement_date"),
        "period_start": merged_period_start,
        "period_end": merged_period_end,
        "opening_balance": new_opening_balance,
        # closing_balance / total_* пересчитываются в _build_bank_context
        # при рендере. serialize_for_storage их игнорирует — оставляем
        # для совместимости с интерфейсом generate_default_transactions.
        "closing_balance": Decimal("0"),
        "total_income": Decimal("0"),
        "total_expense": Decimal("0"),
        "transactions": merged_tx,
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/{app_id}/bank-transactions/generate", response_model=BankStatementResponse)
def generate_bank_transactions(
    app_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> BankStatementResponse:
    """
    Сгенерировать (или перегенерировать) черновик транзакций.

    Если у заявки уже были сохранены отредактированные транзакции —
    они БУДУТ ПЕРЕЗАПИСАНЫ свежим черновиком. Менеджер должен подтверждать
    эту операцию в UI с предупреждением.
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    data = _generate_for_app(application, session)
    if data is None:
        raise HTTPException(
            422,
            "Cannot generate: application missing required fields "
            "(salary_rub, submission_date, contract_number, contract_sign_date, company_id)",
        )

    # Сохраняем в БД (как сериализованную структуру)
    application.bank_transactions_override = serialize_for_storage(data)
    session.add(application)
    session.flush()
    session.refresh(application)

    return _build_response(application, session)


@router.post("/{app_id}/bank-transactions/append", response_model=BankStatementResponse)
def append_bank_transactions(
    app_id: int,
    payload: AppendPeriodPayload,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> BankStatementResponse:
    """
    Pack 51 — дополнить выписку транзакциями за [period_from, period_to]
    БЕЗ перезаписи существующих. Расширяет период (period_start = min,
    period_end = max от существующего и нового). Если period_from раньше
    существующего period_start — пересчитывает opening_balance так, чтобы
    closing на старом period_end не сдвинулся.

    422 если:
    - выписка ещё не сгенерирована (bank_transactions_override = NULL)
    - period_from > period_to
    - не хватает обязательных полей заявки
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    if payload.period_from > payload.period_to:
        raise HTTPException(422, "period_from must be <= period_to")

    # Pack 51-fix1: если override ещё не существует — генерим базовую выписку
    # с текущими настройками и сохраняем как override. Это фиксирует
    # «дефолтное» состояние (что показывалось бы при on-the-fly рендере),
    # чтобы было что дополнять. На UI это поведение отражено хинтом
    # «Текущая дефолтная выписка будет зафиксирована».
    if not application.bank_transactions_override:
        base_data = _generate_for_app(application, session)
        if base_data is None:
            raise HTTPException(
                422,
                "Cannot append: missing required application fields "
                "(salary_rub, submission_date, contract_number, "
                "contract_sign_date, company_id)"
            )
        application.bank_transactions_override = serialize_for_storage(base_data)
        session.add(application)
        session.flush()
        session.refresh(application)

    data = _append_for_app(application, session, payload.period_from, payload.period_to)
    if data is None:
        raise HTTPException(
            422,
            "Cannot append: missing required application fields or broken override"
        )

    application.bank_transactions_override = serialize_for_storage(data)
    session.add(application)
    session.flush()
    session.refresh(application)

    return _build_response(application, session)


@router.get("/{app_id}/bank-transactions", response_model=BankStatementResponse)
def get_bank_transactions(
    app_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> BankStatementResponse:
    """
    Получить текущий список транзакций.

    Если в БД ничего не сохранено — генерирует и возвращает черновик
    (но НЕ сохраняет в БД — это только превью).
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    return _build_response(application, session)


@router.put("/{app_id}/bank-transactions", response_model=BankStatementResponse)
def replace_bank_transactions(
    app_id: int,
    payload: BankStatementData,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> BankStatementResponse:
    """
    Полностью заменить список транзакций. Используется когда менеджер
    отредактировал данные в UI и хочет их сохранить.

    Передавайте список целиком — частичное обновление не поддерживается
    (для надёжности — проще передать всё, чем угадывать что менялось).
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    # Конвертируем Pydantic-модели в простые dict для serialize_for_storage
    transactions = [
        {
            "transaction_date": t.transaction_date,
            "code": t.code,
            "description": t.description,
            "amount": t.amount,
            "currency": t.currency,
        }
        for t in payload.transactions
    ]

    data_to_save = {
        "period_start": payload.period_start,
        "period_end": payload.period_end,
        "opening_balance": payload.opening_balance,
        "transactions": transactions,
    }

    # Используем serialize_for_storage для конвертации в JSON-friendly формат
    application.bank_transactions_override = {
        "period_start": payload.period_start.isoformat(),
        "period_end": payload.period_end.isoformat(),
        "opening_balance": str(payload.opening_balance),
        "transactions": [
            {
                "transaction_date": t["transaction_date"].isoformat(),
                "code": t["code"],
                "description": t["description"],
                "amount": str(t["amount"]),
                "currency": t["currency"],
            }
            for t in transactions
        ],
    }
    session.add(application)
    session.flush()
    session.refresh(application)

    return _build_response(application, session)
