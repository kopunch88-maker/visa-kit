"""
Клиент для получения курса валют ЦБ РФ.

Использует бесплатный API cbr-xml-daily.ru.
Кеш по дате — один и тот же день не запрашивается дважды.

Если нет интернета или ЦБ недоступен — возвращает дефолтный курс
(можно настроить через DEFAULT_EUR_RATE) и логирует предупреждение.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import json
from typing import Optional
import logging

import httpx

logger = logging.getLogger(__name__)


# Простой файловый кеш для разработки. В проде заменить на Redis.
CACHE_DIR = Path(__file__).resolve().parents[2] / "_cache" / "cbr"

# Дефолтный курс если ничего недоступно (примерно середина 2026)
DEFAULT_EUR_RATE = Decimal("89.5")


def _cache_path(d: date, currency: str) -> Path:
    return CACHE_DIR / f"{d.isoformat()}_{currency}.json"


def get_eur_rub_rate(target_date: Optional[date] = None) -> Decimal:
    """
    Возвращает курс EUR/RUB на указанную дату.

    Если на запрошенную дату курс не доступен (выходные, праздники), берётся
    последний предыдущий рабочий день.

    Args:
        target_date: дата, на которую нужен курс. None = сегодня.

    Returns:
        Курс в виде Decimal (например, Decimal("89.4231")).
    """
    if target_date is None:
        target_date = date.today()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Пробуем точную дату, потом откатываемся назад до 7 дней
    for offset in range(7):
        d = target_date - timedelta(days=offset)
        cache = _cache_path(d, "EUR")

        # Кеш-хит
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                return Decimal(data["rate"])
            except (json.JSONDecodeError, KeyError):
                cache.unlink(missing_ok=True)

        # Запрос к ЦБ через зеркало с историей
        try:
            url = f"https://www.cbr-xml-daily.ru/archive/{d.year:04d}/{d.month:02d}/{d.day:02d}/daily_json.js"
            resp = httpx.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                eur = data["Valute"]["EUR"]
                rate = Decimal(str(eur["Value"])) / Decimal(eur["Nominal"])
                cache.write_text(
                    json.dumps({"rate": str(rate), "source_date": d.isoformat()}),
                    encoding="utf-8",
                )
                return rate
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
            logger.debug(f"CBR rate fetch for {d}: {e}")
            continue

    logger.warning(
        f"Could not fetch EUR rate for {target_date} or 7 days before. "
        f"Falling back to DEFAULT_EUR_RATE={DEFAULT_EUR_RATE}"
    )
    return DEFAULT_EUR_RATE


def convert_rub_to_eur(
    amount_rub: Decimal | int | float | None,
    target_date: Optional[date] = None,
    rate_override: Optional[Decimal] = None,
) -> Decimal:
    """
    Конвертирует рубли в евро по курсу ЦБ на дату.

    Args:
        amount_rub: сумма в рублях
        target_date: дата для курса ЦБ
        rate_override: если задано — использует это значение вместо ЦБ

    Returns:
        Сумма в евро, округлённая до целых.
    """
    if amount_rub is None:
        return Decimal("0")
    rate = rate_override if rate_override is not None else get_eur_rub_rate(target_date)
    eur = Decimal(str(amount_rub)) / rate
    return eur.quantize(Decimal("1"))
