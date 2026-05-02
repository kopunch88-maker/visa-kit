"""
Pack 17.1 — Проверка статуса самозанятого (НПД) через ФНС API.

Источник: https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status
(публичный сервис ФНС, бесплатный, без авторизации)

Endpoint:
    POST https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status
    Body: { "inn": "<12 digits>", "requestDate": "YYYY-MM-DD" }

Ответ (если самозанятый активен):
    {
        "status": true,                    # является ли НПД на requestDate
        "message": "...",                  # текстовое сообщение
        "firstName": "ИВАННА",
        "lastName": "АКБАШ",
        "secondName": "ИВАНОВНА",
        "registrationDate": "2023-05-15",  # дата регистрации НПД ← ВОТ ЭТО НАМ НУЖНО
        ...
    }

Ответ если не НПД:
    {
        "status": false,
        "message": "ИНН ... не является плательщиком НПД на ..."
    }

ОГРАНИЧЕНИЯ:
- 2 запроса в минуту с одного IP — критично для нашего пайплайна
- Timeout не менее 60 секунд по требованию ФНС

ИСПОЛЬЗОВАНИЕ:
    async with NpdStatusChecker() as checker:
        result = await checker.check(inn="660501482800")
        if result.is_active:
            print(result.registration_date)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

log = logging.getLogger(__name__)


NPD_BASE_URL = "https://statusnpd.nalog.ru"
NPD_CHECK_ENDPOINT = f"{NPD_BASE_URL}/api/v1/tracker/taxpayer_status"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

# 60-секундный timeout по требованиям ФНС
NPD_TIMEOUT = httpx.Timeout(70.0, connect=10.0)

# Минимальный интервал между запросами (вежливость + страховка от rate limit)
# 2 req/min = 30 секунд между запросами
MIN_REQUEST_INTERVAL_SECONDS = 31.0


class NpdStatusError(Exception):
    """Ошибка проверки статуса НПД."""

    pass


@dataclass
class NpdStatusResult:
    """
    Результат проверки статуса НПД для конкретного ИНН.
    """
    inn: str
    is_active: bool                       # True = является плательщиком НПД
    request_date: date                    # дата на которую проверяли
    registration_date: Optional[date] = None  # дата начала статуса НПД
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    second_name: Optional[str] = None
    message: Optional[str] = None
    raw: Optional[dict] = None

    @property
    def full_name(self) -> str:
        parts = [
            (self.last_name or "").strip(),
            (self.first_name or "").strip(),
            (self.second_name or "").strip(),
        ]
        return " ".join(p for p in parts if p)


class NpdStatusChecker:
    """
    Асинхронный клиент к публичному API проверки НПД ФНС.

    Содержит rate limiter — гарантирует что между запросами проходит
    не менее 31 секунды (2 req/min лимит ФНС).

    Использование:
        async with NpdStatusChecker() as checker:
            result = await checker.check("660501482800")
            if result.is_active:
                print(f"Зарегистрирован {result.registration_date}")
    """

    # Класс-уровневый last_request_time — общий между всеми инстансами
    # (ФНС считает rate limit по IP, а не по сессии)
    _last_request_time: float = 0.0
    _rate_limit_lock: asyncio.Lock = asyncio.Lock()

    def __init__(
        self,
        timeout: httpx.Timeout = NPD_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_rate_limit: bool = True,
    ):
        self._timeout = timeout
        self._user_agent = user_agent
        self._respect_rate_limit = respect_rate_limit
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "NpdStatusChecker":
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _wait_for_rate_limit(self) -> None:
        """
        Ждёт пока не пройдёт MIN_REQUEST_INTERVAL_SECONDS с момента
        последнего запроса. Lock — чтобы при concurrent запросах
        они не превышали лимит.
        """
        if not self._respect_rate_limit:
            return

        async with self._rate_limit_lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            elapsed = now - NpdStatusChecker._last_request_time
            wait_seconds = MIN_REQUEST_INTERVAL_SECONDS - elapsed

            if wait_seconds > 0:
                log.info(
                    f"[npd] Rate limit: waiting {wait_seconds:.1f}s "
                    f"before next request"
                )
                await asyncio.sleep(wait_seconds)

            # Обновляем после ожидания (помечаем что запрос «начался сейчас»)
            NpdStatusChecker._last_request_time = loop.time()

    async def check(
        self,
        inn: str,
        request_date: Optional[date] = None,
    ) -> NpdStatusResult:
        """
        Проверяет статус ИНН на дату (по умолчанию — сегодня).

        Args:
            inn: 12-значный ИНН физлица
            request_date: дата проверки (по умолчанию today)

        Returns:
            NpdStatusResult с is_active и registration_date

        Raises:
            NpdStatusError: если HTTP/JSON ошибка или неожиданный формат ответа
        """
        if self._client is None:
            raise NpdStatusError(
                "NpdStatusChecker не инициализирован — используй `async with`"
            )

        if not inn or len(inn) != 12 or not inn.isdigit():
            raise NpdStatusError(
                f"ИНН должен быть 12 цифр для физлица, получено: {inn!r}"
            )

        if request_date is None:
            request_date = date.today()

        await self._wait_for_rate_limit()

        body = {
            "inn": inn,
            "requestDate": request_date.isoformat(),
        }

        log.info(f"[npd] Checking inn={inn}, requestDate={body['requestDate']}")

        try:
            response = await self._client.post(NPD_CHECK_ENDPOINT, json=body)
        except httpx.HTTPError as e:
            raise NpdStatusError(f"npd HTTP error: {e}") from e

        # 422 = бизнес-ошибка (некорректный запрос)
        if response.status_code == 422:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"raw_text": response.text}
            log.warning(f"[npd] 422 error for inn={inn}: {err_body}")
            raise NpdStatusError(f"ФНС вернул 422 для ИНН {inn}: {err_body}")

        if response.status_code != 200:
            raise NpdStatusError(
                f"npd unexpected status {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as e:
            raise NpdStatusError(f"npd returned non-JSON: {e}") from e

        log.debug(f"[npd] Response for {inn}: {data}")

        is_active = bool(data.get("status", False))

        # Парсинг даты регистрации НПД
        reg_date_str = data.get("registrationDate")
        registration_date = None
        if reg_date_str:
            try:
                registration_date = date.fromisoformat(reg_date_str)
            except ValueError:
                log.warning(
                    f"[npd] Bad registrationDate format: {reg_date_str!r}"
                )

        return NpdStatusResult(
            inn=inn,
            is_active=is_active,
            request_date=request_date,
            registration_date=registration_date,
            first_name=data.get("firstName"),
            last_name=data.get("lastName"),
            second_name=data.get("secondName"),
            message=data.get("message"),
            raw=data,
        )

    @classmethod
    async def reset_rate_limit(cls) -> None:
        """
        Сбросить класс-уровневый rate limiter.
        Используется только в тестах.
        """
        async with cls._rate_limit_lock:
            cls._last_request_time = 0.0
