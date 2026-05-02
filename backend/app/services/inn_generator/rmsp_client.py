"""
Pack 17.1 — HTTP клиент к публичному реестру МСП ФНС
(rmsp-pp.nalog.ru = Реестр Получателей Поддержки).

Несмотря на название «получателей поддержки», это ОЧЕНЬ полная база:
~27 тысяч самозанятых получали хотя бы одну консультацию через ЦП «Малый бизнес»
поэтому попадают в реестр. Это даёт нам широкий выбор по регионам.

Алгоритм работы:
1. GET https://rmsp-pp.nalog.ru/search.html?sk=SZ&kladr={KLADR}
   → получаем JSESSIONID + сервер кэширует фильтр (sk, kladr) в сессии

2. POST https://rmsp-pp.nalog.ru/search-proc.json?m=Support
   form-data: page, pageSize, query, sc, sk, rp, _v
   → возвращает JSON со списком субъектов отфильтрованных по сессии

ВАЖНО:
- Captcha нет (подтверждено пользователем на 02.05.2026)
- Без явных rate limits, но не злоупотребляем (1 запрос за раз достаточно)
- Один человек может встречаться много раз (получал разные виды поддержки),
  поэтому ДЕДУПЛИЦИРУЕМ по subject_inn

ЗАВИСИМОСТИ: httpx (асинхронный HTTP клиент, уже в проекте для других сервисов)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set

import httpx

log = logging.getLogger(__name__)


# Константы для запросов
RMSP_BASE_URL = "https://rmsp-pp.nalog.ru"
RMSP_SEARCH_HTML = f"{RMSP_BASE_URL}/search.html"
RMSP_SEARCH_PROC = f"{RMSP_BASE_URL}/search-proc.json"

# Реалистичный User-Agent — иначе налоговая может вернуть 403
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

# Стандартные timeouts
HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class RmspError(Exception):
    """Ошибка работы с rmsp-pp.nalog.ru."""

    pass


@dataclass
class RmspCandidate:
    """
    Один кандидат-самозанятый из реестра.

    Поля соответствуют структуре ответа rmsp-pp `data[i]`:
    https://rmsp-pp.nalog.ru/search-proc.json
    """
    inn: str                          # subject_inn — 12 цифр
    full_name: str                    # subject_name — "ФАМИЛИЯ ИМЯ ОТЧЕСТВО"
    nptype: str                       # subject_nptype: "SZ"=самозанятый, "IP"=ИП
    category: int                     # subject_category: 4=самозанятый
    region_code: str                  # subject_region: "23"=Краснодарский край
    ogrn: Optional[str] = None        # subject_ogrn: у самозанятых должен быть None

    # Сырые данные ответа (для отладки и расширения)
    raw: dict = field(default_factory=dict)

    @property
    def is_self_employed(self) -> bool:
        """
        True если это «настоящий» самозанятый:
        - тип SZ (а не IP)
        - категория 4 (физлицо-самозанятый)
        - нет ОГРН (это ИП-маркер)

        Иногда в реестре есть бывшие ИП у которых ОГРН остался — отсеиваем.
        """
        return (
            self.nptype == "SZ"
            and self.category == 4
            and not self.ogrn
        )

    @property
    def parts(self) -> tuple[str, str, str]:
        """
        Разбивает full_name "АКБАШ ИВАННА ИВАНОВНА" → (last, first, middle).
        Если средне имя нет — третий элемент пустой.
        """
        words = self.full_name.split()
        last = words[0] if len(words) > 0 else ""
        first = words[1] if len(words) > 1 else ""
        middle = words[2] if len(words) > 2 else ""
        return last, first, middle


class RmspClient:
    """
    Асинхронный клиент к реестру самозанятых ФНС.

    Использование:
        async with RmspClient() as client:
            candidates = await client.search_self_employed(
                kladr_code="2300000700000",
                page_size=100,
            )

    Использует один shared session для cookie persistence (JSESSIONID + filter cache).
    """

    def __init__(
        self,
        timeout: httpx.Timeout = HTTP_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self._timeout = timeout
        self._user_agent = user_agent
        self._client: Optional[httpx.AsyncClient] = None
        self._session_kladr: Optional[str] = None  # последний установленный фильтр

    async def __aenter__(self) -> "RmspClient":
        # follow_redirects=True — на случай редиректа с http→https
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
        Шаг 1: GET search.html — получаем JSESSIONID и сервер кэширует фильтр.
        Делаем повторно только если изменился фильтр (для разных регионов).
        """
        if self._client is None:
            raise RmspError("RmspClient не инициализирован — используй `async with`")

        if self._session_kladr == kladr_code:
            return  # уже инициализирована для этого региона

        params = {"sk": "SZ", "kladr": kladr_code}
        log.info(f"[rmsp] Initializing session for kladr={kladr_code}")

        try:
            response = await self._client.get(RMSP_SEARCH_HTML, params=params)
            response.raise_for_status()
            self._session_kladr = kladr_code
            log.debug(
                f"[rmsp] Session ready for kladr={kladr_code}, "
                f"cookies={dict(self._client.cookies)}"
            )
        except httpx.HTTPError as e:
            raise RmspError(f"Failed to initialize rmsp session: {e}") from e

    async def search_self_employed(
        self,
        kladr_code: str,
        page: int = 1,
        page_size: int = 100,
        query: str = "",
    ) -> List[RmspCandidate]:
        """
        Возвращает список самозанятых отфильтрованных по KLADR региона.

        Args:
            kladr_code: 13-значный KLADR код (например '2300000700000' = Сочи)
            page: номер страницы (1-based)
            page_size: 10/20/50/100 (валидно по rmsp-pp)
            query: дополнительный фильтр по фамилии (если нужно)

        Returns:
            List[RmspCandidate] — список кандидатов с дедупликацией по ИНН.
            Только настоящие самозанятые (sk=SZ, category=4, без ОГРН).

        Raises:
            RmspError: если запрос не удался или ответ невалидный.
        """
        if self._client is None:
            raise RmspError("RmspClient не инициализирован — используй `async with`")

        # Валидация KLADR
        if not kladr_code or len(kladr_code) != 13 or not kladr_code.isdigit():
            raise RmspError(
                f"kladr_code должен быть 13 цифр, получено: {kladr_code!r}"
            )

        if page_size not in (10, 20, 50, 100):
            raise RmspError(
                f"page_size должен быть 10/20/50/100, получено: {page_size}"
            )

        # Шаг 1: инициализируем сессию для этого KLADR
        await self._ensure_session_for_kladr(kladr_code)

        # Шаг 2: запрашиваем данные
        form_data = {
            "page": str(page),
            "pageSize": str(page_size),
            "query": query,
            "sc": "",       # subject_category - пусто
            "sk": "SZ",     # subject_kind - SZ=самозанятый
            "rp": "",       # report_period - пусто
            "_v": "",       # cache buster - пусто
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": RMSP_BASE_URL,
            "Referer": f"{RMSP_SEARCH_HTML}?sk=SZ&kladr={kladr_code}",
            "X-Requested-With": "XMLHttpRequest",
        }

        log.info(
            f"[rmsp] Searching kladr={kladr_code}, page={page}, "
            f"pageSize={page_size}, query={query!r}"
        )

        try:
            response = await self._client.post(
                RMSP_SEARCH_PROC,
                params={"m": "Support"},
                data=form_data,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            raise RmspError(f"rmsp HTTP error: {e}") from e
        except ValueError as e:
            # JSON decode failed
            raise RmspError(f"rmsp returned non-JSON response: {e}") from e

        if "data" not in data:
            log.warning(f"[rmsp] Unexpected response shape: keys={list(data.keys())}")
            raise RmspError(f"rmsp response missing 'data' field: {data}")

        rows = data.get("data", [])
        total = data.get("rowCount", 0)
        log.info(f"[rmsp] Got {len(rows)} rows (total available: {total})")

        # Парсинг + фильтрация + дедупликация
        candidates: List[RmspCandidate] = []
        seen_inns: Set[str] = set()

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
                raw=row,
            )

            # Фильтруем только настоящих самозанятых
            if not candidate.is_self_employed:
                log.debug(
                    f"[rmsp] Skipping {inn} (nptype={candidate.nptype}, "
                    f"category={candidate.category}, ogrn={candidate.ogrn})"
                )
                continue

            candidates.append(candidate)
            seen_inns.add(inn)

        log.info(
            f"[rmsp] Filtered to {len(candidates)} unique self-employed candidates"
        )
        return candidates

    async def search_multiple_pages(
        self,
        kladr_code: str,
        max_candidates: int = 200,
        page_size: int = 100,
        delay_between_pages: float = 1.0,
    ) -> List[RmspCandidate]:
        """
        Запрашивает несколько страниц подряд пока не наберём max_candidates
        уникальных самозанятых.

        Полезно когда первая страница даёт мало уникальных ИНН после дедупликации.
        Между страницами ждёт delay_between_pages секунд (вежливость к ФНС).
        """
        all_candidates: List[RmspCandidate] = []
        seen_inns: Set[str] = set()

        for page in range(1, 11):  # максимум 10 страниц
            page_candidates = await self.search_self_employed(
                kladr_code=kladr_code,
                page=page,
                page_size=page_size,
            )

            # Добавляем только новых
            new_count = 0
            for c in page_candidates:
                if c.inn not in seen_inns:
                    all_candidates.append(c)
                    seen_inns.add(c.inn)
                    new_count += 1

            log.info(f"[rmsp] Page {page}: +{new_count} new (total: {len(all_candidates)})")

            if len(all_candidates) >= max_candidates:
                break

            if new_count == 0:
                # Конец данных
                break

            if page < 10:
                await asyncio.sleep(delay_between_pages)

        return all_candidates[:max_candidates]
