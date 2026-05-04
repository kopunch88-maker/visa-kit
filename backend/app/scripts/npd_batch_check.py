"""
Pack 18.2.3 — Локальный batch-чекер статуса НПД.

Зачем:
    ФНС API заблокировал Railway-IP (зафиксировано 04.05.2026, см. PROJECT_STATE).
    `inn-accept` на бэке теперь идёт по ветке "skipped_fns_unavailable" — ИНН
    выдаётся клиенту БЕЗ live-проверки. В UI это видно как серая плашка
    "Не проверен" (Pack 18.5).

    Этот скрипт запускается ЛОКАЛЬНО на твоём ПК (домашний IP не блокируется),
    проходит по applicant'ам и проверяет их ИНН через ФНС. Результаты пишутся
    в self_employed_registry → плашка в UI становится зелёной "Проверен ФНС"
    или красной "Не действителен".

Использование:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    python -m app.scripts.npd_batch_check                        # только не проверенные
    python -m app.scripts.npd_batch_check --recheck-old 7        # + переписать старше 7 дней

Сценарий:
    1. Скрипт находит applicant'ов с inn IS NOT NULL
    2. Фильтрует по режиму:
        - default:  last_npd_check_at IS NULL (никогда не проверяли)
        - --recheck-old N:  + last_npd_check_at < (today - N дней)
    3. Проверяет каждый ИНН через ФНС (NpdStatusChecker, 31 сек между запросами)
    4. Пишет в self_employed_registry:
        - is_active=True  → last_npd_check_at = now()
        - is_active=False → is_invalid=True + last_npd_check_at = now()
    5. В конце выводит сводку: сколько confirmed / invalid / errors
       + список invalid ИНН с фамилией клиента и номером заявки

Применение результата на фронте:
    Менеджер увидит:
    - 🟢 "Проверен ФНС <дата>" — если confirmed (как раньше)
    - 🔴 "Не действителен (ФНС подтвердил отзыв)" — если invalid
    - менеджер сам решает: перевыдать ИНН? связаться с клиентом? и т.д.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("npd_batch_check")
# Заглушаем многословный httpx INFO о каждом запросе
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Тот же паттерн что в import_dump_local.py — берём DATABASE_URL из env или .env.local
ENV_FILE = Path(__file__).resolve().parents[3] / ".env.local"


def _redact_url(url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def load_or_prompt_database_url() -> str:
    """Копия логики из import_dump_local — env > .env.local > prompt."""
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        log.info("Using DATABASE_URL from environment")
        return env_url

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if url:
                    log.info(f"Using DATABASE_URL from {ENV_FILE}")
                    return url

    print()
    print("=" * 70)
    print("Нужен DATABASE_PUBLIC_URL от Railway Postgres")
    print("=" * 70)
    print("Где взять: Railway → проект visa-kit → Postgres → Variables → DATABASE_PUBLIC_URL")
    print()
    url = input("DATABASE_URL: ").strip()
    if not url.startswith("postgresql://") and not url.startswith("postgres://"):
        log.error("Это не похоже на postgres URL.")
        sys.exit(1)

    ENV_FILE.write_text(f'DATABASE_URL="{url}"\n', encoding="utf-8")
    log.info(f"DATABASE_URL сохранён в {ENV_FILE}")
    return url


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pack 18.2.3 — batch-проверка статуса НПД через ФНС с домашнего ПК",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--recheck-old",
        type=int,
        metavar="N",
        default=None,
        help=(
            "Помимо НИКОГДА НЕ проверенных, также перепроверить тех чья последняя "
            "проверка старше N дней. По умолчанию — только не проверенные."
        ),
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить число проверяемых записей (полезно для smoke-тестов).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать список — не делать запросы в ФНС, ничего не писать в БД.",
    )
    p.add_argument(
        "--no-rate-limit",
        action="store_true",
        help=(
            "Отключить 31-секундную задержку между запросами. ИСПОЛЬЗОВАТЬ ОСТОРОЖНО — "
            "ФНС лимитирует 2 req/min, можем получить блокировку."
        ),
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Поиск кандидатов на проверку
# ---------------------------------------------------------------------------

def find_candidates(engine, recheck_old_days: Optional[int], limit: Optional[int]) -> list[dict]:
    """
    Возвращает список словарей {applicant_id, inn, last_check, last_name, first_name, reference}
    для applicant'ов которые нужно проверить.

    Используем raw SQL через text() — безопаснее чем угадывать с ORM-полями моделей
    (у Application reference и applicant_id это точно, у Applicant inn и last_name_native
    тоже — мы их видели в _enrich() в applicants.py).
    """
    from sqlalchemy import text

    # Базовое условие: applicant имеет ИНН и есть запись в реестре
    where_parts = ["a.inn IS NOT NULL", "a.inn != ''", "r.inn IS NOT NULL"]

    if recheck_old_days is None:
        # Дефолт — только никогда не проверенные
        where_parts.append("r.last_npd_check_at IS NULL")
    else:
        # И никогда не проверенные, И старые
        cutoff = datetime.utcnow() - timedelta(days=recheck_old_days)
        where_parts.append(
            f"(r.last_npd_check_at IS NULL OR r.last_npd_check_at < '{cutoff.isoformat()}')"
        )

    # is_invalid=True пропускаем — нет смысла перепроверять то что уже отозвано ФНС
    where_parts.append("(r.is_invalid IS NULL OR r.is_invalid = FALSE)")

    where_sql = " AND ".join(where_parts)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""

    # LEFT JOIN application по applicant_id — если заявок несколько, берём самую свежую
    # через ORDER BY app.id DESC и DISTINCT ON applicant_id
    sql = f"""
        SELECT DISTINCT ON (a.id)
               a.id AS applicant_id,
               a.inn AS inn,
               a.last_name_native AS last_name,
               a.first_name_native AS first_name,
               r.last_npd_check_at AS last_check,
               app.reference AS reference
        FROM applicant a
        JOIN self_employed_registry r ON r.inn = a.inn
        LEFT JOIN application app ON app.applicant_id = a.id
        WHERE {where_sql}
        ORDER BY a.id DESC, app.id DESC
        {limit_sql}
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Async-проверка через NpdStatusChecker
# ---------------------------------------------------------------------------

async def check_one(checker, candidate: dict) -> dict:
    """
    Проверяет один ИНН. Возвращает обновлённый dict с полями:
      result_status: "confirmed" | "invalid" | "error"
      result_message: str (для error — текст исключения)
      registration_date: date | None (для confirmed)
    """
    from app.services.inn_generator.npd_status import NpdStatusError

    inn = candidate["inn"]
    try:
        res = await checker.check(inn=inn)
        if res.is_active:
            return {
                **candidate,
                "result_status": "confirmed",
                "result_message": (res.message or "")[:200],
                "registration_date": res.registration_date,
            }
        else:
            return {
                **candidate,
                "result_status": "invalid",
                "result_message": (res.message or "ФНС вернул status=False")[:200],
                "registration_date": None,
            }
    except NpdStatusError as e:
        return {
            **candidate,
            "result_status": "error",
            "result_message": str(e)[:200],
            "registration_date": None,
        }
    except Exception as e:
        return {
            **candidate,
            "result_status": "error",
            "result_message": f"{type(e).__name__}: {e}"[:200],
            "registration_date": None,
        }


async def run_checks(candidates: list[dict], no_rate_limit: bool) -> list[dict]:
    """Прогоняет всех кандидатов через checker. Последовательно — иначе rate-limit."""
    from app.services.inn_generator.npd_status import NpdStatusChecker

    results = []
    async with NpdStatusChecker(respect_rate_limit=not no_rate_limit) as checker:
        for i, cand in enumerate(candidates, start=1):
            name = f"{cand.get('last_name') or ''} {cand.get('first_name') or ''}".strip() or "?"
            ref = cand.get("reference") or "—"
            log.info(
                f"[{i}/{len(candidates)}] Проверяю inn={cand['inn']} "
                f"(applicant_id={cand['applicant_id']}, {name}, {ref})..."
            )

            t0 = time.time()
            result = await check_one(checker, cand)
            elapsed = time.time() - t0

            status = result["result_status"]
            icon = {"confirmed": "🟢", "invalid": "🔴", "error": "⚠️ "}[status]
            log.info(
                f"  {icon} {status} ({elapsed:.1f}s) — {result['result_message'][:120]}"
            )
            results.append(result)
    return results


# ---------------------------------------------------------------------------
# Запись результатов
# ---------------------------------------------------------------------------

def apply_results(engine, results: list[dict], dry_run: bool) -> None:
    """
    Пишет результаты в self_employed_registry:
      confirmed → last_npd_check_at = now()
      invalid   → is_invalid = TRUE, last_npd_check_at = now()
      error     → ничего не трогаем (ФНС ответил странно — лучше перепроверить позже)
    """
    if dry_run:
        log.info("DRY-RUN: пропускаем запись в БД")
        return

    from sqlalchemy import text

    now = datetime.utcnow()
    confirmed_inns = [r["inn"] for r in results if r["result_status"] == "confirmed"]
    invalid_inns = [r["inn"] for r in results if r["result_status"] == "invalid"]

    with engine.connect() as conn:
        if confirmed_inns:
            conn.execute(
                text(
                    "UPDATE self_employed_registry SET last_npd_check_at = :now "
                    "WHERE inn = ANY(:inns)"
                ),
                {"now": now, "inns": confirmed_inns},
            )
            log.info(f"Обновлено confirmed: {len(confirmed_inns)} записей")

        if invalid_inns:
            conn.execute(
                text(
                    "UPDATE self_employed_registry "
                    "SET is_invalid = TRUE, last_npd_check_at = :now "
                    "WHERE inn = ANY(:inns)"
                ),
                {"now": now, "inns": invalid_inns},
            )
            log.warning(f"Помечено is_invalid=True: {len(invalid_inns)} записей")

        conn.commit()


# ---------------------------------------------------------------------------
# Сводная таблица в конце
# ---------------------------------------------------------------------------

def print_summary(results: list[dict]) -> None:
    confirmed = [r for r in results if r["result_status"] == "confirmed"]
    invalid = [r for r in results if r["result_status"] == "invalid"]
    errors = [r for r in results if r["result_status"] == "error"]

    print()
    print("=" * 70)
    print("СВОДКА")
    print("=" * 70)
    print(f"Всего проверено:  {len(results)}")
    print(f"  🟢 Confirmed:   {len(confirmed)}  (статус НПД подтверждён)")
    print(f"  🔴 Invalid:     {len(invalid)}  (ФНС подтвердил отзыв)")
    print(f"  ⚠️  Errors:      {len(errors)}  (ФНС не ответил, нужна повторная проверка)")
    print()

    if invalid:
        print("=" * 70)
        print("⚠️  ИНН СТАЛИ НЕДЕЙСТВИТЕЛЬНЫ — рассмотри перевыдачу:")
        print("=" * 70)
        for r in invalid:
            name = f"{r.get('last_name') or ''} {r.get('first_name') or ''}".strip() or "?"
            ref = r.get("reference") or "—"
            print(f"  · applicant_id={r['applicant_id']}  inn={r['inn']}  "
                  f"{name}  заявка {ref}")
            print(f"      → {r['result_message']}")
        print()
        print("В UI у этих клиентов появится 🔴 КРАСНАЯ плашка \"Не действителен\".")
        print("Документы которые уже выданы — НЕ отозваны автоматически.")
        print("Сам решай: перевыдать ИНН через ✨, связаться с клиентом и т.д.")
        print()

    if errors:
        print("=" * 70)
        print("⚠️  ИНН с ошибками проверки (повтори запуск позже):")
        print("=" * 70)
        for r in errors:
            print(f"  · applicant_id={r['applicant_id']}  inn={r['inn']}")
            print(f"      → {r['result_message']}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    database_url = load_or_prompt_database_url()
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    os.environ["DATABASE_URL"] = database_url

    log.info(f"Connecting to: {_redact_url(database_url)}")

    # Импортируем после того как DATABASE_URL уже в env (мало ли где-то модули
    # читают его при импорте)
    from sqlalchemy import create_engine

    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 30,
            "options": "-c statement_timeout=60000",
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )

    # Поиск кандидатов
    log.info("Ищу кандидатов на проверку...")
    candidates = find_candidates(
        engine,
        recheck_old_days=args.recheck_old,
        limit=args.limit,
    )
    log.info(f"Найдено: {len(candidates)} кандидатов")

    if not candidates:
        log.info("Нечего проверять. Выход.")
        return

    # Прогноз времени
    if args.no_rate_limit:
        eta_min = len(candidates) * 0.5 / 60  # ~0.5s на запрос без задержки
        log.info(f"Без rate-limit — ожидаемое время ~{eta_min:.1f} мин")
    else:
        eta_sec = len(candidates) * 31  # 31 секунда между запросами
        log.info(f"С rate-limit (31 сек/запрос) — ожидаемое время ~{eta_sec / 60:.1f} мин")

    # Подтверждение
    print()
    print("=" * 70)
    print(f"ГОТОВО К ПРОВЕРКЕ {len(candidates)} ИНН")
    print("=" * 70)
    print(f"База:           {_redact_url(database_url)}")
    print(f"Режим:          {'recheck-old=' + str(args.recheck_old) if args.recheck_old else 'только не проверенные'}")
    print(f"Rate-limit:     {'ОТКЛЮЧЕН (рискованно)' if args.no_rate_limit else '31 сек между запросами'}")
    print(f"Dry-run:        {'ДА (без записи в БД)' if args.dry_run else 'НЕТ — БД будет обновлена'}")
    print()

    if args.dry_run:
        # В dry-run режиме просто показываем список и выходим
        print("Список кандидатов (dry-run, проверка ФНС НЕ выполняется):")
        for c in candidates:
            name = f"{c.get('last_name') or ''} {c.get('first_name') or ''}".strip() or "?"
            ref = c.get("reference") or "—"
            last = c.get("last_check") or "никогда"
            print(f"  · applicant_id={c['applicant_id']}  inn={c['inn']}  "
                  f"{name}  {ref}  last_check={last}")
        return

    confirm = input("Продолжить? (yes/no): ").strip().lower()
    if confirm not in ("y", "yes", "да", "д"):
        log.info("Отменено пользователем")
        return

    # Прогон проверок
    started = time.time()
    log.info("=" * 70)
    log.info("СТАРТ ПРОВЕРКИ")
    log.info("=" * 70)

    results = asyncio.run(run_checks(candidates, no_rate_limit=args.no_rate_limit))

    elapsed = time.time() - started
    log.info(f"Проверка завершена за {elapsed / 60:.1f} мин")

    # Запись результатов
    apply_results(engine, results, dry_run=args.dry_run)

    # Сводка
    print_summary(results)


if __name__ == "__main__":
    main()
