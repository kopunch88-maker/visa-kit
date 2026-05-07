# -*- coding: utf-8 -*-
"""
RMSP-PP recon — проверяем можно ли программно работать с реестром
получателей поддержки (https://rmsp-pp.nalog.ru/).

Что нас интересует:
  1. Выдержит ли rmsp-pp Python-клиент (тот же домен nalog.ru, может банить
     как и npd.nalog.ru — мы видели 402 от него).
  2. Какой у них API для поиска (есть ли публичный JSON-endpoint).
  3. Можно ли скачать Excel программно (через какой URL/POST).

План разведки:
  Шаг 1: GET главной страницы /search.html — посмотреть что отдаёт.
  Шаг 2: Попробовать GET по URL который ты использовал в браузере
         (с параметрами kladr=2300000700000 — Сочи, Краснодарский край).
  Шаг 3: Изучить ответ — это HTML с предзагруженными результатами,
         или SPA где поиск делается отдельным API-запросом?

Использование:
    python rmsp_pp_recon.py
"""
from __future__ import annotations

import sys

try:
    import requests
except ImportError:
    print("❌ pip install requests", file=sys.stderr)
    sys.exit(1)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def line(c: str = "=") -> None:
    print(c * 70)


def truncate(s: str, n: int = 1000) -> str:
    return s if len(s) <= n else s[:n] + f"\n... [+{len(s)-n} chars]"


def try_request(label: str, url: str, *, session: requests.Session) -> None:
    line()
    print(f"  {label}")
    print(f"  GET {url}")
    line("-")
    try:
        r = session.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"  ❌ network error: {e}")
        return
    print(f"  ← status:        {r.status_code}")
    print(f"  ← Content-Type:  {r.headers.get('Content-Type', '?')}")
    print(f"  ← Content-Length:{r.headers.get('Content-Length', '?')}")
    print(f"  ← cookies after: {list(session.cookies.keys())}")
    print(f"  ← final URL:     {r.url}")
    print()
    print(f"  ← body (первые 1000 chars):")
    line("-")
    print(truncate(r.text, 1000))
    line("-")
    print()

    # Эвристики
    text_lower = r.text.lower()
    if "доступ к сайту временно ограничен" in text_lower:
        print("  ⛔ ВАЖНО: тот же WAF что и у npd.nalog.ru — путь нерабочий!")
    elif r.status_code == 200 and "<html" in text_lower[:200]:
        print(f"  ✅ HTML отдаётся, длина {len(r.text)} bytes")
        # Проверим, это SPA-shell или сразу с данными?
        if "react" in text_lower or "app-root" in text_lower or '<div id="root"' in text_lower:
            print("  ℹ️  это SPA-shell (React) — данные подгружаются отдельным API-запросом.")
        elif "получателей" in text_lower or "найдено записей" in text_lower:
            print("  ℹ️  HTML содержит данные результатов поиска!")


def main() -> int:
    session = requests.Session()

    # Шаг 1: главная страница реестра
    try_request(
        "Шаг 1: главная страница reestra rmsp-pp",
        "https://rmsp-pp.nalog.ru/",
        session=session,
    )

    # Шаг 2: страница поиска с параметрами региона (Краснодарский край)
    # Параметры взяты из URL который ты дал в чате
    try_request(
        "Шаг 2: страница поиска с фильтром по региону (Краснодарский край)",
        "https://rmsp-pp.nalog.ru/search.html?m=SupportExt&page=1&pageSize=100&sk=SZ&kladr=2300000700000",
        session=session,
    )

    # Шаг 3: проверим стандартный путь для API
    # Многие SPA-сайты ФНС используют api.* подомен или /api/ префикс
    api_candidates = [
        "https://rmsp-pp.nalog.ru/api/v1/search?m=SupportExt&page=1&pageSize=100&sk=SZ&kladr=2300000700000",
        "https://rmsp-pp.nalog.ru/search-proc.json?m=SupportExt&kladr=2300000700000",
        "https://rmsp-pp.nalog.ru/api/search?kladr=2300000700000",
    ]
    for url in api_candidates:
        try_request(
            f"Шаг 3: пробуем угаданный API endpoint",
            url,
            session=session,
        )

    line()
    print("ИТОГ:")
    print("  • Если на любом шаге увидели 'Доступ к сайту временно ограничен' —")
    print("    rmsp-pp забанил так же как npd. Нужен Playwright.")
    print("  • Если HTML страницы возвращается, но он SPA-shell без данных —")
    print("    нужно искать настоящий API через DevTools (Network).")
    print("  • Если виден HTML с реальными данными — отлично, парсим как обычный сайт.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
