# -*- coding: utf-8 -*-
"""
RMSP-PP cross-validator — проверяет, что фильтр `sk=SZ` действительно
отдаёт только чистых физиков-самозанятых.

Берёт N случайных ИНН из выдачи rmsp-pp по региону и каждый прогоняет через:
  1. egrul.nalog.ru   — должен НЕ найти (если найден → засветился как ИП)
  2. statusnpd.nalog.ru — должен сказать "является плательщиком" сегодня
  3. rusprofile.ru     — должен НЕ найти (если найден → агрегатор знает про ИП)

Если все 3 проверки чистые на каждом ИНН — фильтр sk=SZ надёжен,
EGRUL-верификатор в Pack 28 можно сделать опциональным.

Если хоть один ИНН засветился — нужен обязательный EGRUL-фильтр.

Использование:
    python rmsp_pp_validate.py
    python rmsp_pp_validate.py --kladr 7700000000000 --count 10  # Москва, 10 ИНН
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from typing import Optional

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
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def fetch_rmsp_inns(session: requests.Session, kladr: str, count: int) -> list[dict]:
    """Тянет случайные count ИНН из rmsp-pp с фильтром sk=SZ."""
    print(f"📥 запрос rmsp-pp для kladr={kladr} (sk=SZ)...")

    # Сначала узнаём общее количество, потом выбираем случайные страницы
    base_params = {
        "m": "SupportExt",
        "kladr": kladr,
        "sk": "SZ",
        "pageSize": 100,
    }

    # Первый запрос — узнаём rowCount
    r = session.get(
        "https://rmsp-pp.nalog.ru/search-proc.json",
        params={**base_params, "page": 1},
        headers={**HEADERS, "Referer": "https://rmsp-pp.nalog.ru/search.html"},
        timeout=20,
    )
    if r.status_code != 200:
        print(f"  ❌ status {r.status_code}: {r.text[:200]}")
        return []

    data = r.json()
    row_count = data.get("rowCount", 0)
    page_count = data.get("pageCount", 1)
    print(f"  → всего записей: {row_count}, страниц: {page_count}")

    if row_count == 0:
        return []

    # Соберём пул ИНН с нескольких случайных страниц для разнообразия
    pages_to_fetch = min(3, page_count)
    sampled_pages = random.sample(range(1, page_count + 1), pages_to_fetch)
    pool: list[dict] = []
    for page in sampled_pages:
        if page != 1:
            r = session.get(
                "https://rmsp-pp.nalog.ru/search-proc.json",
                params={**base_params, "page": page},
                headers=HEADERS,
                timeout=20,
            )
            if r.status_code != 200:
                continue
            data = r.json()
        for row in data.get("data", []):
            inn = row.get("subject_inn")
            if inn and len(inn) == 12:
                pool.append({
                    "inn": inn,
                    "name": row.get("subject_name"),
                    "nptype": row.get("subject_nptype"),
                    "region": row.get("subject_region"),
                    "ogrn": row.get("subject_ogrn"),  # должно быть None/пусто
                })

    # Уникализация по ИНН (один человек может иметь несколько записей о поддержке)
    unique = {}
    for item in pool:
        unique[item["inn"]] = item
    pool = list(unique.values())
    print(f"  → уникальных ИНН в пуле: {len(pool)}")

    if len(pool) <= count:
        return pool
    return random.sample(pool, count)


def check_egrul(session: requests.Session, inn: str) -> Optional[bool]:
    """True = найден (есть ИП/ЮЛ), False = чистый физик, None = ошибка."""
    payload = {
        "vyp3CaptchaToken": "",
        "page": "",
        "query": inn,
        "region": "",
        "PreventChromeAutocomplete": "",
    }
    try:
        r = session.post("https://egrul.nalog.ru/", data=payload,
                         headers=HEADERS, timeout=15)
        token = r.json().get("t")
        if not token:
            return None
        r2 = session.get(f"https://egrul.nalog.ru/search-result/{token}",
                         headers=HEADERS, timeout=15)
        rows = r2.json().get("rows", [])
        total = sum(max(int(row.get("cnt", "0") or "0"),
                        int(row.get("tot", "0") or "0")) for row in rows)
        return total > 0
    except (requests.RequestException, json.JSONDecodeError, ValueError):
        return None


def check_npd_today(session: requests.Session, inn: str) -> Optional[bool]:
    """True = плательщик НПД сегодня, False = нет, None = ошибка."""
    from datetime import date
    payload = {"inn": inn, "requestDate": date.today().isoformat()}
    try:
        r = session.post(
            "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status",
            json=payload,
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        return bool(r.json().get("status"))
    except (requests.RequestException, json.JSONDecodeError):
        return None


def check_rusprofile(session: requests.Session, inn: str) -> Optional[bool]:
    """
    True = найден на rusprofile (засветился как ИП/ЮЛ), False = не найден.
    Парсим title или начало HTML.
    """
    try:
        r = session.get(
            f"https://rusprofile.ru/search?query={inn}",
            headers={
                **HEADERS,
                "Accept": ("text/html,application/xhtml+xml,application/xml;"
                           "q=0.9,*/*;q=0.8"),
            },
            timeout=15,
        )
        if r.status_code != 200:
            return None
        text_lower = r.text.lower()
        if "найдены 0 организаций и 0 индивидуальных предпринимателей" in text_lower:
            return False
        if "попробуйте изменить поисковый запрос" in text_lower:
            return False
        # Если страница содержит карточку организации/ИП — там будет блок results
        if "search-results" in text_lower or "company-item" in text_lower:
            return True
        # На всякий случай — если найдено что-то конкретное по ИНН
        if f'инн {inn}' in text_lower or f'>{inn}<' in text_lower:
            return True
        return False
    except requests.RequestException:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kladr", default="2300000000000",
                        help="код kladr региона (default: Краснодарский край)")
    parser.add_argument("--count", type=int, default=10,
                        help="сколько ИНН проверить (default: 10)")
    args = parser.parse_args()

    random.seed()
    session = requests.Session()
    # warmup
    session.get("https://rmsp-pp.nalog.ru/", headers=HEADERS, timeout=15)

    sample = fetch_rmsp_inns(session, args.kladr, args.count)
    if not sample:
        print("❌ не удалось получить ИНН из rmsp-pp")
        return 1

    print(f"\n🧪 проверяю {len(sample)} ИНН по 3 источникам:\n")

    print(f"  {'ИНН':<14} {'EGRUL':<10} {'NPD сегодня':<14} {'rusprofile':<12} {'ФИО':<40}")
    print("  " + "─" * 95)

    results = []
    for item in sample:
        inn = item["inn"]
        name = (item.get("name") or "").strip()[:38]

        eg = check_egrul(session, inn)
        time.sleep(0.4)
        npd = check_npd_today(session, inn)
        time.sleep(0.4)
        rp = check_rusprofile(session, inn)
        time.sleep(0.4)

        eg_str = ("❌ найден" if eg is True
                  else "✅ нет" if eg is False
                  else "⚠️ err")
        npd_str = ("✅ да" if npd is True
                   else "❌ нет" if npd is False
                   else "⚠️ err")
        rp_str = ("❌ найден" if rp is True
                  else "✅ нет" if rp is False
                  else "⚠️ err")

        clean = (eg is False and npd is True and rp is False)
        marker = "✓" if clean else "✗" if (eg is True or rp is True or npd is False) else "?"

        print(f"{marker} {inn:<14} {eg_str:<10} {npd_str:<14} {rp_str:<12} {name:<40}")
        results.append({
            "inn": inn, "egrul": eg, "npd": npd, "rusprofile": rp, "clean": clean
        })

    print()
    print("=" * 70)
    clean_count = sum(1 for r in results if r["clean"])
    dirty_count = sum(
        1 for r in results
        if r["egrul"] is True or r["rusprofile"] is True or r["npd"] is False
    )
    err_count = len(results) - clean_count - dirty_count

    print(f"  Чистых: {clean_count}/{len(results)}")
    print(f"  Грязных (засветились или сняты с НПД): {dirty_count}/{len(results)}")
    print(f"  С ошибками проверки: {err_count}/{len(results)}")
    print()

    if dirty_count == 0 and err_count == 0:
        print("  ✅ ВСЕ ЧИСТЫЕ — фильтр sk=SZ работает идеально.")
        print("     EGRUL-верификатор в Pack 28 можно сделать опциональным или убрать.")
    elif dirty_count > 0:
        print("  ⚠️  ЕСТЬ ГРЯЗНЫЕ — фильтр пропускает либо ИПшников,")
        print("     либо снятых с НПД. Pack 28 ОБЯЗАН делать пост-проверку.")
    else:
        print("  ⚠️  Часть проверок не прошла (network/captcha).")
        print("     Запустить ещё раз для статистики.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
