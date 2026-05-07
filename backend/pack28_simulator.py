# -*- coding: utf-8 -*-
"""
Pack 28 SIMULATOR — эмулирует будущий верификатор Pack 28 на реальном объёме.

Задача:
  Пройти много кандидатов из rmsp-pp (например, 500-1000) и измерить:
    - какой % реально чистых
    - какой источник проверки самый надёжный (EGRUL vs rusprofile vs NPD)
    - сколько времени уходит на верификацию
    - какие источники падают под нагрузкой и как часто

  По итогу сможем уверенно принять решение по Pack 28:
    - какие чекеры включить в обязательную цепочку
    - сколько кандидатов в среднем нужно перебрать ради 1 чистого
    - реалистичен ли подход «лениво по запросу клиента» или нужен
      батчевый ночной верификатор

Использование:
    python pack28_simulator.py                          # 100 кандидатов из Краснодара
    python pack28_simulator.py --kladr 7700000000000 --total 200
    python pack28_simulator.py --skip-npd               # без NPD (он у тебя забанен)
    python pack28_simulator.py --total 500 --save-csv out.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import date
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


@dataclass
class Verdict:
    inn: str
    name: str = ""
    egrul: Optional[bool] = None        # True=найден ИП/ЮЛ, False=нет, None=err
    rusprofile: Optional[bool] = None   # True=найден, False=нет
    npd: Optional[bool] = None          # True=плательщик, False=нет
    egrul_err: str = ""
    rusprofile_err: str = ""
    npd_err: str = ""
    is_clean: bool = False              # итоговый вердикт

    def compute_clean(self, *, require_npd: bool) -> None:
        # Чистый = и в EGRUL не найден, и в rusprofile не найден,
        # и (опционально) подтверждён НПД-статус сегодня.
        clean = (self.egrul is False) and (self.rusprofile is False)
        if require_npd:
            clean = clean and (self.npd is True)
        self.is_clean = clean


# ─────────────────────────────────────────────────────────────────────────────
# Сборщик кандидатов из rmsp-pp
# ─────────────────────────────────────────────────────────────────────────────
def collect_candidates(session: requests.Session, kladr: str, target: int) -> list[dict]:
    """Идёт по страницам rmsp-pp и набирает уникальные ИНН пока не достигнет target."""
    url = "https://rmsp-pp.nalog.ru/search-proc.json"
    base = {"m": "SupportExt", "kladr": kladr, "sk": "SZ", "pageSize": 100}
    seen: dict[str, dict] = {}
    page = 1
    consecutive_empty = 0

    print(f"📥 собираю {target} уникальных ИНН из rmsp-pp (kladr={kladr})...")
    while len(seen) < target and consecutive_empty < 3:
        try:
            r = session.get(url, params={**base, "page": page},
                            headers={**HEADERS,
                                     "Referer": "https://rmsp-pp.nalog.ru/search.html"},
                            timeout=20)
        except requests.RequestException as e:
            print(f"  ⚠️  стр {page}: {e}; пауза 3 сек")
            time.sleep(3)
            continue

        if r.status_code != 200:
            print(f"  ⚠️  стр {page}: HTTP {r.status_code}")
            consecutive_empty += 1
            page += 1
            continue

        try:
            data = r.json()
        except json.JSONDecodeError:
            consecutive_empty += 1
            page += 1
            continue

        rows = data.get("data") or []
        if not rows:
            consecutive_empty += 1
            page += 1
            continue
        consecutive_empty = 0

        added = 0
        for row in rows:
            inn = row.get("subject_inn")
            if inn and len(inn) == 12 and inn not in seen:
                seen[inn] = {
                    "inn": inn,
                    "name": (row.get("subject_name") or "").strip(),
                    "region": row.get("subject_region"),
                }
                added += 1
                if len(seen) >= target:
                    break

        if page % 5 == 0 or added > 0:
            print(f"  стр {page}: {added} новых, всего {len(seen)}/{target}")
        page += 1
        time.sleep(0.2)

    print(f"  ✓ собрано {len(seen)} уникальных ИНН за {page - 1} страниц\n")
    return list(seen.values())


# ─────────────────────────────────────────────────────────────────────────────
# Чекеры
# ─────────────────────────────────────────────────────────────────────────────
def check_egrul(session: requests.Session, inn: str) -> tuple[Optional[bool], str]:
    payload = {"vyp3CaptchaToken": "", "page": "", "query": inn,
               "region": "", "PreventChromeAutocomplete": ""}
    try:
        r = session.post("https://egrul.nalog.ru/", data=payload,
                         headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None, f"http {r.status_code}"
        data = r.json()
        if data.get("captchaRequired"):
            return None, "captcha"
        token = data.get("t")
        if not token:
            return None, "no token"
        r2 = session.get(f"https://egrul.nalog.ru/search-result/{token}",
                         headers=HEADERS, timeout=15)
        rows = r2.json().get("rows", [])
        total = sum(max(int(row.get("cnt", "0") or "0"),
                        int(row.get("tot", "0") or "0")) for row in rows)
        return total > 0, ""
    except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
        return None, str(e)[:80]


def check_rusprofile(session: requests.Session, inn: str) -> tuple[Optional[bool], str]:
    try:
        r = session.get(
            f"https://rusprofile.ru/search?query={inn}",
            headers={**HEADERS,
                     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
            timeout=15,
        )
        if r.status_code != 200:
            return None, f"http {r.status_code}"
        text_lower = r.text.lower()
        # Маркеры «не найдено»
        not_found_markers = [
            "найдены 0 организаций и 0 индивидуальных предпринимателей",
            "попробуйте изменить поисковый запрос",
        ]
        for m in not_found_markers:
            if m in text_lower:
                return False, ""
        # Маркеры «найдено»
        found_markers = ["search-results", "company-item", f"инн {inn}"]
        for m in found_markers:
            if m in text_lower:
                return True, ""
        return False, ""
    except requests.RequestException as e:
        return None, str(e)[:80]


def check_npd(session: requests.Session, inn: str) -> tuple[Optional[bool], str]:
    payload = {"inn": inn, "requestDate": date.today().isoformat()}
    try:
        r = session.post(
            "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status",
            json=payload,
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code == 422:
            return False, "422 (не зарегистрирован)"
        if r.status_code != 200:
            return None, f"http {r.status_code}"
        return bool(r.json().get("status")), ""
    except (requests.RequestException, json.JSONDecodeError) as e:
        return None, str(e)[:80]


# ─────────────────────────────────────────────────────────────────────────────
# Основной цикл
# ─────────────────────────────────────────────────────────────────────────────
def verify_one(session: requests.Session, cand: dict, *,
               skip_npd: bool, throttle: float) -> Verdict:
    v = Verdict(inn=cand["inn"], name=cand.get("name", ""))

    v.egrul, v.egrul_err = check_egrul(session, v.inn)
    time.sleep(throttle)

    # Если EGRUL уже сказал «найден» — rusprofile/npd можно не дёргать
    # (всё равно отбросим). Но для статистики прогоним всё.
    v.rusprofile, v.rusprofile_err = check_rusprofile(session, v.inn)
    time.sleep(throttle)

    if not skip_npd:
        v.npd, v.npd_err = check_npd(session, v.inn)
        time.sleep(throttle)

    v.compute_clean(require_npd=not skip_npd)
    return v


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kladr", default="2300000000000",
                        help="kladr региона (default: Краснодарский край)")
    parser.add_argument("--total", type=int, default=100,
                        help="сколько кандидатов прогнать через верификатор")
    parser.add_argument("--throttle", type=float, default=0.5,
                        help="пауза между запросами, сек (default 0.5)")
    parser.add_argument("--skip-npd", action="store_true",
                        help="не дёргать NPD (он у нас часто банится)")
    parser.add_argument("--save-csv", default="",
                        help="путь для сохранения результатов в CSV")
    parser.add_argument("--shuffle", action="store_true", default=True,
                        help="перемешивать кандидатов перед прогоном (default true)")
    args = parser.parse_args()

    session = requests.Session()
    session.get("https://rmsp-pp.nalog.ru/", headers=HEADERS, timeout=15)

    # Шаг 1: сбор
    candidates = collect_candidates(session, args.kladr, args.total)
    if not candidates:
        print("❌ не получилось собрать ни одного кандидата")
        return 1
    if args.shuffle:
        random.shuffle(candidates)

    # Шаг 2: верификация
    print(f"🧪 верификация {len(candidates)} кандидатов "
          f"(throttle {args.throttle}s, NPD={'OFF' if args.skip_npd else 'ON'})\n")

    # Если есть save-csv — открываем сразу и пишем по ходу
    csv_writer = None
    csv_file = None
    if args.save_csv:
        csv_file = open(args.save_csv, "w", encoding="utf-8-sig", newline="")
        csv_writer = csv.DictWriter(
            csv_file, fieldnames=list(asdict(Verdict("x")).keys())
        )
        csv_writer.writeheader()
        csv_file.flush()
        print(f"  💾 чекпоинты пишутся в {args.save_csv} после каждого ИНН")
        print(f"     при остановке (Ctrl+C) промежуточные результаты сохранены\n")

    verdicts: list[Verdict] = []
    t_start = time.time()
    try:
        for i, cand in enumerate(candidates, 1):
            v = verify_one(session, cand, skip_npd=args.skip_npd, throttle=args.throttle)
            verdicts.append(v)

            # Чекпоинт в CSV
            if csv_writer:
                csv_writer.writerow(asdict(v))
                csv_file.flush()

            # Краткий лог каждые 10 или для чистых
            marker = "✓" if v.is_clean else (
                "✗" if (v.egrul is True or v.rusprofile is True or v.npd is False) else "?")
            if i % 10 == 0 or v.is_clean:
                elapsed = time.time() - t_start
                rate = i / elapsed
                print(f"  [{i:>4}/{len(candidates)}] {marker} {v.inn} "
                      f"egrul={v.egrul} rusprof={v.rusprofile} npd={v.npd} "
                      f"({rate:.1f} ИНН/сек)")
    except KeyboardInterrupt:
        print(f"\n  ⏸️  остановлено пользователем на {len(verdicts)}/{len(candidates)}")
        if csv_file:
            print(f"  ✓ {len(verdicts)} результатов сохранены в {args.save_csv}")
    finally:
        if csv_file:
            csv_file.close()

    # Шаг 3: статистика
    total = len(verdicts)
    if total == 0:
        print("\n  ничего не проверено")
        return 0
    elapsed = time.time() - t_start
    clean = sum(1 for v in verdicts if v.is_clean)
    egrul_found = sum(1 for v in verdicts if v.egrul is True)
    rusprof_found = sum(1 for v in verdicts if v.rusprofile is True)
    npd_active = sum(1 for v in verdicts if v.npd is True)
    egrul_err = sum(1 for v in verdicts if v.egrul is None)
    rusprof_err = sum(1 for v in verdicts if v.rusprofile is None)
    npd_err = sum(1 for v in verdicts if v.npd is None)

    # Сравнение источников: расхождения между EGRUL и rusprofile
    only_egrul = sum(1 for v in verdicts
                     if v.egrul is True and v.rusprofile is False)
    only_rusprof = sum(1 for v in verdicts
                       if v.egrul is False and v.rusprofile is True)
    both = sum(1 for v in verdicts
               if v.egrul is True and v.rusprofile is True)

    print()
    print("═" * 70)
    print(f"  ИТОГИ (верификация {total} кандидатов за {elapsed:.0f} сек, "
          f"≈{elapsed/total:.1f} сек/ИНН)")
    print("═" * 70)
    print(f"  ✅ Чистых:           {clean:>4} / {total}  ({100*clean/total:.1f}%)")
    print(f"     → 1 чистый на каждые {total/clean if clean else 0:.1f} проверенных")
    if clean:
        # Прикинем экстраполяцию: для ~50 заявок/мес сколько в день верификатор?
        per_chistyy_sec = elapsed / clean
        print(f"     → время на 1 чистого: ~{per_chistyy_sec:.0f} сек "
              f"({per_chistyy_sec/60:.1f} мин)")
        print(f"     → 50 чистых в месяц = ~{50*per_chistyy_sec/60:.0f} мин верификатора")
    print()
    print(f"  Засветились в EGRUL:      {egrul_found} ({100*egrul_found/total:.0f}%)")
    print(f"  Засветились в rusprofile: {rusprof_found} ({100*rusprof_found/total:.0f}%)")
    if not args.skip_npd:
        print(f"  Активны на НПД сегодня:   {npd_active} ({100*npd_active/total:.0f}%)")
    print()
    print(f"  ОШИБКИ (сетевые/бан):")
    print(f"    EGRUL err:       {egrul_err:>4} / {total}")
    print(f"    rusprofile err:  {rusprof_err:>4} / {total}")
    if not args.skip_npd:
        print(f"    NPD err:         {npd_err:>4} / {total}")
    print()
    print(f"  СРАВНЕНИЕ EGRUL vs rusprofile (только успешно проверенные):")
    print(f"    Только EGRUL нашёл:      {only_egrul}")
    print(f"    Только rusprofile нашёл: {only_rusprof}")
    print(f"    Оба нашли:               {both}")
    if only_rusprof == 0 and both > 0:
        print(f"    → rusprofile НИЧЕГО не добавляет, EGRUL достаточен")
    elif only_rusprof > 0:
        print(f"    → rusprofile ловит {only_rusprof} которых EGRUL пропустил — нужны ОБА")
    print()

    # Распределение примеров чистых
    print(f"  ПРИМЕРЫ ЧИСТЫХ ИНН (готовы к выдаче):")
    sample_clean = [v for v in verdicts if v.is_clean][:10]
    for v in sample_clean:
        print(f"    • {v.inn}  {v.name[:50]}")

    if args.save_csv:
        print(f"\n  💾 финальный CSV: {args.save_csv} ({len(verdicts)} строк)")

    print()
    print("═" * 70)
    print("  РЕКОМЕНДАЦИЯ ПО Pack 28:")
    if total == 0:
        print("  Недостаточно данных")
    elif clean / total >= 0.10:
        print(f"  ✅ КПД достаточный ({100*clean/total:.0f}%) — Pack 28 рабочий")
        print("     Верификатор гонять батчем заранее, держать в пуле buffer")
    elif clean / total >= 0.03:
        print(f"  ⚠️  КПД низкий ({100*clean/total:.0f}%) но рабочий — Pack 28 с большим буфером")
        print("     Верификатор должен поддерживать ~3x больше кандидатов чем нужно")
    else:
        print(f"  ❌ КПД очень низкий ({100*clean/total:.0f}%) — нужно искать другой источник")

    return 0


if __name__ == "__main__":
    sys.exit(main())
