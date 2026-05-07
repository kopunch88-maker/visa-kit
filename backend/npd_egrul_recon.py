# -*- coding: utf-8 -*-
"""
NPD/EGRUL API Recon — разведка трёх API ФНС перед написанием Pack 28.

Что проверяем:
  1) egrul.nalog.ru — поиск ИНН в ЕГРИП (отсев тех у кого открыто ИП).
     На сайте форма работает через POST на /. Проверим, отдаёт ли он что-то
     программно, какой формат у запроса/ответа.

  2) npd.nalog.ru/api/v1/tracker/taxpayer_status — проверка статуса НПД.
     Из формы на сайте видно что endpoint принимает inn и requestDate.
     Реальный URL API нужно проверить — DevTools показал бы наверняка,
     но попробуем угадать стандартный паттерн.

  3) Идея бинпоиска даты — сделать 2 запроса к npd на разные даты:
     - 2019-01-01 (НПД ещё не было) → должен сказать «не плательщик»
     - сегодня → должен сказать «плательщик»
     Если поведение разное — бинпоиск имеет смысл.

Использование:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1   # для requests
    $env:PYTHONIOENCODING = "utf-8"
    python npd_egrul_recon.py 236600621929

Если requests не установлен глобально — установи:
    pip install requests --break-system-packages
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

try:
    import requests
except ImportError:
    print("❌ Нет библиотеки requests. Установи: pip install requests", file=sys.stderr)
    sys.exit(1)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.9",
}


def _print_section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def _truncate(s: str, n: int = 800) -> str:
    return s if len(s) <= n else s[:n] + f"\n... [+{len(s)-n} chars]"


# ----------------------------------------------------------------------------
# 1. EGRUL — проверка наличия ИП по ИНН
# ----------------------------------------------------------------------------
def check_egrul(inn: str) -> None:
    _print_section(f"1️⃣  EGRUL.NALOG.RU — есть ли ИП с ИНН {inn}?")

    # Сайт egrul.nalog.ru использует POST на /. Из публичных описаний:
    # endpoint POST https://egrul.nalog.ru/  с form-data {query: <ИНН>, ...}
    # отдаёт {"t": "<token>"}. Затем GET /search-result/<token> возвращает JSON.
    url = "https://egrul.nalog.ru/"
    payload = {
        "vyp3CaptchaToken": "",
        "page": "",
        "query": inn,
        "region": "",
        "PreventChromeAutocomplete": "",
    }
    print(f"POST {url}")
    print(f"     payload: {payload}")
    try:
        r = requests.post(url, data=payload, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        print(f"  ❌ network error: {e}")
        return

    print(f"  ← status: {r.status_code}")
    print(f"  ← Content-Type: {r.headers.get('Content-Type', '?')}")
    print(f"  ← body (first 800 chars):")
    print(_truncate(r.text))

    # Если получили токен — попробуем подтянуть результат
    try:
        token_data = r.json()
    except json.JSONDecodeError:
        print("\n  (тело не JSON — возможно поменяли API или нужна капча)")
        return

    token = token_data.get("t")
    if not token:
        print(f"\n  ⚠️  В ответе нет токена 't'. Полный JSON: {token_data}")
        return

    print(f"\n  ✓ получили токен: {token}")
    result_url = f"https://egrul.nalog.ru/search-result/{token}"
    print(f"  GET  {result_url}")
    try:
        r2 = requests.get(result_url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        print(f"  ❌ network error: {e}")
        return

    print(f"  ← status: {r2.status_code}")
    print(f"  ← Content-Type: {r2.headers.get('Content-Type', '?')}")
    print(f"  ← body (first 800 chars):")
    print(_truncate(r2.text))

    try:
        data = r2.json()
    except json.JSONDecodeError:
        print("\n  (результат не JSON)")
        return

    rows = data.get("rows", [])
    print(f"\n  📊 найдено записей: {len(rows)}")
    if rows:
        print("  ❌ ИНН СВЕТИТСЯ как ИП — для легенды НЕ подходит")
        for row in rows[:3]:
            print(f"     • {row}")
    else:
        print("  ✅ ИНН в ЕГРИП НЕ НАЙДЕН — кандидат подходит (если NPD-статус ОК)")


# ----------------------------------------------------------------------------
# 2. NPD — проверка статуса плательщика НПД
# ----------------------------------------------------------------------------
def check_npd(inn: str, check_date: str, label: str) -> dict | None:
    print(f"\n  • {label} ({check_date})")
    # endpoint: POST https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status
    # payload: {"inn": "...", "requestDate": "YYYY-MM-DD"}
    url = "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status"
    payload = {"inn": inn, "requestDate": check_date}
    print(f"    POST {url}")
    print(f"        payload: {payload}")
    try:
        r = requests.post(
            url, json=payload, headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"    ❌ network error: {e}")
        return None

    print(f"    ← status: {r.status_code}")
    print(f"    ← body: {_truncate(r.text, 400)}")

    try:
        data = r.json()
    except json.JSONDecodeError:
        return None

    return data


def explore_npd(inn: str) -> None:
    _print_section(f"2️⃣  NPD.NALOG.RU — статус ИНН {inn} как плательщика НПД")

    today = date.today().isoformat()
    long_ago = "2019-01-15"  # за пару недель до запуска НПД (1 января 2019 в 4 регионах)

    # Сегодня — должен быть «плательщик»
    today_data = check_npd(inn, today, "Сегодня")

    # Давно — должен быть «не плательщик» (если человек тогда ещё не зарегился)
    past_data = check_npd(inn, long_ago, "На заре НПД (2019-01-15)")

    if today_data and past_data:
        # Ищем поле статуса. Имя поля может быть разным — посмотрим что есть
        print("\n  📊 структура ответов:")
        print(f"     сегодня:  ключи = {list(today_data.keys())}")
        print(f"     2019-01:  ключи = {list(past_data.keys())}")

        # Эвристика: если ответы отличаются — бинпоиск имеет смысл
        if today_data != past_data:
            print("  ✅ Ответы для разных дат ОТЛИЧАЮТСЯ — бинпоиск даты постановки сработает")
        else:
            print("  ⚠️  Ответы одинаковые — нужно смотреть на конкретное поле статуса")


def main() -> int:
    parser = argparse.ArgumentParser(description="EGRUL + NPD API recon")
    parser.add_argument(
        "inn",
        nargs="?",
        default="236600621929",
        help="ИНН для проверки (по умолчанию — Абакумова из rmsp-pp)",
    )
    args = parser.parse_args()

    inn = args.inn.strip()
    if not inn.isdigit() or len(inn) not in (10, 12):
        print(f"❌ ИНН должен быть 10 или 12 цифр, получено: {inn!r}", file=sys.stderr)
        return 1

    print(f"🔍 Проверяю ИНН: {inn}")

    check_egrul(inn)
    explore_npd(inn)

    _print_section("ИТОГИ")
    print("Что нужно увидеть в выводе выше:")
    print("  1. EGRUL: rows=[] (или has_more=false) → ИП нет, кандидат годный")
    print("  2. NPD сегодня: статус 'плательщик' (HTTP 200, поле status или текст)")
    print("  3. NPD на 2019-01-15: статус 'не плательщик' / другой ответ")
    print()
    print("Если все три пункта ОК — план Pack 28 рабочий, можно делать.")
    print("Если что-то не так (например NPD endpoint не статусnpd, а другой) —")
    print("открой DevTools на npd.nalog.ru/check-status, сделай ручную проверку,")
    print("скопируй URL запроса из вкладки Network и пришли мне.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
