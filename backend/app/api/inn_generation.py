"""
Pack 17 / Pack 18.1 / Pack 18.2 — endpoints автогенерации ИНН самозанятого.

Pack 18.1 изменения (без изменений):
- В response /inn-suggest добавлены поля fallback_used / requested_region_name /
  requested_region_code / fallback_reason / region_code — фронт показывает
  warning менеджеру при сдвиге региона.
- Удалён query-параметр filter_by_region (всегда фильтруем по региону, fallback
  гарантирует что кандидат найдётся).
- В /inn-accept проставляется used_at=utcnow() помимо is_used=True.

Pack 18.2 изменения (текущая версия):
- /inn-accept теперь ASYNC (def → async def).
- Перед сохранением проверяет ИНН через ФНС API
  (statusnpd.nalog.ru/api/v1/tracker/taxpayer_status).
- Если ФНС вернул status=False → помечаем кандидат is_invalid=True в БД и
  возвращаем 409 «Кандидат потерял статус НПД, попробуйте подобрать другого».
  Менеджер нажимает ✨ ИНН ещё раз.
- Если ФНС timeout/недоступен → мягкий пропуск: выдаём ИНН без проверки,
  в response добавляются npd_check_status=skipped + manual_check_url для
  ручной проверки менеджером.
- Если ФНС вернул status=True → проставляем last_npd_check_at=now() и
  продолжаем как раньше.

Pack 18.8 изменения (текущая версия):
- Новый endpoint POST /admin/applicants/{id}/regen-address — генерирует новый
  случайный адрес из того же города куда привязан ИНН (applicant.inn_kladr_code).
  Не пишет в БД, только возвращает {home_address, kladr_code}. Запись через
  обычный PATCH /applicants/{id} (UI «Сохранить»).
- Используется кнопкой ✨ рядом с полем «Адрес проживания» в ApplicantDrawer.
  Менеджер может перегенерировать адрес сколько угодно раз — например, если
  клиент сказал что в этом районе не живёт.

Rate limit ФНС (2 req/min) реализован в NpdStatusChecker через class-level
asyncio.Lock + 31 секундный sleep между запросами.

⚠️ Замечание про async:
До Pack 18.2 endpoint был синхронным (def inn_accept). Теперь async, потому
что NpdStatusChecker — асинхронный httpx-клиент. FastAPI поддерживает оба,
переход прозрачный для вызывающего кода (фронт ничего не замечает).
"""

from __future__ import annotations

import logging
import random  # Pack 18.8: для regen-address
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import (
    Applicant,
    Application,
    Company,
    SelfEmployedRegistry,
)
from app.services.inn_generator.kladr_address_gen import (
    KNOWN_REGIONS,         # Pack 18.8: для валидации kladr_code в regen-address
    generate_address,      # Pack 18.8: для regen-address
)
from app.services.inn_generator.npd_status import (
    NpdStatusChecker,
    NpdStatusError,
)
from app.services.inn_generator.pipeline import (
    InnSuggestion,
    suggest_inn_for_applicant,
)
from .dependencies import require_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/applicants", tags=["inn-generation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InnSuggestResponse(BaseModel):
    """
    Ответ /inn-suggest. Старые поля (Pack 17) сохранены, добавлены новые
    region_code и fallback_* поля (Pack 18.1).
    """

    inn: str
    full_name: str
    home_address: str
    kladr_code: str
    region_name: str
    region_code: str  # NEW: 2-значный код субъекта ('77', '02', ...)
    inn_registration_date: date
    source: str

    # Pack 18.1: warning-поля
    fallback_used: bool = False
    requested_region_name: Optional[str] = None
    requested_region_code: Optional[str] = None
    fallback_reason: Optional[str] = None


class InnAcceptRequest(BaseModel):
    inn: str
    home_address: Optional[str] = None
    kladr_code: Optional[str] = None
    inn_registration_date: Optional[date] = None
    inn_source: Optional[str] = "registry_snrip"


class InnAcceptResponse(BaseModel):
    """
    Pack 18.2: расширен полями npd_check_status и manual_check_url.

    npd_check_status:
      'confirmed' — ФНС подтвердил что ИНН валиден на сегодня
      'skipped_fns_unavailable' — ФНС недоступен/timeout, ИНН выдан без проверки
      'skipped_already_checked' — ИНН проверяли недавно, кэш использован

    manual_check_url: если skipped — даём менеджеру ссылку для ручной проверки
    """
    ok: bool
    applicant_id: int
    inn: str
    npd_check_status: Literal[
        "confirmed",
        "skipped_fns_unavailable",
        "skipped_already_checked",
    ] = "confirmed"
    manual_check_url: Optional[str] = None
    npd_check_message: Optional[str] = None  # человекочитаемое описание


class RegenAddressRequest(BaseModel):
    """
    Pack 18.8: запрос на перегенерацию адреса.
    Все поля опциональны — по умолчанию берётся applicant.inn_kladr_code.
    """
    # Если задан — используется вместо applicant.inn_kladr_code (override).
    # Полезно если в будущем добавим выбор региона из выпадающего списка.
    kladr_code: Optional[str] = None


class RegenAddressResponse(BaseModel):
    """
    Pack 18.8: новый сгенерированный адрес. НЕ записывается в БД —
    запись через PATCH /applicants/{id} (UI «Сохранить»).
    """
    home_address: str
    kladr_code: str  # KLADR города из которого сгенерирован адрес


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_application_for_applicant(
    session: Session, applicant_id: int
) -> Optional[Application]:
    """
    Pack 17.3 defensive fix: Applicant НЕ имеет поля application_id, поэтому ищем
    обратным SELECT'ом по Application.applicant_id.
    Берём последнюю заявку (ORDER BY id DESC) — обычно одна, но если их несколько
    хотим самую свежую.
    """
    stmt = (
        select(Application)
        .where(Application.applicant_id == applicant_id)
        .order_by(Application.id.desc())  # type: ignore[union-attr]
    )
    return session.exec(stmt).first()


def _get_company_for_application(
    session: Session, application: Optional[Application]
) -> Optional[Company]:
    if not application or not application.company_id:
        return None
    return session.get(Company, application.company_id)


def _make_manual_check_url(inn: str) -> str:
    """
    Pack 18.2: URL для ручной проверки менеджером через сайт ФНС.
    Это публичная страница где можно ввести ИНН и дату.
    """
    return f"https://npd.nalog.ru/check-status/?inn={inn}"


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/inn-suggest
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/inn-suggest",
    response_model=InnSuggestResponse,
    summary="Подобрать ИНН самозанятого для заявителя",
)
def inn_suggest(
    applicant_id: int,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> InnSuggestResponse:
    """
    Pack 18.1: подбор ИНН с tier-fallback.
    Параметр filter_by_region удалён — всегда фильтруем по региону, гарантия
    результата обеспечивается fallback'ом на диаспоры → Москву.

    Pack 18.2: НЕ делаем проверку через ФНС здесь (rate limit 2 req/min,
    держать менеджера 31+ сек на каждом ✨ — неюзабельно). Проверка
    выполняется в /inn-accept когда менеджер уже принял решение.

    Кандидаты с is_invalid=True (помеченные предыдущей проверкой как
    «потерял статус НПД») здесь НЕ исключаются — фильтрация идёт только
    по is_used. Это компромисс: при здоровой БД is_invalid очень редок,
    стоимость отдельного фильтра не оправдана. Если попадётся invalid,
    inn-accept его поймает.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    application = _find_application_for_applicant(session, applicant_id)
    company = _get_company_for_application(session, application)

    log.info(
        "inn-suggest: applicant_id=%s nationality=%s home_addr=%r contract_city=%r company_legal=%r",
        applicant_id,
        applicant.nationality,
        applicant.home_address,
        application.contract_sign_city if application else None,
        company.legal_address if company else None,
    )

    try:
        suggestion: InnSuggestion = suggest_inn_for_applicant(
            session,
            applicant=applicant,
            application=application,
            company=company,
        )
    except RuntimeError as e:
        # Реестр исчерпан или другая нерешаемая проблема
        log.error("inn-suggest: pipeline failure for applicant_id=%s: %s", applicant_id, e)
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # pragma: no cover
        log.exception("inn-suggest: unexpected error")
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")

    return InnSuggestResponse(
        inn=suggestion.inn,
        full_name=suggestion.full_name,
        home_address=suggestion.home_address,
        kladr_code=suggestion.kladr_code,
        region_name=suggestion.region_name,
        region_code=suggestion.region_code,
        inn_registration_date=suggestion.inn_registration_date,
        source=suggestion.source,
        fallback_used=suggestion.fallback_used,
        requested_region_name=suggestion.requested_region_name,
        requested_region_code=suggestion.requested_region_code,
        fallback_reason=suggestion.fallback_reason,
    )


# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/inn-accept
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/inn-accept",
    response_model=InnAcceptResponse,
    summary="Принять ИНН: проверить через ФНС, сохранить в applicant + пометить is_used",
)
async def inn_accept(
    applicant_id: int,
    payload: InnAcceptRequest,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> InnAcceptResponse:
    """
    Pack 18.2: проверяет ИНН через ФНС API перед сохранением.

    Сценарии:
    1. ФНС подтвердил статус НПД (status=True):
       → сохраняем как раньше, npd_check_status=confirmed
    2. ФНС сообщил что не плательщик (status=False):
       → помечаем кандидат is_invalid=True в БД
       → возвращаем 409 «Кандидат потерял статус НПД, попробуйте подобрать
         другого». Менеджер жмёт ✨ ИНН ещё раз.
    3. ФНС timeout/недоступен:
       → мягкий пропуск, ИНН выдаётся БЕЗ проверки,
         npd_check_status=skipped_fns_unavailable + manual_check_url с
         ссылкой на сайт ФНС для ручной проверки

    Идемпотентно: если applicant.inn уже совпадает с переданным — просто
    200 OK (но если запись в реестре по какой-то причине is_used=False —
    починим и попробуем проверить статус если ещё не проверяли).
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    inn = (payload.inn or "").strip()
    if not inn:
        raise HTTPException(status_code=400, detail="inn is required")

    # ----- Идемпотентность -----
    if applicant.inn == inn:
        cand = session.get(SelfEmployedRegistry, inn)
        if cand and not cand.is_used:
            cand.is_used = True
            cand.used_by_applicant_id = applicant.id
            cand.used_at = datetime.utcnow()
            session.add(cand)
            session.commit()
            log.info("inn-accept: marked candidate inn=%s as used (idempotent fix)", inn)
        return InnAcceptResponse(
            ok=True,
            applicant_id=applicant.id,
            inn=inn,
            npd_check_status="skipped_already_checked",
            npd_check_message="ИНН уже принят ранее, повторная проверка не выполнялась",
        )

    # ----- Проверка кандидата в реестре -----
    cand = session.get(SelfEmployedRegistry, inn)
    if not cand:
        raise HTTPException(
            status_code=404,
            detail=f"INN {inn} not found in registry. Refuse to write unknown INN.",
        )
    if cand.is_used and cand.used_by_applicant_id != applicant.id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"INN {inn} уже использован заявителем id={cand.used_by_applicant_id}. "
                "Подберите другого кандидата."
            ),
        )

    # ----- Pack 18.2: проверка через ФНС API -----
    npd_check_status: Literal[
        "confirmed", "skipped_fns_unavailable", "skipped_already_checked"
    ] = "confirmed"
    manual_check_url: Optional[str] = None
    npd_check_message: Optional[str] = None

    log.info("inn-accept: starting NPD check for inn=%s via ФНС API", inn)
    try:
        async with NpdStatusChecker() as checker:
            result = await checker.check(inn=inn)

        if not result.is_active:
            # ФНС подтвердил: НЕ плательщик. Помечаем кандидат invalid и отказываем.
            cand.is_invalid = True
            cand.last_npd_check_at = datetime.utcnow()
            session.add(cand)
            session.commit()
            log.warning(
                "inn-accept: ФНС вернул status=False для inn=%s — помечен is_invalid=True. "
                "Сообщение ФНС: %s",
                inn,
                result.message,
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"ФНС сообщил что ИНН {inn} не является плательщиком НПД "
                    f"(сообщение: {result.message or 'нет деталей'}). "
                    "Кандидат помечен как недействительный. "
                    "Подберите другого через кнопку ✨ ИНН."
                ),
            )

        # ФНС подтвердил статус — успех
        cand.last_npd_check_at = datetime.utcnow()
        log.info(
            "inn-accept: ФНС подтвердил статус НПД для inn=%s (registration_date=%s)",
            inn,
            result.registration_date,
        )

    except NpdStatusError as e:
        # ФНС вернул ошибку (timeout, 5xx, нечитаемый ответ) — мягкий пропуск
        log.warning(
            "inn-accept: NpdStatusError для inn=%s, мягкий пропуск проверки: %s",
            inn,
            e,
        )
        npd_check_status = "skipped_fns_unavailable"
        manual_check_url = _make_manual_check_url(inn)
        npd_check_message = (
            f"ФНС API временно недоступен ({e!s}). "
            f"ИНН выдан без проверки. Рекомендуем проверить вручную на сайте ФНС: "
            f"{manual_check_url}"
        )

    except HTTPException:
        # 409 от блока с is_active=False — пробрасываем как есть
        raise

    except Exception as e:
        # Любая другая ошибка — тоже мягкий пропуск (защита менеджера от блокировки)
        log.exception("inn-accept: unexpected error during NPD check")
        npd_check_status = "skipped_fns_unavailable"
        manual_check_url = _make_manual_check_url(inn)
        npd_check_message = (
            f"Не удалось выполнить проверку статуса НПД ({type(e).__name__}: {e}). "
            f"ИНН выдан без проверки. Рекомендуем проверить вручную: {manual_check_url}"
        )

    # ----- Транзакционная запись -----
    applicant.inn = inn
    if payload.home_address:
        applicant.home_address = payload.home_address
    if payload.kladr_code:
        applicant.inn_kladr_code = payload.kladr_code
    if payload.inn_registration_date:
        applicant.inn_registration_date = payload.inn_registration_date
    if payload.inn_source:
        applicant.inn_source = payload.inn_source

    cand.is_used = True
    cand.used_by_applicant_id = applicant.id
    cand.used_at = datetime.utcnow()

    session.add(applicant)
    session.add(cand)
    session.commit()

    log.info(
        "inn-accept: SUCCESS applicant_id=%s inn=%s region_kladr=%s npd_check=%s",
        applicant_id,
        inn,
        payload.kladr_code,
        npd_check_status,
    )
    return InnAcceptResponse(
        ok=True,
        applicant_id=applicant.id,
        inn=inn,
        npd_check_status=npd_check_status,
        manual_check_url=manual_check_url,
        npd_check_message=npd_check_message,
    )

# ---------------------------------------------------------------------------
# POST /api/admin/applicants/{applicant_id}/regen-address
# Pack 18.8: перегенерировать случайный адрес в том же городе что у ИНН
# ---------------------------------------------------------------------------


@router.post(
    "/{applicant_id}/regen-address",
    response_model=RegenAddressResponse,
    summary="Сгенерировать новый случайный адрес из того же города куда привязан ИНН",
)
def regen_address(
    applicant_id: int,
    payload: RegenAddressRequest,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
) -> RegenAddressResponse:
    """
    Pack 18.8: помогает менеджеру выдать клиенту другой адрес без перевыдачи ИНН.

    Сценарии использования:
    - Клиент посмотрел сгенерированный адрес и сказал «я там не живу/не нравится»
    - Менеджер хочет посмотреть пару вариантов до принятия решения
    - Случайно сгенерировался адрес в неудобном районе

    Логика:
    1. По умолчанию берёт applicant.inn_kladr_code (KLADR города куда привязан ИНН).
    2. Если payload.kladr_code задан — используется он (override).
    3. Валидируем что KLADR есть в KNOWN_REGIONS (kladr_address_gen.py).
       Если нет — 400 с подсказкой что нужно перевыдать ИНН.
    4. Генерируем случайный адрес через generate_address(kladr_code, rng).
    5. Возвращаем {home_address, kladr_code}. В БД НЕ пишем — это сделает фронт
       через обычный PATCH /applicants/{id} когда менеджер нажмёт «Сохранить».

    Не требует ни обращений к ФНС, ни поиска ИНН в реестре — это «лёгкая»
    операция (~10ms). Можно дёргать сколько угодно раз.
    """
    applicant = session.get(Applicant, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    # 1. Определяем целевой KLADR
    kladr_code = (payload.kladr_code or applicant.inn_kladr_code or "").strip()

    if not kladr_code:
        raise HTTPException(
            status_code=400,
            detail=(
                "Невозможно сгенерировать адрес: у клиента не задан inn_kladr_code. "
                "Сначала выдайте ИНН через ✨ — KLADR региона запишется автоматически."
            ),
        )

    # 2. Валидируем KLADR — должен быть в KNOWN_REGIONS
    # (KNOWN_REGIONS — это dict[kladr_code, RegionTemplate] из kladr_address_gen.py)
    if kladr_code not in KNOWN_REGIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"KLADR {kladr_code} не поддерживается генератором адресов. "
                f"Возможно ИНН был выдан до Pack 18.6 — рекомендуем перевыдать через ✨ "
                f"чтобы записался актуальный KLADR из KNOWN_REGIONS."
            ),
        )

    # 3. Генерируем адрес
    rng = random.Random()  # Pack 18.8: без seed — каждый вызов даёт разный адрес
    address = generate_address(kladr_code, rng)

    log.info(
        "regen-address: applicant_id=%s kladr_code=%s generated %r",
        applicant_id, kladr_code, address,
    )

    return RegenAddressResponse(
        home_address=address,
        kladr_code=kladr_code,
    )
