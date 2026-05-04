"""
Pack 20.2 cleanup — финальная очистка справочника Position.

ЦЕЛИ:
1. Удалить очевидный мусор (id=1 'xczxczxc', id=10 'nkhljkl')
2. Удалить тестовую заявку 2026-0002 (привязана к id=1)
3. Перепривязать заявку 2026-0003 (Vedat) с position id=11 на id=14
4. Удалить старые позиции дубликаты после разрыва ссылок (id=3,4,5,6,11)
5. Разметить уцелевшие старые Position'ы (id=2, 7, 8, 9):
   - id=2 'инженер-геодезист' → 07.03.01 Архитектура (или 08.03.01 Строит-во), L2 Middle
     (золотой эталон, оставить как есть)
   - id=7 'Project manager' → 38.03.02 Менеджмент, L3 Senior
   - id=8 'IT-консультант' → 38.03.02 Менеджмент, L2 Middle
   - id=9 'Маркетолог' → 42.03.01 Реклама и связи с общественностью, L2 Middle

ИТОГО ПОСЛЕ:
   32 Position в БД, ВСЕ с specialty_id+level. Никаких дубликатов и мусора.

ВАЖНО про id=2 геодезист:
   Это ЭТАЛОН СТИЛЯ (PROJECT_STATE). У него 11 duties, привязка к заявке 2026-0001.
   Специальность для геодезиста по строгому ОКСО — 21.03.02 «Землеустройство и
   кадастры», но её НЕТ в нашем seed. Ближайший аналог — 07.03.01 «Архитектура»
   (id=13) или 08.03.01 «Строительство» (id=6). Привязываем к 08.03.01 — это
   логичнее (геодезисты в РФ чаще работают в строительстве).

ВАЖНО про мусорные salary:
   id=1 имеет salary=30000000, id=10 имеет salary=3000000000. Это плодит
   странные значения в логах. После удаления — никаких проблем не будет.

ИДЕМПОТЕНТНОСТЬ:
   Каждый шаг проверяет наличие Position перед операцией. При повторе —
   просто сообщает "skip".

КАК ПРИМЕНИТЬ:
    $env:DATABASE_URL = "..."
    $env:PYTHONIOENCODING = "utf-8"
    cd D:\\VISA\\visa_kit\\backend
    python -m app.scripts.migration_pack20_2_cleanup
"""

from sqlalchemy import text
from app.db.session import engine


# ============================================================================
# CONFIG
# ============================================================================

# Маппинг старых Position на новые specialty/level
REMAP_OLD_POSITIONS = {
    # id_old : (specialty_code, level)
    2: ("08.03.01", 2),  # инженер-геодезист → Строительство, Middle
    7: ("38.03.02", 3),  # Project manager → Менеджмент, Senior
    8: ("38.03.02", 2),  # IT-консультант → Менеджмент, Middle
    9: ("42.03.01", 2),  # Маркетолог → Реклама, Middle
}

# Position'ы которые удаляем (после разрыва ссылок)
POSITIONS_TO_DELETE = [
    1,   # 'xczxczxc' мусор
    3,   # 'технический переводчик' — есть id=37
    4,   # 'бизнес-аналитик' — есть id=25
    5,   # 'Backend developer' — есть id=18
    6,   # 'Frontend developer' — есть id=18
    10,  # 'nkhljkl' мусор
    11,  # 'инженер-проектировщик' — будет перепривязка → удаление
]

# Заявки которые удаляем безвозвратно (тестовые)
APPLICATIONS_TO_DELETE = [
    2,   # 2026-0002 — привязана к мусорной id=1
]

# Заявки которые перепривязываем
APPLICATION_REMAPS = [
    # (app_id, old_position_id, new_position_id, причина)
    (13, 11, 14, "Vedat: 'инженер-проектировщик' → 'Ведущий инженер-проектировщик' (Senior)"),
]


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("[Pack 20.2 cleanup] start")

    with engine.begin() as conn:
        # ====================================================================
        # 0. SAFETY — показать состояние до изменений
        # ====================================================================
        print("\n[Pack 20.2] === BEFORE: state of Position 1..11 + applications ===")
        rows = conn.execute(text("""
            SELECT p.id, p.title_ru, p.is_active, p.primary_specialty_id, p.level,
                   COUNT(a.id) AS n_apps
            FROM position p
            LEFT JOIN application a ON a.position_id = p.id
            WHERE p.id BETWEEN 1 AND 11
            GROUP BY p.id, p.title_ru, p.is_active, p.primary_specialty_id, p.level
            ORDER BY p.id
        """)).fetchall()
        for r in rows:
            print(f"    id={r[0]:>2}  active={r[2]}  spec={r[3]} L{r[4]}  apps={r[5]}  '{r[1]}'")

        # ====================================================================
        # 1. DELETE тестовых заявок и связанных данных
        # ====================================================================
        print("\n[Pack 20.2] === STEP 1: delete test applications ===")
        for app_id in APPLICATIONS_TO_DELETE:
            app_row = conn.execute(
                text("SELECT id, reference, status FROM application WHERE id = :id"),
                {"id": app_id},
            ).fetchone()
            if not app_row:
                print(f"    skip: application id={app_id} not found")
                continue
            # Удаляем зависимые объекты сначала
            conn.execute(text("DELETE FROM timeline_event WHERE application_id = :id"), {"id": app_id})
            conn.execute(text("DELETE FROM family_member WHERE application_id = :id"), {"id": app_id})
            conn.execute(text("DELETE FROM previous_residence WHERE application_id = :id"), {"id": app_id})
            conn.execute(text("DELETE FROM uploaded_file WHERE application_id = :id"), {"id": app_id})
            conn.execute(text("DELETE FROM generated_document WHERE application_id = :id"), {"id": app_id})
            # Сама заявка
            conn.execute(text("DELETE FROM application WHERE id = :id"), {"id": app_id})
            print(f"    DELETED application id={app_id} ref={app_row[1]} status={app_row[2]}")

        # ====================================================================
        # 2. REMAP применений (перепривязка к новым Position)
        # ====================================================================
        print("\n[Pack 20.2] === STEP 2: remap applications to new Position ===")
        for app_id, old_pid, new_pid, reason in APPLICATION_REMAPS:
            app_row = conn.execute(
                text("SELECT id, reference, position_id FROM application WHERE id = :id"),
                {"id": app_id},
            ).fetchone()
            if not app_row:
                print(f"    skip: application id={app_id} not found")
                continue
            current_pid = app_row[2]
            if current_pid != old_pid:
                print(f"    skip: app id={app_id} ref={app_row[1]} has position_id={current_pid}, "
                      f"expected {old_pid}; not remapping")
                continue
            # Проверяем что target Position существует
            target = conn.execute(
                text("SELECT id, title_ru FROM position WHERE id = :id"),
                {"id": new_pid},
            ).fetchone()
            if not target:
                print(f"    ⚠️  ERROR: target Position id={new_pid} not found, skipping remap")
                continue
            # Делаем UPDATE
            conn.execute(
                text("UPDATE application SET position_id = :new WHERE id = :id"),
                {"new": new_pid, "id": app_id},
            )
            print(f"    REMAPPED app id={app_id} ref={app_row[1]}: position {old_pid} → {new_pid}")
            print(f"        ({reason})")

        # ====================================================================
        # 3. UPDATE specialty/level для оставшихся старых Position
        # ====================================================================
        print("\n[Pack 20.2] === STEP 3: assign specialty/level to surviving old Position ===")
        for pid, (spec_code, level) in REMAP_OLD_POSITIONS.items():
            # Проверяем что Position существует
            pos_row = conn.execute(
                text("SELECT id, title_ru, primary_specialty_id, level FROM position WHERE id = :id"),
                {"id": pid},
            ).fetchone()
            if not pos_row:
                print(f"    skip: Position id={pid} not found")
                continue
            # Резолвим specialty_id по коду
            spec_row = conn.execute(
                text("SELECT id, name FROM specialty WHERE code = :code"),
                {"code": spec_code},
            ).fetchone()
            if not spec_row:
                print(f"    ⚠️  ERROR: specialty code={spec_code} not found, skipping id={pid}")
                continue
            spec_id, spec_name = spec_row[0], spec_row[1]
            # Обновляем
            conn.execute(
                text("""
                    UPDATE position
                    SET primary_specialty_id = :spec_id,
                        level = :level,
                        updated_at = NOW()
                    WHERE id = :pid
                """),
                {"spec_id": spec_id, "level": level, "pid": pid},
            )
            print(f"    UPDATED Position id={pid} '{pos_row[1]}' "
                  f"→ specialty={spec_code} ({spec_name}), level={level}")

        # ====================================================================
        # 4. DELETE Position'ы (мусор + дубликаты)
        # ====================================================================
        print("\n[Pack 20.2] === STEP 4: delete junk and duplicate Position ===")
        for pid in POSITIONS_TO_DELETE:
            pos_row = conn.execute(
                text("SELECT id, title_ru FROM position WHERE id = :id"),
                {"id": pid},
            ).fetchone()
            if not pos_row:
                print(f"    skip: Position id={pid} already gone")
                continue
            # Безопасность: проверяем что нет активных применений
            n_apps = conn.execute(
                text("SELECT COUNT(*) FROM application WHERE position_id = :id"),
                {"id": pid},
            ).scalar()
            if n_apps > 0:
                print(f"    ⚠️  SKIP: Position id={pid} '{pos_row[1]}' has {n_apps} applications, "
                      f"cannot delete safely")
                continue
            # Удаляем
            conn.execute(text("DELETE FROM position WHERE id = :id"), {"id": pid})
            print(f"    DELETED Position id={pid} '{pos_row[1]}'")

        # ====================================================================
        # 5. FINAL — показать итоговую картину
        # ====================================================================
        print("\n[Pack 20.2] === FINAL: state of Position table ===")
        n_total = conn.execute(text("SELECT COUNT(*) FROM position")).scalar()
        n_marked = conn.execute(
            text("SELECT COUNT(*) FROM position WHERE primary_specialty_id IS NOT NULL")
        ).scalar()
        n_unmarked = n_total - n_marked
        print(f"    Total positions: {n_total}")
        print(f"    Marked (specialty+level): {n_marked}")
        print(f"    Unmarked: {n_unmarked}")

        if n_unmarked > 0:
            print("\n    Unmarked positions (требуют внимания):")
            unmarked = conn.execute(text("""
                SELECT id, title_ru, salary_rub_default
                FROM position
                WHERE primary_specialty_id IS NULL
                ORDER BY id
            """)).fetchall()
            for r in unmarked:
                print(f"      id={r[0]:>2}  '{r[1]}'  salary={r[2]}")

        print("\n    Распределение по специальностям:")
        rows = conn.execute(text("""
            SELECT s.code, s.name, COUNT(*) AS n
            FROM position p
            JOIN specialty s ON p.primary_specialty_id = s.id
            GROUP BY s.code, s.name
            ORDER BY s.code
        """)).fetchall()
        for r in rows:
            print(f"      {r[0]} {r[1]:<32}: {r[2]} Position")

    print("\n[Pack 20.2 cleanup] ✅ DONE")


if __name__ == "__main__":
    main()
