"""
Pack 17.1.1 — HTTP клиент к публичному реестру МСП ФНС
(rmsp-pp.nalog.ru = Реестр Получателей Поддержки).

ИЗМЕНЕНИЯ ОТНОСИТЕЛЬНО Pack 17.1:
- KLADR теперь передаётся явно в URL POST `/search-proc.json` (?kladr=...&sk=SZ...)
  и в form body, и в Referer — для гарантии что фильтр применится.
- Добавлен post-filter по region_code из 2 первых цифр KLADR — на случай если
  ФНС всё равно вернёт записи из других регионов.
- Возвращаются даты dt_create/dt_support_begin/dt_support_period — из них берём
  «приближённую дату начала статуса НПД» (т.к. публичный NPD API не отдаёт точную).

Алгоритм работы:
1. GET https://rmsp-pp.nalog.ru/search.html?sk=SZ&kladr={KLADR}
   → JSESSIONID + сервер регистрирует session

2. POST https://rmsp-pp.nalog.ru/search-proc.json?m=Support&sk=SZ&kladr={KLADR}
   form-data: page, pageSize, query, sc, sk, rp, _v, kladr
   → возвращает JSON с самозанятыми

3. Post-filter: оставляем только записи где subject_region == kladr[:2]

ВАЖНО:
- Captcha нет (подтверждено пользователем на 02.05.2026)
- Один человек встречается много раз — ДЕДУПЛИЦИРУЕМ по subject_inn
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

HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class RmspError(Exception):
    pass


@dataclass
class RmspCandidate:
    """
    Один кандидат-самозанятый из реестра.
    """
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
        Приближённая дата начала статуса НПД — самая ранняя из доступных дат RMSP
        (формат "DD.MM.YYYY"). Это нижняя граница: «человек ТОЧНО был самозанятым
        на эту дату». Реальная дата регистрации может быть раньше но не позже.
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
        if self._client is None:
            raise RmspError("RmspClient не инициализирован — используй `async with`")

        if self._session_kladr == kladr_code:
            return

        params = {"sk": "SZ", "kladr": kladr_code}
        log.info(f"[rmsp] GET search.html sk=SZ kladr={kladr_code}")

        try:
            response = await self._client.get(RMSP_SEARCH_HTML, params=params)
            response.raise_for_status()
            self._session_kladr = kladr_code
            log.debug(
                f"[rmsp] Session ready, cookies={dict(self._client.cookies)}"
            )
        except httpx.HTTPError as e:
            raise RmspError(f"Failed to initialize rmsp session: {e}") from e

    async def search_self_employed(
        self,
        kladr_code: str,
        page: int = 1,
        page_size: int = 100,
        query: str = "",
        strict_region_filter: bool = True,
    ) -> List[RmspCandidate]:
        """
        Возвращает список самозанятых отфильтрованных по KLADR региона.

        Args:
            kladr_code: 13-значный KLADR код
            page, page_size, query: стандартные параметры пагинации
            strict_region_filter: если True (default) — пост-фильтр по region_code
                (первые 2 цифры KLADR). Чужие регионы отсекаются на клиентской стороне.
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

        # Pack 17.1.1: kladr передаём И в URL И в body — для надёжности
        url_params = {
            "m": "Support",
            "sk": "SZ",
            "kladr": kladr_code,
        }

        form_data = {
            "page": str(page),
            "pageSize": str(page_size),
            "query": query,
            "sc": "",
            "sk": "SZ",
            "rp": "",
            "_v": "",
            "kladr": kladr_code,
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
                continue

            if strict_region_filter and candidate.region_code != expected_region:
                wrong_region_count += 1
                log.debug(
                    f"[rmsp] Skip {inn} from region {candidate.region_code} "
                    f"(expected {expected_region})"
                )
                continue

            candidates.append(candidate)
            seen_inns.add(inn)

        if wrong_region_count > 0:
            log.warning(
                f"[rmsp] Filtered {wrong_region_count} candidates from wrong regions "
                f"(expected {expected_region})"
            )

        log.info(
            f"[rmsp] Returning {len(candidates)} candidates from region {expected_region}"
        )
        return candidates

    async def search_multiple_pages(
        self,
        kladr_code: str,
        max_candidates: int = 100,
        page_size: int = 100,
        max_pages: int = 5,
        delay_between_pages: float = 1.0,
        strict_region_filter: bool = True,
    ) -> List[RmspCandidate]:
        """
        Запрашивает несколько страниц подряд пока не наберём max_candidates.
        Полезно когда первая страница даёт мало местных кандидатов после фильтра.
        """
        all_candidates: List[RmspCandidate] = []
        seen_inns: Set[str] = set()

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
                f"[rmsp] Page {page}: +{new_count} (total: {len(all_candidates)})"
            )

            if len(all_candidates) >= max_candidates:
                break
            if new_count == 0:
                log.info("[rmsp] No new candidates, stopping")
                break
            if page < max_pages:
                await asyncio.sleep(delay_between_pages)

        return all_candidates[:max_candidates]
