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
from app.models import Application, Company
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
    )


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
