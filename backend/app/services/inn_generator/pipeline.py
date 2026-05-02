"""
Pack 17.2 — pipeline автогенерации ИНН самозанятого.

Orchestrator всех шагов:
1. region_picker → определяет регион (KLADR)
2. rmsp_client → запрашивает 1-3 страницы реестра, собирает кандидатов
3. Фильтрует уже использованные ИНН (по нашей БД applicant.inn)
4. Генерирует адрес если его нет
5. Возвращает результат

Архитектурное решение: НЕ запрашиваем NPD на этапе suggest — это требует 31 сек
ожидания (rate limit). Менеджер сам нажмёт кнопку «Проверить статус» в UI
если захочет верификации. Но `dt_support_begin` из RMSP уже дает приближённую
дату начала статуса — этого достаточно для документов.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlmodel import Session, select

from app.models import Applicant, Application, Company, Region

from .rmsp_client import RmspClient, RmspError, RmspCandidate
from .kladr_address_gen import generate_address, GeneratedAddress, is_known_region
from .region_picker import pick_region, RegionPickResult


log = logging.getLogger(__name__)


@dataclass
class InnSuggestion:
    """
    Результат подбора ИНН для заявителя.
    Возвращается из pipeline.suggest_inn_for_applicant().
    """
    inn: str                              # 12-значный ИНН
    full_name_rmsp: str                   # ФИО самозанятого как в реестре (для отладки)
    region_code: str                      # 2-значный код региона ИНН ("23", "77", и т.д.)

    # Адрес — либо существующий, либо сгенерированный
    home_address: str                     # полный адрес
    address_was_generated: bool           # True если мы сгенерировали, False если был у applicant

    # Дата начала статуса НПД (приближённая)
    estimated_npd_start: Optional[date]   # приближённая, из RMSP dt_support_begin
    estimated_npd_start_raw: Optional[str]  # как пришло из ФНС: "DD.MM.YYYY"

    # KLADR региона который мы выбрали для address generation
    target_kladr_code: str                # KLADR региона (наш выбор, может отличаться от ИНН)
    target_region_name: str               # название региона ("Сочи", "Москва")

    # Метаданные о принятии решения
    region_pick_source: str               # 'home_address', 'sign_city', 'company', 'diaspora', 'fallback'
    region_pick_explanation: str          # для UI: «Использую регион Заказчика → Сочи»

    # Сырые данные для отладки
    rmsp_raw: dict


class InnPipelineError(Exception):
    """Ошибки pipeline."""

    pass


async def suggest_inn_for_applicant(
    session: Session,
    applicant: Applicant,
    application: Optional[Application] = None,
    company: Optional[Company] = None,
    *,
    rmsp_max_pages: int = 5,
    rmsp_page_size: int = 100,
    skip_used_inns: bool = True,
    rng: Optional[random.Random] = None,
) -> InnSuggestion:
    """
    Главная функция: подбирает ИНН + адрес + дату для заявителя.

    Args:
        session: SQLModel сессия (для запроса used_inns + Region)
        applicant: заявитель
        application: заявка (для contract_sign_city)
        company: компания-Заказчик (для legal_address)
        rmsp_max_pages: сколько страниц RMSP пробивать (1 страница ~100 кандидатов)
        rmsp_page_size: 100 — максимум для одной страницы
        skip_used_inns: исключать ИНН уже используемые в БД
        rng: для тестов

    Returns:
        InnSuggestion с готовыми данными для UI/сохранения

    Raises:
        InnPipelineError: если не удалось найти подходящего кандидата
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

    # === Шаг 2: Запрос RMSP — берём ИНН любого активного самозанятого ===
    # ВАЖНО: strict_region_filter=False, потому что:
    # - ФНС не применяет KLADR-фильтр через программный API
    # - Для нашей задачи РЕГИОН ИНН не критичен (адрес генерируется отдельно)
    # - Главное — ИНН реальный и активный
    candidates = await _fetch_rmsp_candidates(
        kladr_code=region_result.region.kladr_code,
        max_candidates=rmsp_page_size * 2,
        max_pages=rmsp_max_pages,
        page_size=rmsp_page_size,
    )

    if not candidates:
        raise InnPipelineError(
            "RMSP не вернул ни одного активного самозанятого. "
            "Возможна проблема с подключением к ФНС."
        )

    # === Шаг 3: Фильтр уже использованных ИНН ===
    if skip_used_inns:
        used_inns = _get_used_inns(session)
        candidates = [c for c in candidates if c.inn not in used_inns]

        if not candidates:
            raise InnPipelineError(
                f"Все полученные ИНН ({len(used_inns)} использованных в БД) "
                f"уже использованы. Попробуй увеличить max_pages."
            )

        log.info(f"[pipeline] After skip_used_inns: {len(candidates)} candidates left")

    # === Шаг 4: Выбор кандидата ===
    # Стратегия: берём СТАРЫЙ (по ИНН — старые ИНН были выданы раньше).
    # Сортируем по ИНН возрастающе и берём первого.
    # Это статистически выбирает «зрелого» самозанятого (уже на НПД давно).
    candidates_sorted = sorted(candidates, key=lambda c: c.inn)
    chosen = candidates_sorted[0]

    log.info(
        f"[pipeline] Chosen candidate: {chosen.inn} {chosen.full_name} "
        f"(region {chosen.region_code}, npd_start≈{chosen.estimated_npd_start})"
    )

    # === Шаг 5: Адрес ===
    home_address: str
    address_was_generated: bool

    if region_result.use_existing_address and applicant.home_address:
        home_address = applicant.home_address.strip()
        address_was_generated = False
        log.info(f"[pipeline] Using existing address: {home_address}")
    else:
        # Генерируем под выбранный регион
        if not is_known_region(region_result.region.kladr_code):
            raise InnPipelineError(
                f"Регион {region_result.region.kladr_code} ({region_result.region.name}) "
                f"не поддерживается address-generator'ом. "
                f"Известны только 10 базовых регионов."
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


async def _fetch_rmsp_candidates(
    kladr_code: str,
    max_candidates: int,
    max_pages: int,
    page_size: int,
) -> List[RmspCandidate]:
    """
    Запрашивает RMSP с несколькими страницами.

    Note: strict_region_filter=False потому что ФНС всё равно не применяет
    KLADR-фильтр через программный API. Регион ИНН не критичен — он не
    отображается клиенту/консулату, и адрес мы генерируем отдельно.
    """
    async with RmspClient() as client:
        try:
            return await client.search_multiple_pages(
                kladr_code=kladr_code,
                max_candidates=max_candidates,
                page_size=page_size,
                max_pages=max_pages,
                strict_region_filter=False,
                delay_between_pages=0.5,
            )
        except RmspError as e:
            raise InnPipelineError(f"RMSP error: {e}") from e


def _get_used_inns(session: Session) -> set[str]:
    """
    Возвращает множество ИНН которые уже используются в applicant.inn.
    Это предотвращает повторное использование одного ИНН для разных клиентов.
    """
    statement = select(Applicant.inn).where(Applicant.inn != None)  # noqa: E711
    rows = session.exec(statement).all()
    return {inn for inn in rows if inn}


def _parse_npd_start_date(
    candidate: RmspCandidate,
) -> tuple[Optional[date], Optional[str]]:
    """
    Парсит самую раннюю из дат RMSP в `date`.
    Возвращает (parsed_date, raw_string).

    RMSP даёт даты в формате "DD.MM.YYYY HH:MM:SS" (например "02.12.2025 00:00:00").
    """
    raw = candidate.estimated_npd_start
    if not raw:
        return None, None

    # Берём только дату (до пробела)
    date_part = raw.split(" ", 1)[0].strip()

    try:
        # "02.12.2025" → date(2025, 12, 2)
        d, m, y = date_part.split(".")
        return date(int(y), int(m), int(d)), raw
    except (ValueError, AttributeError) as e:
        log.warning(f"[pipeline] Bad date format from RMSP: {raw!r}, error: {e}")
        return None, raw
