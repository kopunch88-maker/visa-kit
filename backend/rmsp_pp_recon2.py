# -*- coding: utf-8 -*-
"""
RMSP-PP search-proc.json — финальная разведка JSON API.

Что выясняем:
  1. Какой набор параметров в запросе соответствует «Физлицо НПД»
     (галка в браузерной форме которую Костя ставил).
  2. Можно ли пагинировать большие выдачи.
  3. Какие subject_nptype бывают в реальных данных и как
     отфильтровать только наших — самозанятых физиков.

Стратегия:
  - GET search-proc.json?...&kladr=... с разными комбинациями параметров.
  - Считаем какие subject_nptype вернулись.
  - Проверяем что фильтр по NP_FL даёт только нужных.

Использование:
    python rmsp_pp_recon2.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter

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
    "Referer": "https://rmsp-pp.nalog.ru/search.html",
}


def line(c="="):
    print(c * 70)


def fetch(session: requests.Session, params: dict, label: str) -> dict | None:
    line()
    print(f"  {label}")
    print(f"  params: {params}")
    line("-")
    url = "https://rmsp-pp.nalog.ru/search-proc.json"
    try:
        r = session.get(url, params=params, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"  ❌ {e}")
        return None
    print(f"  ← status: {r.status_code}, len: {len(r.text)}")
    if r.status_code != 200:
        print(f"  ← body: {r.text[:500]}")
        return None
    try:
        data = r.json()
    except json.JSONDecodeError as e:
        print(f"  ❌ не JSON: {e}")
        return None

    rows = data.get("data") or []
    print(f"  ← записей в data: {len(rows)}")
    print(f"  ← top-level keys: {list(data.keys())}")
    print(f"  ← всё кроме data: " + json.dumps(
        {k: v for k, v in data.items() if k != "data"}, ensure_ascii=False
    ))

    if rows:
        # Распределение nptype и category и наличия ОГРН
        nptype_dist = Counter(row.get("subject_nptype") for row in rows)
        category_dist = Counter(row.get("subject_category") for row in rows)
        has_ogrn = sum(1 for row in rows if row.get("subject_ogrn"))
        no_ogrn = len(rows) - has_ogrn

        print(f"  ← subject_nptype:    {dict(nptype_dist)}")
        print(f"  ← subject_category:  {dict(category_dist)}")
        print(f"  ← с ОГРН/ОГРНИП:     {has_ogrn}/{len(rows)}")
        print(f"  ← без ОГРН (физики): {no_ogrn}/{len(rows)}")

        print(f"\n  Образец первой записи:")
        sample = {k: v for k, v in rows[0].items()}
        print("  " + json.dumps(sample, ensure_ascii=False, indent=2)[:1000])

        # Если есть записи без ОГРН — покажем одну для контраста
        for row in rows:
            if not row.get("subject_ogrn"):
                print(f"\n  Образец записи без ОГРН (предположительно физик-НПД):")
                print("  " + json.dumps(
                    {k: v for k, v in row.items()},
                    ensure_ascii=False, indent=2
                )[:1000])
                break

    return data


def main() -> int:
    session = requests.Session()
    # Прогрев — чтобы получить JSESSIONID как браузер
    session.get("https://rmsp-pp.nalog.ru/", headers=HEADERS, timeout=15)

    KRAS = "2300000700000"  # Краснодарский край (Сочи)

    # Эксперимент 1: пустые параметры — посмотрим что вернётся по умолчанию
    fetch(session, {"m": "SupportExt", "kladr": KRAS}, "1. без доп. параметров")

    # Эксперимент 2: sk=SZ (это что в URL у Кости было — возможно
    # «Самозанятые»?)
    fetch(session, {"m": "SupportExt", "kladr": KRAS, "sk": "SZ"},
          "2. sk=SZ (которое было в URL у Кости)")

    # Эксперимент 3: sk=SZ + признак НПД
    # Параметр обычно называется subject_nptype или sub_type
    for cand_param, cand_value in [
        ("subject_nptype", "FL"),
        ("subject_nptype", "NP_FL"),
        ("nptype", "FL"),
        ("subject_category", "4"),  # м.б. категория физиков-НПД
        ("subject_category", "3"),
        ("kategFLP", "1"),  # видел такое в формах ФНС
    ]:
        fetch(
            session,
            {"m": "SupportExt", "kladr": KRAS, "sk": "SZ", cand_param: cand_value},
            f"3. {cand_param}={cand_value}",
        )

    # Эксперимент 4: пагинация
    fetch(session, {"m": "SupportExt", "kladr": KRAS, "sk": "SZ",
                    "page": 1, "pageSize": 100},
          "4. пагинация: page=1, pageSize=100")

    line()
    print("Что искать в выводе:")
    print(" • Запрос на котором ВСЕ записи без ОГРН — это правильный фильтр для физиков-НПД")
    print(" • dtQueryEnd/dtQueryBegin показывают что данные real-time")
    print(" • pageCount=500 в первом ответе — возможно общее количество страниц или")
    print("   значение по умолчанию pageSize")
    return 0


if __name__ == "__main__":
    sys.exit(main())
