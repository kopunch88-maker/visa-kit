"""
Pack 19.0 — миграция справочников вузов (v2: bulk-insert вместо DELETE-loop).

Создаёт 4 таблицы:
- specialty
- university
- university_specialty_link (M2M)
- position_specialty_map

Заполняет seed (30 specialty, 40 university, 60+ position patterns).

V2 changes vs v1:
- university seed теперь использует TRUNCATE + bulk INSERT вместо
  DELETE-loop по каждому вузу (висло через Railway proxy на ~10-й итерации).
- specialty seed остался ON CONFLICT — он быстрый.

Запуск:
  python -m app.scripts.migration_pack19_0
"""
from __future__ import annotations

import logging
from sqlalchemy import text

from app.db.session import engine
from app.seeds.universities_seed import (
    SPECIALTIES_SEED,
    UNIVERSITIES_SEED,
    POSITION_SPECIALTY_SEED,
)

log = logging.getLogger(__name__)


def run() -> None:
    log.warning("[Pack 19.0] applying universities migration...")

    with engine.begin() as conn:
        # === 1. Создаём 4 таблицы ===
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS specialty (
                id SERIAL PRIMARY KEY,
                code VARCHAR(10) UNIQUE NOT NULL,
                name VARCHAR(256) NOT NULL,
                level VARCHAR(32) NOT NULL DEFAULT 'bachelor',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_specialty_code ON specialty(code)"
        ))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS university (
                id SERIAL PRIMARY KEY,
                region_code VARCHAR(2) NOT NULL,
                city VARCHAR(128) NOT NULL,
                name_full VARCHAR(512) NOT NULL,
                name_short VARCHAR(128) NOT NULL,
                founding_year INTEGER,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_university_region ON university(region_code)"
        ))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS university_specialty_link (
                university_id INTEGER NOT NULL REFERENCES university(id) ON DELETE CASCADE,
                specialty_id INTEGER NOT NULL REFERENCES specialty(id) ON DELETE CASCADE,
                PRIMARY KEY (university_id, specialty_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS position_specialty_map (
                id SERIAL PRIMARY KEY,
                position_pattern VARCHAR(256) NOT NULL,
                specialty_id INTEGER NOT NULL REFERENCES specialty(id) ON DELETE CASCADE,
                priority INTEGER DEFAULT 100 NOT NULL,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_psm_pattern ON position_specialty_map(position_pattern)"
        ))

        log.warning("[Pack 19.0] tables created (or already exist)")

        # === 2. Specialty seed (быстрый ON CONFLICT) ===
        # Делаем bulk INSERT одним запросом для скорости
        specialty_values_sql = ", ".join(
            f"(:c{i}, :n{i}, :l{i})" for i in range(len(SPECIALTIES_SEED))
        )
        specialty_params: dict = {}
        for i, (code, name, level) in enumerate(SPECIALTIES_SEED):
            specialty_params[f"c{i}"] = code
            specialty_params[f"n{i}"] = name
            specialty_params[f"l{i}"] = level

        conn.execute(
            text(f"""
                INSERT INTO specialty (code, name, level)
                VALUES {specialty_values_sql}
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            """),
            specialty_params,
        )

        # Получаем id_map одним запросом
        rows = conn.execute(
            text("SELECT code, id FROM specialty")
        ).all()
        specialty_id_map: dict[str, int] = {r.code: r.id for r in rows}

        log.warning(
            "[Pack 19.0] specialty seed: %d records",
            len(specialty_id_map),
        )

        # === 3. Universities — TRUNCATE + bulk INSERT (быстрее) ===
        # CASCADE удалит все связи в university_specialty_link автоматически
        conn.execute(text(
            "TRUNCATE TABLE university RESTART IDENTITY CASCADE"
        ))
        log.warning("[Pack 19.0] university table truncated")

        # Bulk INSERT всех вузов одним запросом
        uni_values_sql = ", ".join(
            f"(:rc{i}, :ci{i}, :nf{i}, :ns{i}, :fy{i}, TRUE)"
            for i in range(len(UNIVERSITIES_SEED))
        )
        uni_params: dict = {}
        for i, (region_code, city, name_full, name_short, founding_year, _) in enumerate(UNIVERSITIES_SEED):
            uni_params[f"rc{i}"] = region_code
            uni_params[f"ci{i}"] = city
            uni_params[f"nf{i}"] = name_full
            uni_params[f"ns{i}"] = name_short
            uni_params[f"fy{i}"] = founding_year

        conn.execute(
            text(f"""
                INSERT INTO university
                (region_code, city, name_full, name_short, founding_year, is_active)
                VALUES {uni_values_sql}
            """),
            uni_params,
        )

        log.warning("[Pack 19.0] university bulk insert: %d records", len(UNIVERSITIES_SEED))

        # Получаем id всех вузов одним запросом
        rows = conn.execute(
            text("SELECT id, name_full FROM university ORDER BY id")
        ).all()
        # Mapping: name_full → id
        uni_id_map: dict[str, int] = {r.name_full: r.id for r in rows}

        # === 4. M2M связи University ↔ Specialty (bulk INSERT) ===
        link_rows: list[dict] = []
        for region_code, city, name_full, name_short, founding_year, spec_codes in UNIVERSITIES_SEED:
            uni_id = uni_id_map.get(name_full)
            if uni_id is None:
                log.warning("[Pack 19.0] missing uni_id for %s", name_short)
                continue
            for code in spec_codes:
                spec_id = specialty_id_map.get(code)
                if spec_id is None:
                    log.warning("[Pack 19.0] missing specialty %s for %s", code, name_short)
                    continue
                link_rows.append({"uid": uni_id, "sid": spec_id})

        if link_rows:
            # Bulk INSERT всех связей одним запросом
            link_values_sql = ", ".join(
                f"(:uid{i}, :sid{i})" for i in range(len(link_rows))
            )
            link_params: dict = {}
            for i, lr in enumerate(link_rows):
                link_params[f"uid{i}"] = lr["uid"]
                link_params[f"sid{i}"] = lr["sid"]

            conn.execute(
                text(f"""
                    INSERT INTO university_specialty_link (university_id, specialty_id)
                    VALUES {link_values_sql}
                """),
                link_params,
            )

        log.warning(
            "[Pack 19.0] university_specialty_link bulk insert: %d links",
            len(link_rows),
        )

        # === 5. Position-specialty map (bulk INSERT) ===
        conn.execute(text("TRUNCATE TABLE position_specialty_map RESTART IDENTITY CASCADE"))

        psm_rows: list[dict] = []
        for pattern, spec_code, priority in POSITION_SPECIALTY_SEED:
            spec_id = specialty_id_map.get(spec_code)
            if spec_id is None:
                log.warning("[Pack 19.0] unknown specialty %s for pattern %r", spec_code, pattern)
                continue
            psm_rows.append({
                "pat": pattern.lower(),
                "sid": spec_id,
                "prio": priority,
            })

        if psm_rows:
            psm_values_sql = ", ".join(
                f"(:pat{i}, :sid{i}, :prio{i}, TRUE)" for i in range(len(psm_rows))
            )
            psm_params: dict = {}
            for i, r in enumerate(psm_rows):
                psm_params[f"pat{i}"] = r["pat"]
                psm_params[f"sid{i}"] = r["sid"]
                psm_params[f"prio{i}"] = r["prio"]

            conn.execute(
                text(f"""
                    INSERT INTO position_specialty_map
                    (position_pattern, specialty_id, priority, is_active)
                    VALUES {psm_values_sql}
                """),
                psm_params,
            )

        log.warning(
            "[Pack 19.0] position_specialty_map seed: %d patterns",
            len(psm_rows),
        )

    log.warning("[Pack 19.0] migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
