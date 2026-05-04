"""
Pack 19.1 — миграция справочников LegendCompany и CareerTrack
для генератора work_history.

Создаёт 2 таблицы:
- legend_company    (~70 записей — фейковые компании для CV-легенды)
- career_track      (28 записей — должности по специальности с уровнями 1-4)

Обе таблицы FK на specialty.id — поэтому ОБЯЗАТЕЛЬНО прогнать сначала
migration_pack19_0 (если ещё не прогонялся).

Pattern: bulk INSERT через единый VALUES + параметры :name0, :name1, ...
(копия паттерна из migration_pack19_0.py — медленный DELETE-loop через
Railway proxy висит на 10+ итерациях).

Идемпотентность:
- CREATE TABLE IF NOT EXISTS — можно перезапускать
- TRUNCATE RESTART IDENTITY CASCADE перед bulk INSERT — чистая перезаливка
  (если потом понадобится только UPDATE без TRUNCATE — отдельный скрипт
  типа migration_pack19_1_1.py по аналогии с 19.0.1)

Запуск:
  cd D:\\VISA\\visa_kit\\backend
  python -m app.scripts.migration_pack19_1
"""
from __future__ import annotations

import logging
from sqlalchemy import text

from app.db.session import engine
from app.seeds.legend_companies_seed import (
    CAREER_TRACKS_SEED,
    LEGEND_COMPANIES_SEED,
)

log = logging.getLogger(__name__)


def run() -> None:
    log.warning("[Pack 19.1] applying legend_company + career_track migration...")

    with engine.begin() as conn:
        # === 1. Проверяем что Pack 19.0 уже применён (specialty таблица есть) ===
        rows = conn.execute(
            text("SELECT code, id FROM specialty")
        ).all()
        specialty_id_map: dict[str, int] = {r.code: r.id for r in rows}

        if not specialty_id_map:
            raise RuntimeError(
                "Pack 19.1: таблица specialty пуста или отсутствует. "
                "Сначала прогоните migration_pack19_0 чтобы залить специальности."
            )

        log.warning(
            "[Pack 19.1] found %d specialties in DB",
            len(specialty_id_map),
        )

        # === 2. CREATE TABLE legend_company ===
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS legend_company (
                id SERIAL PRIMARY KEY,
                region_code VARCHAR(2) NOT NULL,
                city VARCHAR(128) NOT NULL,
                name_full VARCHAR(512) NOT NULL,
                name_short VARCHAR(256) NOT NULL,
                primary_specialty_id INTEGER NOT NULL
                    REFERENCES specialty(id) ON DELETE CASCADE,
                size VARCHAR(16) NOT NULL DEFAULT 'medium',
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_legend_company_region ON legend_company(region_code)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_legend_company_specialty ON legend_company(primary_specialty_id)"
        ))

        # === 3. CREATE TABLE career_track ===
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS career_track (
                id SERIAL PRIMARY KEY,
                specialty_id INTEGER NOT NULL
                    REFERENCES specialty(id) ON DELETE CASCADE,
                level INTEGER NOT NULL,
                title_ru VARCHAR(128) NOT NULL,
                title_es VARCHAR(128),
                duties JSON NOT NULL DEFAULT '[]'::json,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_career_track_specialty ON career_track(specialty_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_career_track_level ON career_track(level)"
        ))

        log.warning("[Pack 19.1] tables created (or already exist)")

        # === 4. CAREER_TRACKS — TRUNCATE + bulk INSERT ===
        conn.execute(text("TRUNCATE TABLE career_track RESTART IDENTITY CASCADE"))
        log.warning("[Pack 19.1] career_track table truncated")

        ct_rows: list[dict] = []
        for code, level, title_ru, title_es in CAREER_TRACKS_SEED:
            spec_id = specialty_id_map.get(code)
            if spec_id is None:
                log.warning(
                    "[Pack 19.1] unknown specialty %s for career_track %r — skipping",
                    code, title_ru,
                )
                continue
            ct_rows.append({
                "sid": spec_id,
                "lvl": level,
                "tru": title_ru,
                "tes": title_es,
            })

        if ct_rows:
            ct_values_sql = ", ".join(
                # Pack 19.1a: duties = '[]'::json (пустой массив, заполним в 19.1b)
                f"(:sid{i}, :lvl{i}, :tru{i}, :tes{i}, '[]'::json, TRUE)"
                for i in range(len(ct_rows))
            )
            ct_params: dict = {}
            for i, r in enumerate(ct_rows):
                ct_params[f"sid{i}"] = r["sid"]
                ct_params[f"lvl{i}"] = r["lvl"]
                ct_params[f"tru{i}"] = r["tru"]
                ct_params[f"tes{i}"] = r["tes"]

            conn.execute(
                text(f"""
                    INSERT INTO career_track
                    (specialty_id, level, title_ru, title_es, duties, is_active)
                    VALUES {ct_values_sql}
                """),
                ct_params,
            )

        log.warning(
            "[Pack 19.1] career_track bulk insert: %d records",
            len(ct_rows),
        )

        # === 5. LEGEND_COMPANIES — TRUNCATE + bulk INSERT ===
        conn.execute(text("TRUNCATE TABLE legend_company RESTART IDENTITY CASCADE"))
        log.warning("[Pack 19.1] legend_company table truncated")

        lc_rows: list[dict] = []
        for region_code, city, name_full, name_short, spec_code, size in LEGEND_COMPANIES_SEED:
            spec_id = specialty_id_map.get(spec_code)
            if spec_id is None:
                log.warning(
                    "[Pack 19.1] unknown specialty %s for legend_company %r — skipping",
                    spec_code, name_short,
                )
                continue
            lc_rows.append({
                "rc": region_code,
                "ci": city,
                "nf": name_full,
                "ns": name_short,
                "sid": spec_id,
                "sz": size,
            })

        if lc_rows:
            lc_values_sql = ", ".join(
                f"(:rc{i}, :ci{i}, :nf{i}, :ns{i}, :sid{i}, :sz{i}, TRUE)"
                for i in range(len(lc_rows))
            )
            lc_params: dict = {}
            for i, r in enumerate(lc_rows):
                lc_params[f"rc{i}"] = r["rc"]
                lc_params[f"ci{i}"] = r["ci"]
                lc_params[f"nf{i}"] = r["nf"]
                lc_params[f"ns{i}"] = r["ns"]
                lc_params[f"sid{i}"] = r["sid"]
                lc_params[f"sz{i}"] = r["sz"]

            conn.execute(
                text(f"""
                    INSERT INTO legend_company
                    (region_code, city, name_full, name_short,
                     primary_specialty_id, size, is_active)
                    VALUES {lc_values_sql}
                """),
                lc_params,
            )

        log.warning(
            "[Pack 19.1] legend_company bulk insert: %d records",
            len(lc_rows),
        )

        # === 6. Финальная сводка ===
        ct_count = conn.execute(
            text("SELECT COUNT(*) FROM career_track")
        ).scalar()
        lc_count = conn.execute(
            text("SELECT COUNT(*) FROM legend_company")
        ).scalar()
        regions_count = conn.execute(
            text("SELECT COUNT(DISTINCT region_code) FROM legend_company")
        ).scalar()

        log.warning(
            "[Pack 19.1] FINAL: %d career_tracks, %d legend_companies in %d regions",
            ct_count, lc_count, regions_count,
        )

    log.warning("[Pack 19.1] migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
