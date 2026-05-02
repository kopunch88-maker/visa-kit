"""
Pack 17.1.2 — HTTP клиент к публичному реестру МСП ФНС.

ИСТОРИЯ ИЗМЕНЕНИЙ:
- 17.1: первая версия. ФНС возвращает кандидатов из всех регионов
        (фильтр по KLADR не применяется при программном запросе).
- 17.1.1: попытался передавать kladr в URL/body. ФНС возвращает HTTP 5xx —
          схема запроса оказалась неприемлемой.
- 17.1.2 (текущая): возвращаемся к РАБОЧЕМУ формату запроса 17.1
          + оставляем только post-filter по region_code на нашей стороне
          + по умолчанию делаем multipage чтобы набрать достаточно
            кандидатов из нужного региона.

Алгоритм работы:
1. GET https://rmsp-pp.nalog.ru/search.html?sk=SZ&kladr={KLADR}
   → JSESSIONID

2. POST https://rmsp-pp.nalog.ru/search-proc.json?m=Support
   form-data: page, pageSize, query, sc, sk, rp, _v
   → возвращает JSON с самозанятыми (из всех регионов России)

3. POST-FILTER на нашей стороне: оставляем только субъекты где
   subject_region == kladr_code[:2] (первые 2 цифры).
   Например для Сочи (kladr=2300000700000) принимаем только region_code="23".

4. Если на одной странице мало местных — пробиваем пагинацию (multipage).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set

import httpx

log = logging.getLogger(__name__)


RMSP_BASE_URL = "https://rmsp-pp.nalog.ru"
RMSP_SEARCH_HTML = f"{RMSP_BASE_URL}/search.html"
RMSP_SEARCH_PROC = f"{RMSP_BASE_URL}/search-proc.json"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

# Pack 17.2.3: увеличены таймауты — ФНС иногда тянет TCP-handshake до 30 сек
# с Railway IP. Особенно после burst-rate-limit она отвечает медленно.
HTTP_TIMEOUT = httpx.Timeout(60.0, connect=30.0)

# Retry parameters внутри _ensure_session_for_kladr
SESSION_INIT_RETRIES = 2
SESSION_INIT_RETRY_DELAY = 8.0  # сек


class RmspError(Exception):
    pass


@dataclass
class RmspCandidate:
    inn: str
    full_name: str
    nptype: str
    category: int
    region_code: str
    ogrn: Optional[str] = None

    # Pack 17.1.1: даты из RMSP — для оценки даты начала НПД
    dt_create: Optional[str] = None
    dt_support_begin: Optional[str] = None
    dt_support_period: Optional[str] = None

    raw: dict = field(default_factory=dict)

    @property
    def is_self_employed(self) -> bool:
        return (
            self.nptype == "SZ"
            and self.category == 4
            and not self.ogrn
        )

    @property
    def parts(self) -> tuple[str, str, str]:
        words = self.full_name.split()
        last = words[0] if len(words) > 0 else ""
        first = words[1] if len(words) > 1 else ""
        middle = words[2] if len(words) > 2 else ""
        return last, first, middle

    @property
    def estimated_npd_start(self) -> Optional[str]:
        """
        Самая ранняя из доступных дат RMSP — приближённая дата начала НПД.
        Это нижняя граница: «человек ТОЧНО был самозанятым на эту дату».
        """
        return (
            self.dt_support_begin
            or self.dt_support_period
            or self.dt_create
        )


class RmspClient:
    """
    Асинхронный клиент к реестру самозанятых ФНС.

    Использование:
        async with RmspClient() as client:
            candidates = await client.search_self_employed(
                kladr_code="2300000700000",
                page_size=100,
            )
    """

    def __init__(
        self,
        timeout: httpx.Timeout = HTTP_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self._timeout = timeout
        self._user_agent = user_agent
        self._client: Optional[httpx.AsyncClient] = None
        self._session_kladr: Optional[str] = None

    async def __aenter__(self) -> "RmspClient":
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self._user_agent,
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_session_for_kladr(self, kladr_code: str) -> None:
        """
        GET search.html для получения JSESSIONID + регистрации фильтра в session.

        Pack 17.2.3: добавлен retry с exponential backoff на ConnectTimeout/ConnectError —
        ФНС иногда не отвечает на TCP-handshake с Railway IP с первого раза.
        """
        if self._client is None:
            raise RmspError("RmspClient не инициализирован — используй `async with`")

        if self._session_kladr == kladr_code:
            return

        params = {"sk": "SZ", "kladr": kladr_code}
        last_error: Optional[Exception] = None
        delay = SESSION_INIT_RETRY_DELAY

        for attempt in range(SESSION_INIT_RETRIES + 1):
            log.info(
                f"[rmsp] GET search.html sk=SZ kladr={kladr_code} "
                f"(attempt {attempt + 1}/{SESSION_INIT_RETRIES + 1})"
            )
            try:
                response = await self._client.get(RMSP_SEARCH_HTML, params=params)
                response.raise_for_status()
                self._session_kladr = kladr_code
                log.debug(
                    f"[rmsp] Session ready, cookies={dict(self._client.cookies)}"
                )
                return
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                error_class = e.__class__.__name__
                error_msg = str(e) or "(empty)"
                log.warning(
                    f"[rmsp] Session init {error_class} on attempt {attempt + 1}: "
                    f"{error_msg}"
                )

                if attempt < SESSION_INIT_RETRIES:
                    log.info(f"[rmsp] Waiting {delay:.0f}s before retry...")
                    await asyncio.sleep(delay)
                    delay *= 2
            except httpx.HTTPError as e:
                # 4xx/5xx — не имеет смысла retry, сразу возвращаем ошибку
                raise RmspError(
                    f"Failed to initialize rmsp session (HTTP error): {e}"
                ) from e

        raise RmspError(
            f"Failed to initialize rmsp session after "
            f"{SESSION_INIT_RETRIES + 1} attempts: {last_error}"
        ) from last_error

    async def search_self_employed(
        self,
        kladr_code: str,
        page: int = 1,
        page_size: int = 100,
        query: str = "",
        strict_region_filter: bool = True,
    ) -> List[RmspCandidate]:
        """
        Возвращает список самозанятых.

        ФНС не применяет фильтр по KLADR при программном запросе — поэтому:
        - strict_region_filter=True (default): пост-фильтр на нашей стороне
          по subject_region == kladr_code[:2]
        - strict_region_filter=False: возвращаем что вернула ФНС как есть
          (для отладки)

        Args:
            kladr_code: 13-значный KLADR код (используется для определения
                ожидаемого region_code и для Referer)
            page, page_size, query: параметры пагинации
            strict_region_filter: фильтр по региону на нашей стороне
        """
        if self._client is None:
            raise RmspError("RmspClient не инициализирован — используй `async with`")

        if not kladr_code or len(kladr_code) != 13 or not kladr_code.isdigit():
            raise RmspError(
                f"kladr_code должен быть 13 цифр, получено: {kladr_code!r}"
            )

        if page_size not in (10, 20, 50, 100):
            raise RmspError(
                f"page_size должен быть 10/20/50/100, получено: {page_size}"
            )

        await self._ensure_session_for_kladr(kladr_code)

        # Pack 17.1.2: возвращаем формат запроса 17.1 (РАБОЧИЙ — kladr только в Referer)
        # ФНС не понравились kladr в URL/body (вернула 5xx).
        url_params = {"m": "Support"}

        form_data = {
            "page": str(page),
            "pageSize": str(page_size),
            "query": query,
            "sc": "",
            "sk": "",       # пусто как в твоём cURL
            "rp": "",
            "_v": "",
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": RMSP_BASE_URL,
            "Referer": f"{RMSP_SEARCH_HTML}?sk=SZ&kladr={kladr_code}",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        log.info(
            f"[rmsp] POST search-proc kladr={kladr_code}, page={page}, "
            f"pageSize={page_size}"
        )

        try:
            response = await self._client.post(
                RMSP_SEARCH_PROC,
                params=url_params,
                data=form_data,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            raise RmspError(f"rmsp HTTP error: {e}") from e
        except ValueError as e:
            raise RmspError(f"rmsp returned non-JSON: {e}") from e

        if "data" not in data:
            log.warning(f"[rmsp] Unexpected response shape: keys={list(data.keys())}")
            raise RmspError("rmsp response missing 'data' field")

        rows = data.get("data", [])
        total = data.get("rowCount", 0)
        log.info(f"[rmsp] Got {len(rows)} rows (total: {total})")

        # Парсинг + фильтрация + дедупликация + post-filter по региону
        candidates: List[RmspCandidate] = []
        seen_inns: Set[str] = set()
        expected_region = kladr_code[:2]
        wrong_region_count = 0
        not_self_employed_count = 0

        for row in rows:
            inn = row.get("subject_inn")
            if not inn or inn in seen_inns:
                continue

            candidate = RmspCandidate(
                inn=inn,
                full_name=row.get("subject_name", "").strip(),
                nptype=row.get("subject_nptype", ""),
                category=row.get("subject_category", 0),
                region_code=row.get("subject_region", ""),
                ogrn=row.get("subject_ogrn"),
                dt_create=row.get("dt_create"),
                dt_support_begin=row.get("dt_support_begin"),
                dt_support_period=row.get("dt_support_period"),
                raw=row,
            )

            if not candidate.is_self_employed:
                not_self_employed_count += 1
                continue

            if strict_region_filter and candidate.region_code != expected_region:
                wrong_region_count += 1
                continue

            candidates.append(candidate)
            seen_inns.add(inn)

        log.info(
            f"[rmsp] Filtered: {wrong_region_count} wrong region, "
            f"{not_self_employed_count} not SZ. "
            f"Returning {len(candidates)} candidates from region {expected_region}"
        )
        return candidates

    async def search_multiple_pages(
        self,
        kladr_code: str,
        max_candidates: int = 50,
        page_size: int = 100,
        max_pages: int = 10,
        delay_between_pages: float = 0.5,
        strict_region_filter: bool = True,
    ) -> List[RmspCandidate]:
        """
        Запрашивает несколько страниц подряд пока не наберём max_candidates.
        Особенно полезно когда ФНС не применяет KLADR-фильтр и мы пробиваем
        страницы пока не наберём достаточно из нужного региона.
        """
        all_candidates: List[RmspCandidate] = []
        seen_inns: Set[str] = set()
        empty_pages_in_row = 0

        for page in range(1, max_pages + 1):
            page_candidates = await self.search_self_employed(
                kladr_code=kladr_code,
                page=page,
                page_size=page_size,
                strict_region_filter=strict_region_filter,
            )

            new_count = 0
            for c in page_candidates:
                if c.inn not in seen_inns:
                    all_candidates.append(c)
                    seen_inns.add(c.inn)
                    new_count += 1

            log.info(
                f"[rmsp] Page {page}: +{new_count} new "
                f"(total: {len(all_candidates)}/{max_candidates})"
            )

            if len(all_candidates) >= max_candidates:
                break

            # Если 3 страницы подряд без новых из нужного региона — стоп
            if new_count == 0:
                empty_pages_in_row += 1
                if empty_pages_in_row >= 3:
                    log.info(
                        f"[rmsp] {empty_pages_in_row} pages without new candidates, "
                        f"stopping"
                    )
                    break
            else:
                empty_pages_in_row = 0

            if page < max_pages:
                await asyncio.sleep(delay_between_pages)

        return all_candidates[:max_candidates]
