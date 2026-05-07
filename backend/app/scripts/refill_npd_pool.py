"""
Pack 28 (07.05.2026) + Pack 28 Часть 2 (08.05.2026): CLI для пополнения пула.

Запускается на проде/локально для разовых операций — например, чтобы быстро
наполнить пул в Москве и СПб без ожидания cron.

USAGE:
    # Пополнить регион 23 (Краснодарский край) до 5 verified
    python -m app.scripts.refill_npd_pool --region 23 --target 5

    # Запустить ревалидацию всех verified старше 7 дней
    python -m app.scripts.refill_npd_pool --revalidate

    # Глобальный refill (как cron) — все ключевые регионы по 5 verified
    python -m app.scripts.refill_npd_pool --global

    # Показать статистику пула без изменений
    python -m app.scripts.refill_npd_pool --stats

ВАЖНО (Правило 36): использует Session(engine), а не get_session() который
является FastAPI dependency через yield.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from sqlmodel import Session

from app.db.session import engine
from app.models import NpdRefillTask
from app.services.inn_generator.npd_pool import (
    KEY_REGIONS,
    get_pool_stats,
    refill_pool_for_region,
    revalidate_verified_candidates,
    run_global_refill,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("refill_npd_pool")


def cmd_stats() -> None:
    """Показать статистику пула."""
    with Session(engine) as session:
        stats = get_pool_stats(session)
    print("=" * 60)
    print(f"Pool stats (total: {stats.total})")
    print("=" * 60)
    print("\nBy status:")
    for status, count in sorted(stats.by_status.items()):
        print(f"  {status:24} {count:>6}")
    print("\nVerified by region:")
    for region, count in sorted(stats.by_region_verified.items()):
        print(f"  region={region:2}  {count:>6}")
    print(f"\nLast refill at: {stats.last_refill_at}")
    print(f"Last refill region: {stats.last_refill_region}")


async def cmd_region(region_code: str, target: int) -> None:
    """Пополнить один регион (без task)."""
    log.info("Refilling region=%s target=%d", region_code, target)
    with Session(engine) as session:
        result = await refill_pool_for_region(session, region_code, target=target)
    print("=" * 60)
    print(f"Refill region={region_code} done")
    print("=" * 60)
    print(f"  rmsp_fetched:        {result.rmsp_fetched}")
    print(f"  duplicates_skipped:  {result.duplicates_skipped}")
    print(f"  egrul_rejected:      {result.egrul_rejected}")
    print(f"  npd_rejected:        {result.npd_rejected}")
    print(f"  verified_added:      {result.verified_added}")
    print(f"  errors:              {result.errors}")
    print(f"  elapsed:             {result.elapsed_seconds:.1f} sec")


async def cmd_revalidate(max_age_days: int) -> None:
    """Ревалидация всех verified."""
    log.info("Revalidating verified candidates (max_age_days=%d)", max_age_days)
    with Session(engine) as session:
        result = await revalidate_verified_candidates(
            session, max_age_days=max_age_days,
        )
    print("=" * 60)
    print("Revalidate done")
    print("=" * 60)
    print(f"  total checked:    {result['total']}")
    print(f"  invalidated:      {result['invalidated']}")
    print(f"  still_valid:      {result['still_valid']}")


async def cmd_global(target_per_region: int, no_revalidate: bool) -> None:
    """Глобальный refill (как cron)."""
    log.info(
        "Global refill: regions=%s target_per_region=%d revalidate=%s",
        KEY_REGIONS, target_per_region, not no_revalidate,
    )

    # Создаём task для прогресса (используется в логах)
    with Session(engine) as session:
        task = NpdRefillTask(
            kind="global",
            status="pending",
            progress_text="CLI: starting global refill...",
            progress_total=len(KEY_REGIONS) * target_per_region,
            triggered_by="cli:refill_npd_pool",
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id

    log.info("Created global refill task_id=%s", task_id)

    with Session(engine) as session:
        await run_global_refill(
            session=session,
            task_id=task_id or 0,
            regions=list(KEY_REGIONS),
            target_per_region=target_per_region,
            revalidate_first=not no_revalidate,
        )

    # Финальная статистика
    with Session(engine) as session:
        task = session.get(NpdRefillTask, task_id)
        print("=" * 60)
        print(f"Global refill done (task_id={task_id})")
        print("=" * 60)
        if task:
            print(f"  status:                 {task.status}")
            print(f"  verified_added:         {task.verified_added}")
            print(f"  egrul_rejected:         {task.egrul_rejected}")
            print(f"  npd_rejected:           {task.npd_rejected}")
            print(f"  revalidated_total:      {task.revalidated_total}")
            print(f"  revalidated_invalidated:{task.revalidated_invalidated}")
            print(f"  error:                  {task.error}")
            print(f"  elapsed:                {task.finished_at - task.started_at if task.finished_at and task.started_at else '?'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pack 28 Часть 2 — CLI пополнения пула самозанятых",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stats", action="store_true",
                       help="Показать статистику пула")
    group.add_argument("--region", type=str,
                       help="Пополнить один регион (2-значный код, '23')")
    group.add_argument("--revalidate", action="store_true",
                       help="Ревалидация всех verified")
    group.add_argument("--global", dest="global_refill", action="store_true",
                       help="Глобальный refill (как cron)")

    parser.add_argument("--target", type=int, default=5,
                        help="Сколько verified добавить (для --region и --global)")
    parser.add_argument("--max-age-days", type=int, default=7,
                        help="Минимальный возраст для ревалидации")
    parser.add_argument("--no-revalidate", action="store_true",
                        help="Для --global: пропустить шаг ревалидации")

    args = parser.parse_args()

    if args.stats:
        cmd_stats()
    elif args.region:
        asyncio.run(cmd_region(args.region, args.target))
    elif args.revalidate:
        asyncio.run(cmd_revalidate(args.max_age_days))
    elif args.global_refill:
        asyncio.run(cmd_global(args.target, args.no_revalidate))


if __name__ == "__main__":
    main()
