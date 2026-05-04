"""
Pack 18.9.0 — Универсальный МФЦ для всех клиентов.

Добавляет в mfc_office колонку is_universal и одну новую запись:
  Филиал ГБУ г. Москвы «МФЦ предоставления государственных услуг ...»
  ЮЗАО / Новоясеневский просп., д. 1
  staff_names: Иваничкина Ольга Николаевна, Соколова Анна Дмитриевна,
               Петрова Марина Сергеевна, Кузнецова Елена Викторовна

После миграции _pick_mfc() в context_npd_certificate.py возвращает эту запись
для всех applicant'ов независимо от их inn_kladr_code/region_code.

Старые 18 записей не удаляются — остаются is_universal=False, чтобы при
необходимости можно было быстро вернуться к региональному выбору
(ALTER staff_universal=False — система откатится к старой логике по region_code).

Запускается автоматически при старте Railway через main.py или локально:
  python -m app.scripts.migrate_pack18_9_0
"""
from __future__ import annotations

import logging
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import engine

log = logging.getLogger(__name__)

# Точное название из присланной справки самозанятого (Иваничкина О.Н.)
UNIVERSAL_MFC_NAME = (
    "Филиал Государственного бюджетного учреждения города Москвы "
    "«Многофункциональные центры предоставления государственных услуг "
    "города Москвы» многофункциональный центр предоставления государственных "
    "услуг Юго-Западного административного округа города Москвы "
    "Филиал ГБУ МФЦ города Москвы — МФЦ окружного значения Западного "
    "административного округа города Москвы"
)
UNIVERSAL_MFC_ADDRESS = "Город Москва, просп. Новоясеневский, д. 1"
UNIVERSAL_MFC_STAFF = [
    "Иваничкина Ольга Николаевна",
    "Соколова Анна Дмитриевна",
    "Петрова Марина Сергеевна",
    "Кузнецова Елена Викторовна",
]


def run() -> None:
    log.warning("[Pack 18.9.0] applying universal MFC migration...")

    with engine.begin() as conn:
        # 1. Добавляем колонку is_universal (если ещё нет)
        conn.execute(
            text(
                """
                ALTER TABLE mfc_office
                ADD COLUMN IF NOT EXISTS is_universal BOOLEAN DEFAULT FALSE NOT NULL
                """
            )
        )
        log.warning("[Pack 18.9.0] column is_universal added (or already exists)")

        # 1b. Расширяем name с VARCHAR(300) до VARCHAR(500).
        # Длинные московские МФЦ-названия не помещались.
        # ALTER COLUMN ... TYPE безопасен (данные сохраняются).
        conn.execute(
            text(
                """
                ALTER TABLE mfc_office
                ALTER COLUMN name TYPE VARCHAR(500)
                """
            )
        )
        log.warning("[Pack 18.9.0] column name expanded to VARCHAR(500)")

        # 2. Индекс на is_universal (для быстрого поиска в _pick_mfc)
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_mfc_universal
                ON mfc_office (is_universal)
                WHERE is_universal = TRUE
                """
            )
        )
        log.warning("[Pack 18.9.0] partial index idx_mfc_universal created (or exists)")

        # 3. Сбрасываем флаг на всех существующих (на случай повторного запуска)
        conn.execute(text("UPDATE mfc_office SET is_universal = FALSE"))

        # 4. Проверяем — есть ли уже запись с этим именем (повторный запуск)
        result = conn.execute(
            text("SELECT id FROM mfc_office WHERE name = :name LIMIT 1"),
            {"name": UNIVERSAL_MFC_NAME},
        )
        existing = result.first()

        if existing:
            # Есть запись — просто обновляем её и ставим is_universal=True
            conn.execute(
                text(
                    """
                    UPDATE mfc_office
                    SET is_universal = TRUE,
                        is_active = TRUE,
                        address = :address,
                        staff_names = CAST(:staff_names AS JSONB)
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing[0],
                    "address": UNIVERSAL_MFC_ADDRESS,
                    "staff_names": _to_json(UNIVERSAL_MFC_STAFF),
                },
            )
            log.warning(
                "[Pack 18.9.0] existing universal MFC id=%s updated and marked is_universal=True",
                existing[0],
            )
        else:
            # Нет — создаём новую
            conn.execute(
                text(
                    """
                    INSERT INTO mfc_office
                        (region_code, city, name, address, staff_names,
                         is_universal, is_active, created_at, updated_at)
                    VALUES
                        ('77', 'Москва', :name, :address,
                         CAST(:staff_names AS JSONB),
                         TRUE, TRUE, NOW(), NOW())
                    """
                ),
                {
                    "name": UNIVERSAL_MFC_NAME,
                    "address": UNIVERSAL_MFC_ADDRESS,
                    "staff_names": _to_json(UNIVERSAL_MFC_STAFF),
                },
            )
            log.warning("[Pack 18.9.0] new universal MFC inserted (Новоясеневский д.1)")

    log.warning("[Pack 18.9.0] migration complete")


def _to_json(value: list) -> str:
    """Сериализует list для CAST AS JSONB."""
    import json
    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
