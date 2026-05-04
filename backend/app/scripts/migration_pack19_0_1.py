"""
Pack 19.0.1 — точечный апдейт position_specialty_map (без перезаливки вузов).

Что меняется vs Pack 19.0:
- Расширены паттерны должностей с ~70 до 110+ (добавлены английские)
- Добавлены явные паттерны для строительной отрасли:
    "проектировщик", "инженер-проектировщик", "инженер проектировщик",
    "civil engineer", "structural engineer", "design engineer", и т.д.
- Generic паттерн "инженер" / "engineer" теперь приоритетнее "менеджер"
  (было: оба priority=90, теперь "менеджер" = 95 — то есть срабатывает
  только если ни одна из инженерных не сработала)

Не трогает таблицы:
  - specialty (там тот же набор)
  - university (38 записей залиты в прошлый раз, не пересоздаём)
  - university_specialty_link

Запуск:
  python -m app.scripts.migration_pack19_0_1
"""
from __future__ import annotations

import logging
from sqlalchemy import text

from app.db.session import engine
from app.seeds.universities_seed import POSITION_SPECIALTY_SEED

log = logging.getLogger(__name__)


def run() -> None:
    log.warning("[Pack 19.0.1] applying position_specialty_map update...")

    with engine.begin() as conn:
        # Получаем mapping code → id (из существующих specialty)
        rows = conn.execute(
            text("SELECT code, id FROM specialty")
        ).all()
        specialty_id_map: dict[str, int] = {r.code: r.id for r in rows}

        if not specialty_id_map:
            raise RuntimeError(
                "Pack 19.0.1: таблица specialty пуста. "
                "Сначала прогоните migration_pack19_0 чтобы залить специальности."
            )

        log.warning(
            "[Pack 19.0.1] found %d specialties in DB",
            len(specialty_id_map),
        )

        # TRUNCATE и bulk INSERT с новыми паттернами
        conn.execute(text("TRUNCATE TABLE position_specialty_map RESTART IDENTITY CASCADE"))

        psm_rows: list[dict] = []
        for pattern, spec_code, priority in POSITION_SPECIALTY_SEED:
            spec_id = specialty_id_map.get(spec_code)
            if spec_id is None:
                log.warning(
                    "[Pack 19.0.1] unknown specialty %s for pattern %r — skipping",
                    spec_code, pattern,
                )
                continue
            psm_rows.append({
                "pat": pattern.lower(),
                "sid": spec_id,
                "prio": priority,
            })

        if psm_rows:
            psm_values_sql = ", ".join(
                f"(:pat{i}, :sid{i}, :prio{i}, TRUE)"
                for i in range(len(psm_rows))
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
            "[Pack 19.0.1] position_specialty_map: %d patterns inserted",
            len(psm_rows),
        )

    log.warning("[Pack 19.0.1] migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
