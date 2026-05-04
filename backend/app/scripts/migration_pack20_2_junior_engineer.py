"""
Pack 20.2 — наполнение Position справочника (этап 1: 1 эталон).

Создаёт ОДНУ Position для теста стиля:
- Инженер-проектировщик (Junior) для специальности 08.03.01 Строительство

Источники duties (правило PROJECT_STATE — компиляция из реальных, не из головы):
1. Приказ Минздравсоцразвития РФ от 23.04.2008 N 188 (ЕКС) — должностная
   инструкция «Инженер-проектировщик» без категории. Адаптировано для
   современных проектных бюро: убраны устаревшие пункты (изобретения,
   рационализаторские предложения), добавлены инструменты (AutoCAD, Revit, BIM).
2. Реальные вакансии Junior-инженеров-проектировщиков с hh.ru / superjob
   (2025-2026): «Группа Б3» (Revit-моделлер по инж. системам),
   «Реализация Инноваций Масстар» (КЖ/КМ/АР), школы и детсады в Москве.
3. Стиль duties — копирует образец Position id=2 (геодезист):
   безличная форма, конкретика инструментов, профессиональная терминология.

КАК ПРИМЕНИТЬ:
    $env:DATABASE_URL = "postgresql://postgres:...@switchyard.proxy.rlwy.net:34408/railway"
    $env:PYTHONIOENCODING = "utf-8"
    cd D:\\VISA\\visa_kit\\backend
    python -m app.scripts.migration_pack20_2_junior_engineer

Идемпотентно: проверяет наличие Position по уникальному `title_ru` +
`primary_specialty_id` + `level`. При повторном запуске — UPDATE.
"""

from sqlalchemy import text
from app.db.session import engine


# ============================================================================
# DATA — Position для теста стиля
# ============================================================================

# Specialty 08.03.01 Строительство — лежит в таблице specialty (Pack 19.0).
# В seed code = "08.03.01". Запрашиваем id перед вставкой.
SPECIALTY_CODE = "08.03.01"

POSITION_DATA = {
    "title_ru": "Инженер-проектировщик",
    "title_ru_genitive": "инженера-проектировщика",
    "title_es": "ingeniero proyectista",
    "level": 1,  # Junior — соответствует «Инженер-проектировщик» без категории по ЕКС
    "salary_rub_default": 180000,
    # Tags — ключевые слова профессии для LLM-рекомендатора
    "tags": [
        "проектирование",
        "AutoCAD",
        "Revit",
        "BIM",
        "ПГС",
        "проектная документация",
        "СНиП",
    ],
    "profile_description": (
        "Junior-инженер-проектировщик в строительной/проектной организации. "
        "Работает под руководством ведущего/главного специалиста, выполняет "
        "разделы рабочей документации в AutoCAD/Revit. "
        "Подходит выпускникам строительных вузов (08.03.01 «Строительство», "
        "ПГС, инженерные системы) и специалистам с опытом до 1 года."
    ),
    # 9 duties в стиле эталона — конкретные действия Junior'а
    "duties": [
        # 1. Базовая работа с CAD — основная активность Junior'а
        "Разработка отдельных листов и узлов рабочей документации в AutoCAD по решениям, принятым ведущим специалистом",
        # 2. BIM-моделирование — современный обязательный навык
        "Моделирование строительных конструкций и инженерных систем в Autodesk Revit (расстановка оборудования, трассировка систем, настройка видов и спецификаций)",
        # 3. Сбор исходных данных — типичная Junior-задача из ЕКС
        "Сбор и систематизация исходных данных для проектирования: топосъёмка, геология, технические условия от ресурсоснабжающих организаций",
        # 4. Расчёты — конкретный пример уровня сложности
        "Выполнение технико-экономических расчётов и подбор оборудования по разрабатываемому разделу проекта",
        # 5. Спецификации/ведомости — рутинная работа Junior'а
        "Составление спецификаций оборудования, ведомостей материалов и объёмов работ к разработанным чертежам",
        # 6. Взаимодействие со смежниками
        "Подготовка заданий для смежных разделов проекта (электрика, водоснабжение, отопление) и согласование принятых решений со специалистами смежных отделов",
        # 7. Внесение правок — главная Junior-боль
        "Внесение в проектную документацию изменений по замечаниям ведущего специалиста, ГИП и заказчика",
        # 8. Нормоконтроль на своём уровне
        "Проверка разработанной документации на соответствие действующим ГОСТам, СП, СНиП и стандартам предприятия",
        # 9. Сопровождение коллизий в BIM
        "Участие в проверке BIM-моделей на коллизии и устранение конфликтов с моделями смежных разделов",
    ],
}


# ============================================================================
# MIGRATION
# ============================================================================

def main():
    print("[Pack 20.2 / Junior Engineer] start")

    with engine.begin() as conn:
        # 1. Найти specialty_id по коду 08.03.01
        spec_row = conn.execute(
            text("SELECT id, name FROM specialty WHERE code = :code"),
            {"code": SPECIALTY_CODE},
        ).fetchone()
        if not spec_row:
            raise SystemExit(
                f"[Pack 20.2] FATAL: specialty with code={SPECIALTY_CODE} not found. "
                f"Make sure migration_pack19_0 was applied."
            )
        specialty_id, specialty_name = spec_row[0], spec_row[1]
        print(f"[Pack 20.2] specialty resolved: id={specialty_id}, name='{specialty_name}'")

        # 2. Проверить — есть ли уже такая Position
        existing = conn.execute(
            text(
                "SELECT id FROM position "
                "WHERE title_ru = :title_ru "
                "AND primary_specialty_id = :spec_id "
                "AND level = :level"
            ),
            {
                "title_ru": POSITION_DATA["title_ru"],
                "spec_id": specialty_id,
                "level": POSITION_DATA["level"],
            },
        ).fetchone()

        import json
        params = {
            "title_ru": POSITION_DATA["title_ru"],
            "title_ru_genitive": POSITION_DATA["title_ru_genitive"],
            "title_es": POSITION_DATA["title_es"],
            "duties": json.dumps(POSITION_DATA["duties"], ensure_ascii=False),
            "salary": POSITION_DATA["salary_rub_default"],
            "tags": json.dumps(POSITION_DATA["tags"], ensure_ascii=False),
            "profile": POSITION_DATA["profile_description"],
            "spec_id": specialty_id,
            "level": POSITION_DATA["level"],
        }

        if existing:
            position_id = existing[0]
            conn.execute(
                text("""
                    UPDATE position SET
                        title_ru_genitive = :title_ru_genitive,
                        title_es = :title_es,
                        duties = CAST(:duties AS JSON),
                        salary_rub_default = :salary,
                        tags = CAST(:tags AS JSON),
                        profile_description = :profile,
                        is_active = TRUE,
                        updated_at = NOW()
                    WHERE id = :pos_id
                """),
                {**params, "pos_id": position_id},
            )
            print(f"[Pack 20.2] UPDATED existing Position id={position_id}")
        else:
            result = conn.execute(
                text("""
                    INSERT INTO position (
                        title_ru, title_ru_genitive, title_es,
                        duties, salary_rub_default, tags,
                        profile_description, primary_specialty_id, level,
                        is_active, created_at, updated_at
                    ) VALUES (
                        :title_ru, :title_ru_genitive, :title_es,
                        CAST(:duties AS JSON), :salary, CAST(:tags AS JSON),
                        :profile, :spec_id, :level,
                        TRUE, NOW(), NOW()
                    )
                    RETURNING id
                """),
                params,
            )
            position_id = result.scalar()
            print(f"[Pack 20.2] INSERTED new Position id={position_id}")

        # 3. Показать что получилось
        print("[Pack 20.2] FINAL state of created Position:")
        final = conn.execute(
            text("""
                SELECT id, title_ru, title_es, level, primary_specialty_id,
                       salary_rub_default, jsonb_array_length(duties::jsonb) AS n_duties
                FROM position WHERE id = :pos_id
            """),
            {"pos_id": position_id},
        ).fetchone()
        print(f"    id={final[0]}")
        print(f"    title_ru={final[1]}")
        print(f"    title_es={final[2]}")
        print(f"    level={final[3]} (1=Junior)")
        print(f"    primary_specialty_id={final[4]}")
        print(f"    salary_rub_default={final[5]}")
        print(f"    duties count={final[6]}")

    print("[Pack 20.2 / Junior Engineer] ✅ DONE")


if __name__ == "__main__":
    main()
