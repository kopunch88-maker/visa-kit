"""
Pack 28 (07.05.2026): EGRUL-чекер для отсева ИНН открывших ИП.

КОНТЕКСТ:
  rmsp-pp.nalog.ru c фильтром sk=SZ возвращает физиков-самозанятых, но
  часть из них ПОСЛЕ получения поддержки открыли ИП. На разведке Pack 28
  (07.05.2026, 209+135 кандидатов из Краснодара/Москвы) это ~40-75%.
  Их нужно отсеять, иначе при гуглении ИНН вылезет фамилия + ОГРНИП.

API ФНС:
  Двухэтапный поиск через публичный сервис EGRUL:

    1. POST https://egrul.nalog.ru/
       form-data: query=<ИНН>, vyp3CaptchaToken="", page="", region="",
                  PreventChromeAutocomplete=""
       → JSON: {"t": "<token>", "captchaRequired": false}

    2. GET https://egrul.nalog.ru/search-result/<token>
       → JSON: {"rows": [{"cnt": "0", "tot": "0", "k": "sprav-fl", ...}]}

  Если суммарно по rows max(cnt, tot) > 0 → ИНН найден в ЕГРИП/ЕГРЮЛ.
  Если все нули — чистый физик.

EGRUL не имеет жёсткого rate-limit'а: на разведке прошло 200+ запросов
без бана и капчи. Throttle 0.3-0.5 сек между запросами — для вежливости.

ОГРАНИЧЕНИЯ:
  - При burst может потребовать капчу (response: captchaRequired=true).
    В этом случае мы поднимаем EgrulCaptchaRequired, вызывающий код
    делает паузу 60+ сек и ретраит.
  - HTTP 5xx в редких случаях — поднимаем EgrulError, retry на уровне
    pool refill loop (delay + повтор).

Использование:
    async with EgrulChecker() as checker:
        found_in_egrul = await checker.is_in_egrul("236600621929")
        if found_in_egrul:
            # отсев — кандидат открыл ИП
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)


EGRUL_BASE_URL = "https://egrul.nalog.ru"
EGRUL_SEARCH_URL = f"{EGRUL_BASE_URL}/"
EGRUL_RESULT_URL = f"{EGRUL_BASE_URL}/search-result"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

EGRUL_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


class EgrulError(Exception):
    """Любая ошибка работы с EGRUL API (HTTP, JSON, etc.)."""


class EgrulCaptchaRequired(EgrulError):
    """ФНС потребовал капчу — нужна пауза перед следующими запросами."""


class EgrulChecker:
    """
    Асинхронный клиент к публичному поиску ЕГРЮЛ/ЕГРИП ФНС.

    Использование:
        async with EgrulChecker() as checker:
            in_egrul = await checker.is_in_egrul("236600621929")

    Метод is_in_egrul:
        True  — ИНН найден (есть запись в ЕГРИП/ЕГРЮЛ → отсев)
        False — ИНН не найден (чистый физик)

    На исключения (network/JSON/captcha) — поднимает EgrulError/-Captcha-.
    """

    def __init__(
        self,
        timeout: httpx.Timeout = EGRUL_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        throttle_seconds: float = 0.3,
    ):
        self._timeout = timeout
        self._user_agent = user_agent
        self._throttle = throttle_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "EgrulChecker":
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_in_egrul(self, inn: str) -> bool:
        """
        Возвращает True если ИНН зарегистрирован в ЕГРИП или ЕГРЮЛ
        (то есть человек открыл ИП или связан с ЮЛ → не подходит для легенды).

        Возвращает False если ничего не найдено.

        Raises:
            EgrulCaptchaRequired — нужна пауза, повторить позже
            EgrulError — другая ошибка (HTTP/JSON), вызвавший код решает retry
        """
        if self._client is None:
            raise EgrulError("EgrulChecker not initialized — use `async with`")

        if not inn or len(inn) not in (10, 12) or not inn.isdigit():
            raise EgrulError(f"INN must be 10 or 12 digits, got: {inn!r}")

        if self._throttle > 0:
            await asyncio.sleep(self._throttle)

        # ----- Шаг 1: получить токен -----
        payload = {
            "vyp3CaptchaToken": "",
            "page": "",
            "query": inn,
            "region": "",
            "PreventChromeAutocomplete": "",
        }

        try:
            r1 = await self._client.post(EGRUL_SEARCH_URL, data=payload)
        except httpx.HTTPError as e:
            err_type = type(e).__name__
            log.warning("[egrul] step1 HTTPError for inn=%s: %s: %s",
                        inn, err_type, e)
            raise EgrulError(f"egrul step1 ({err_type}): {e}") from e

        if r1.status_code != 200:
            raise EgrulError(
                f"egrul step1 unexpected status {r1.status_code}: "
                f"{r1.text[:200]}"
            )

        try:
            data1 = r1.json()
        except ValueError as e:
            raise EgrulError(f"egrul step1 returned non-JSON: {e}") from e

        if data1.get("captchaRequired"):
            log.warning("[egrul] CAPTCHA required for inn=%s", inn)
            raise EgrulCaptchaRequired(f"CAPTCHA required for {inn}")

        token = data1.get("t")
        if not token:
            raise EgrulError(f"egrul step1 returned no token: {data1!r}")

        # ----- Шаг 2: получить результат -----
        try:
            r2 = await self._client.get(f"{EGRUL_RESULT_URL}/{token}")
        except httpx.HTTPError as e:
            err_type = type(e).__name__
            log.warning("[egrul] step2 HTTPError for inn=%s: %s: %s",
                        inn, err_type, e)
            raise EgrulError(f"egrul step2 ({err_type}): {e}") from e

        if r2.status_code != 200:
            raise EgrulError(
                f"egrul step2 unexpected status {r2.status_code}: "
                f"{r2.text[:200]}"
            )

        try:
            data2 = r2.json()
        except ValueError as e:
            raise EgrulError(f"egrul step2 returned non-JSON: {e}") from e

        rows = data2.get("rows", [])
        if not isinstance(rows, list):
            raise EgrulError(f"egrul step2 'rows' is not a list: {type(rows)}")

        # Подсчёт совпадений: каждый row — это раздел поиска.
        total_found = 0
        for row in rows:
            try:
                cnt = int(row.get("cnt", "0") or "0")
                tot = int(row.get("tot", "0") or "0")
            except (TypeError, ValueError):
                cnt = tot = 0
            total_found += max(cnt, tot)

        log.debug("[egrul] inn=%s rows_count=%d total_found=%d",
                  inn, len(rows), total_found)

        return total_found > 0
