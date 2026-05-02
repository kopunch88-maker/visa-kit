"""
Pack 17.2.1 — pipeline автогенерации ИНН с консервативной нагрузкой на ФНС.

ИЗМЕНЕНИЯ vs 17.2:
- max_pages по умолчанию = 1 (было 5)
- page_size = 100 (одной страницы достаточно — 100 кандидатов хватит после фильтра used_inns)
- Если первый запрос упал ConnectError — пробуем 1 раз через 5 секунд
- В случае всех проблем возвращаем подробную диагностику

Логика прежняя: regions → rmsp → фильтр used_inns → выбор «старого» ИНН →
адрес (существующий или сгенерированный) → дата НПД из RMSP.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlmodel import Session, select

from app.models import Applicant, Application, Company

from .rmsp_client import RmspClient, RmspError, RmspCandidate
from .kladr_address_gen import generate_address, GeneratedAddress, is_known_region
from .region_picker import pick_region, RegionPickResult


log = logging.getLogger(__name__)


@dataclass
class InnSuggestion:
    inn: str
    full_name_rmsp: str
    region_code: str

    home_address: str
    address_was_generated: bool

    estimated_npd_start: Optional[date]
    estimated_npd_start_raw: Optional[str]

    target_kladr_code: str
    target_region_name: str

    region_pick_source: str
    region_pick_explanation: str

    rmsp_raw: dict


class InnPipelineError(Exception):
    pass


async def suggest_inn_for_applicant(
    session: Session,
    applicant: Applicant,
    application: Optional[Application] = None,
    company: Optional[Company] = None,
    *,
    rmsp_max_pages: int = 1,           # 17.2.1: было 5 — снижено для меньшей нагрузки на ФНС
    rmsp_page_size: int = 100,
    skip_used_inns: bool = True,
    rng: Optional[random.Random] = None,
) -> InnSuggestion:
    """
    Главная функция: подбирает ИНН + адрес + дату для заявителя.

    17.2.1: уменьшена нагрузка на ФНС (1 страница вместо 5)
    + retry на сетевых ошибках.
    """
    if rng is None:
        rng = random.Random()

    # === Шаг 1: Выбор региона ===
    region_result: RegionPickResult = pick_region(
        session=session,
        applicant=applicant,
        application=application,
        company=company,
        rng=rng,
    )

    log.info(
        f"[pipeline] Region picked: {region_result.region.name} "
        f"(source={region_result.source}, kladr={region_result.region.kladr_code})"
    )

    # === Шаг 2: Запрос RMSP с retry ===
    candidates = await _fetch_rmsp_candidates_with_retry(
        kladr_code=region_result.region.kladr_code,
        max_pages=rmsp_max_pages,
        page_size=rmsp_page_size,
    )

    if not candidates:
        raise InnPipelineError(
            "RMSP не вернул ни одного активного самозанятого. "
            "Возможно ФНС временно ограничивает запросы."
        )

    # === Шаг 3: Фильтр уже использованных ИНН ===
    if skip_used_inns:
        used_inns = _get_used_inns(session)
        before = len(candidates)
        candidates = [c for c in candidates if c.inn not in used_inns]

        if not candidates:
            raise InnPipelineError(
                f"Все {before} полученных ИНН уже использованы в БД "
                f"({len(used_inns)} зарезервированных). "
                f"Подождите минуту и попробуйте ещё раз — "
                f"тогда ФНС вернёт другую выборку."
            )

        log.info(
            f"[pipeline] After skip_used_inns: {len(candidates)} candidates "
            f"(filtered out {before - len(candidates)} used)"
        )

    # === Шаг 4: Выбор кандидата ===
    # Берём «старого» — сортируем по ИНН (старые ИНН выданы раньше)
    candidates_sorted = sorted(candidates, key=lambda c: c.inn)
    chosen = candidates_sorted[0]

    log.info(
        f"[pipeline] Chosen: {chosen.inn} {chosen.full_name} "
        f"(region {chosen.region_code}, npd_start≈{chosen.estimated_npd_start})"
    )

    # === Шаг 5: Адрес ===
    home_address: str
    address_was_generated: bool

    if region_result.use_existing_address and applicant.home_address:
        home_address = applicant.home_address.strip()
        address_was_generated = False
        log.info(f"[pipeline] Using existing address")
    else:
        if not is_known_region(region_result.region.kladr_code):
            raise InnPipelineError(
                f"Регион {region_result.region.kladr_code} ({region_result.region.name}) "
                f"не поддерживается address-generator'ом."
            )

        generated: GeneratedAddress = generate_address(
            kladr_code=region_result.region.kladr_code,
            rng=rng,
        )
        home_address = generated.full
        address_was_generated = True
        log.info(f"[pipeline] Generated address: {home_address}")

    # === Шаг 6: Дата начала НПД ===
    estimated_npd_start, estimated_raw = _parse_npd_start_date(chosen)

    return InnSuggestion(
        inn=chosen.inn,
        full_name_rmsp=chosen.full_name,
        region_code=chosen.region_code,
        home_address=home_address,
        address_was_generated=address_was_generated,
        estimated_npd_start=estimated_npd_start,
        estimated_npd_start_raw=estimated_raw,
        target_kladr_code=region_result.region.kladr_code,
        target_region_name=region_result.region.name,
        region_pick_source=region_result.source,
        region_pick_explanation=region_result.explanation,
        rmsp_raw=chosen.raw,
    )


async def _fetch_rmsp_candidates_with_retry(
    kladr_code: str,
    max_pages: int,
    page_size: int,
    max_retries: int = 2,
    initial_delay: float = 5.0,
) -> List[RmspCandidate]:
    """
    Запрашивает RMSP с retry при сетевых ошибках.

    17.2.1: при ConnectError/Timeout ждём initial_delay секунд (увеличиваем
    в 2 раза с каждой попыткой) и повторяем. До max_retries попыток.

    Это нужно потому что у ФНС агрессивный burst-rate-limit:
    несколько запросов подряд за секунды → connection reset на 1-5 минут.
    """
    last_error: Optional[Exception] = None
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            async with RmspClient() as client:
                if max_pages <= 1:
                    # Один запрос — самое щадящее для ФНС
                    return await client.search_self_employed(
                        kladr_code=kladr_code,
                        page=1,
                        page_size=page_size,
                        strict_region_filter=False,
                    )
                else:
                    return await client.search_multiple_pages(
                        kladr_code=kladr_code,
                        max_candidates=page_size,
                        page_size=page_size,
                        max_pages=max_pages,
                        strict_region_filter=False,
                        delay_between_pages=3.0,  # увеличено для безопасности
                    )
        except RmspError as e:
            last_error = e
            error_str = str(e) or "(empty)"
            log.warning(
                f"[pipeline] RMSP error attempt {attempt+1}/{max_retries+1}: {error_str}"
            )

            if attempt < max_retries:
                log.info(f"[pipeline] Waiting {delay:.0f}s before retry...")
                await asyncio.sleep(delay)
                delay *= 2  # exponential backoff

    raise InnPipelineError(
        f"RMSP недоступен после {max_retries + 1} попыток. "
        f"Последняя ошибка: {last_error}. "
        f"ФНС возможно временно ограничивает запросы — попробуй через 5-10 минут."
    )


def _get_used_inns(session: Session) -> set[str]:
    """Множество ИНН в applicant.inn (исключаем повторное использование)."""
    statement = select(Applicant.inn).where(Applicant.inn != None)  # noqa: E711
    rows = session.exec(statement).all()
    return {inn for inn in rows if inn}


def _parse_npd_start_date(
    candidate: RmspCandidate,
) -> tuple[Optional[date], Optional[str]]:
    """
    Парсит самую раннюю из дат RMSP в `date`.
    RMSP даёт даты в формате "DD.MM.YYYY HH:MM:SS".
    """
    raw = candidate.estimated_npd_start
    if not raw:
        return None, None

    date_part = raw.split(" ", 1)[0].strip()

    try:
        d, m, y = date_part.split(".")
        return date(int(y), int(m), int(d)), raw
    except (ValueError, AttributeError) as e:
        log.warning(f"[pipeline] Bad date format from RMSP: {raw!r}, error: {e}")
        return None, raw
