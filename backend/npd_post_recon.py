# -*- coding: utf-8 -*-
"""
NPD POST-форма recon — воспроизводим что делает браузер на npd.nalog.ru/check-status/

Логика:
    1. GET https://npd.nalog.ru/check-status/  → парсим HTML, выдёргиваем
       скрытые поля формы (__VIEWSTATE и т.п. для ASP.NET) + cookies сессии.
    2. POST на ту же страницу с этими полями + ИНН + дата.
    3. Парсим HTML-ответ, ищем фразу «является плательщиком» / «не является».

Делаем 3 проверки на одном ИНН для разных дат:
    - сегодня        → ожидаем «является»
    - 15.01.2024     → если зарегистрирован тогда — «является», иначе «не является»
    - 01.01.2019     → ожидаем «не является» (НПД ещё не запущен)

Если хотя бы один формат запроса вернёт распознаваемый ответ — план рабочий.

Использование (PowerShell):
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    pip install requests beautifulsoup4
    $env:PYTHONIOENCODING = "utf-8"
    python npd_post_recon.py 236600621929
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from typing import Optional

try:
    import requests
except ImportError:
    print("❌ pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)


URL = "https://npd.nalog.ru/check-status/"

# Полный набор Chrome-like заголовков. ASP.NET сайт может фильтровать
# по Sec-Fetch-* и наличию правильного Accept-Encoding.
HEADERS_GET = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Google Chrome";v="124", "Chromium";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _truncate(s: str, n: int = 600) -> str:
    return s if len(s) <= n else s[:n] + f"... [+{len(s)-n}]"


def fetch_form(session: requests.Session) -> tuple[Optional[BeautifulSoup], Optional[str]]:
    """
    GET страницы. Возвращает (soup, debug_html_path).
    soup — распаршенный HTML, чтобы можно было выдрать поля формы.
    """
    print(f"\n[1/2] GET {URL}")
    try:
        r = session.get(URL, headers=HEADERS_GET, timeout=20)
    except requests.RequestException as e:
        print(f"  ❌ {e}")
        return None, None

    print(f"  ← status: {r.status_code}, len: {len(r.text)} bytes, "
          f"cookies: {list(session.cookies.keys())}")
    if r.status_code != 200:
        print(f"  ← body: {_truncate(r.text)}")
        return None, None

    return BeautifulSoup(r.text, "html.parser"), r.text


def extract_form_fields(soup: BeautifulSoup) -> dict[str, str]:
    """
    Достаём все скрытые поля + поля input/select формы поиска.
    ASP.NET кладёт VIEWSTATE/EVENTVALIDATION в hidden inputs.
    """
    form = soup.find("form")
    if not form:
        print("  ⚠️  <form> на странице не найден")
        return {}

    fields: dict[str, str] = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name")
        if not name:
            continue
        value = inp.get("value", "")
        # Не перезаписываем submit-кнопки — мы свою назначим сами
        if inp.get("type") == "submit":
            continue
        fields[name] = value

    print(f"  📋 поля формы найдены: {len(fields)}")
    for k in fields:
        v = fields[k]
        v_short = _truncate(v, 60) if v else "(пусто)"
        print(f"     {k} = {v_short}")
    return fields


def find_inn_and_date_fields(fields: dict[str, str]) -> tuple[Optional[str], Optional[str]]:
    """
    Ищем имена полей ИНН и даты по эвристике.
    Они обычно содержат «inn», «query», «date», «request» или ASP.NET-style ct100$...$txtInn.
    """
    inn_field = None
    date_field = None
    for name in fields:
        low = name.lower()
        if any(s in low for s in ("inn", "query", "tbinn", "txtinn")):
            inn_field = name
        if any(s in low for s in ("date", "tbdate", "txtdate", "calendar")):
            date_field = name
    return inn_field, date_field


def check_one(session: requests.Session, fields: dict[str, str],
              inn_field: str, date_field: str,
              inn: str, check_date_str: str, button_field: Optional[str]) -> Optional[bool]:
    """Делает POST и пытается распознать ответ."""
    payload = {**fields, inn_field: inn, date_field: check_date_str}
    if button_field:
        payload[button_field] = "Найти"

    headers_post = {
        **HEADERS_GET,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://npd.nalog.ru",
        "Referer": URL,
        # Для постбэка на ту же страницу:
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }

    print(f"\n  POST {inn} на дату {check_date_str}")
    try:
        r = session.post(URL, data=payload, headers=headers_post, timeout=20,
                         allow_redirects=True)
    except requests.RequestException as e:
        print(f"    ❌ {e}")
        return None

    print(f"    ← status: {r.status_code}, len: {len(r.text)}, "
          f"final url: {r.url}")
    print(f"    ← response headers (first 5): "
          f"{dict(list(r.headers.items())[:5])}")

    if r.status_code != 200:
        print(f"    ← ПОЛНОЕ ТЕЛО ОТВЕТА:")
        print("─" * 70)
        print(r.text)
        print("─" * 70)
        return None

    text = r.text
    # Ищем характерные фразы ответа
    pos_match = re.search(r"является плательщиком налога на профессиональный доход", text)
    neg_match = re.search(r"не\s+является плательщиком налога на профессиональный доход", text)

    if neg_match:
        print(f"    📨 ответ: ❌ НЕ является плательщиком")
        return False
    if pos_match:
        print(f"    📨 ответ: ✅ является плательщиком")
        return True

    # Не нашли ни того ни другого — что-то странное, покажу кусок страницы
    # Ищем блок результата
    soup_resp = BeautifulSoup(text, "html.parser")
    # На странице результат лежит в div'е снизу; для дебага возьмём весь текст body
    body = soup_resp.find("body")
    body_text = (body.get_text(separator=" ", strip=True) if body else "")[:1500]
    print(f"    ⚠️  не распознан ответ. Текст body (первые 1500 chars):")
    print(f"    {body_text}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inn", nargs="?", default="236600621929")
    args = parser.parse_args()

    inn = args.inn.strip()
    print(f"🔍 проверяю ИНН {inn} через POST-форму на {URL}")

    session = requests.Session()
    soup, _ = fetch_form(session)
    if not soup:
        return 1

    print(f"\n[2/2] разбор формы…")
    fields = extract_form_fields(soup)
    if not fields:
        return 1

    inn_field, date_field = find_inn_and_date_fields(fields)
    print(f"\n  предположение:")
    print(f"     поле ИНН  = {inn_field!r}")
    print(f"     поле даты = {date_field!r}")
    if not inn_field or not date_field:
        print("\n  ❌ не нашёл поля. Дамп формы выше — посмотри, какие имена реальные.")
        return 1

    # Имя кнопки submit — найдём отдельно
    submit_button = None
    form_tag = soup.find("form")
    if form_tag:
        for btn in form_tag.find_all(["input", "button"]):
            if btn.get("type") == "submit":
                submit_button = btn.get("name")
                if submit_button:
                    print(f"     кнопка    = {submit_button!r}")
                    break

    # Пробуем ОДНУ дату чтобы увидеть полный ответ. Если будет 402 — печатаем
    # тело целиком и разбираемся, потом расширим до 3 дат.
    test_dates = [
        "15-01-2024",
    ]

    print(f"\n[3/3] пробуем {len(test_dates)} дату…")
    for d in test_dates:
        check_one(session, fields, inn_field, date_field, inn, d, submit_button)

    print("\n" + "=" * 70)
    print("ИТОГ:")
    print("Если хоть одна проверка вернула 'является' / 'не является' — рабочий путь найден.")
    print("Если ни одна — нужно смотреть body-дамп выше и подкручивать.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
