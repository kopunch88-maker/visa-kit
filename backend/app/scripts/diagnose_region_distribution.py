"""
Pack 17.6 / 18.0 — диагностика распределения записей по регионам.

Запускать ЛОКАЛЬНО против прод-БД для проверки что миграции прошли успешно
и что в каждом из наших 10 регионов есть достаточно свободных кандидатов.

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    .venv\\Scripts\\Activate.ps1
    $env:DATABASE_URL = "postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"
    python -m app.scripts.diagnose_region_distribution
"""
from __future__ import annotations

import sys

from sqlalchemy import text
from sqlmodel import Session

from app.db.session import engine


# Наши 10 целевых регионов и их коды (= первые 2 цифры ИНН)
TARGET_REGIONS = {
    77: "Москва",
    78: "Санкт-Петербург",
    23: "Краснодарский край (Сочи + Краснодар)",
    61: "Ростовская область",
    5:  "Республика Дагестан (Махачкала)",
    20: "Чеченская Республика (Грозный)",
    16: "Республика Татарстан (Казань)",
    2:  "Республика Башкортостан (Уфа)",
    52: "Нижегородская область",
}

# Минимальный порог "запас на полгода" (50 заявок/мес × 6 мес = 300, но
# не все регионы поровну — диаспорный fallback может разгрузить)
MIN_THRESHOLD = 200


def main() -> int:
    print("=" * 80)
    print("Pack 17.6 — диагностика распределения по регионам")
    print("=" * 80)

    with Session(engine) as s:
        # Проверяем что колонка существует
        col = s.exec(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'self_employed_registry' AND column_name = 'region_code'
        """)).first()

        if not col:
            print("\n❌ ОШИБКА: колонка region_code не найдена в self_employed_registry")
            print("   Запустите миграцию Pack 17.6 (рестарт backend применит автоматически)")
            return 1

        # Общая статистика
        total_row = s.exec(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_used = FALSE THEN 1 ELSE 0 END) AS available,
                SUM(CASE WHEN region_code IS NULL THEN 1 ELSE 0 END) AS null_region
            FROM self_employed_registry
        """)).first()

        total, available, null_region = total_row[0], total_row[1], total_row[2]
        print(f"\n📊 Общая статистика реестра:")
        print(f"   total:        {total:,}")
        print(f"   available:    {available:,} (is_used=FALSE)")
        print(f"   null_region:  {null_region:,} (должно быть 0!)")

        if null_region > 0:
            print(f"\n⚠️  WARNING: {null_region} записей с NULL region_code")
            print("   Это означает что backfill не отработал полностью")

        # Распределение по нашим 10 целевым регионам
        print(f"\n📍 Целевые регионы (10):")
        print(f"   {'Code':<5} {'Название':<45} {'Total':>10} {'Free':>10}  Status")
        print(f"   {'-'*5} {'-'*45} {'-'*10} {'-'*10}  {'-'*15}")

        weak_regions = []
        for code, name in TARGET_REGIONS.items():
            row = s.exec(text("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_used = FALSE THEN 1 ELSE 0 END) AS free
                FROM self_employed_registry
                WHERE region_code = :rc
            """).bindparams(rc=code)).first()

            t, f = (row[0] or 0), (row[1] or 0)
            status = "✅ OK" if f >= MIN_THRESHOLD else f"⚠️  LOW (<{MIN_THRESHOLD})"
            if f < MIN_THRESHOLD:
                weak_regions.append((code, name, f))
            print(f"   {code:>5} {name:<45} {t:>10,} {f:>10,}  {status}")

        # Топ-15 регионов по объёму (общая картина)
        print(f"\n🏆 Топ-15 регионов в реестре (для понимания распределения):")
        rows = s.exec(text("""
            SELECT
                region_code,
                COUNT(*) AS total,
                SUM(CASE WHEN is_used = FALSE THEN 1 ELSE 0 END) AS free
            FROM self_employed_registry
            GROUP BY region_code
            ORDER BY total DESC
            LIMIT 15
        """)).all()
        for r in rows:
            in_target = " ← target" if r[0] in TARGET_REGIONS else ""
            print(f"   {r[0]:>5}: {r[1]:>10,} total, {r[2]:>10,} free{in_target}")

        # Итог
        if not weak_regions:
            print(f"\n✅ Все целевые регионы имеют ≥{MIN_THRESHOLD} свободных кандидатов")
        else:
            print(f"\n⚠️  Слабые регионы (нужен tier-fallback):")
            for code, name, free in weak_regions:
                print(f"   {code:>5} {name}: {free} свободных")
            print("\n   Это ожидаемо для Дагестана/Чечни — для них Pack 18 настроит")
            print("   автоматический fallback на диаспорный регион (Сочи / Москва).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
