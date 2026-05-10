"""
Pack 33.8 (10.05.2026) — Расширение справочника ИФНС для точного подбора
по адресу клиента.

ЧТО ДЕЛАЕТ:
  1. ALTER TABLE ifns_office ADD COLUMN coverage_keywords JSONB
     DEFAULT '[]'::jsonb NOT NULL — новое поле для точного матчинга
     районной инспекции по applicant.home_address.
  2. UPDATE существующих 3 non-default записей (Сочи 2367, Москва 7728,
     СПб 7841) — заполняем им coverage_keywords по реальной зоне
     обслуживания.
  3. INSERT 7 новых записей:
     - 16 (Татарстан): МИФНС №14 (Казань, Вахитовский)
     - 61 (Ростовская обл.): МИФНС №24 (Ростов-на-Дону, Советский+ЖД)
     - 77 (Москва): ИФНС №13 (САО), №15 (СВАО), №24 (ЮАО), №27 (ЮЗАО), №31 (ЗАО)

ИСТОЧНИКИ ДАННЫХ (все проверены):
  - nalog.gov.ru (официальный сайт ФНС)
  - alta.ru/ifns (справочник от Альта-Софт, источник — ГНИВЦ ФНС)
  - nalogia.ru (открытые данные с привязкой кодов СОУН к адресам)

КАК ПРИМЕНИТЬ:
    $env:DATABASE_URL = "postgresql://...railway..."
    $env:PYTHONIOENCODING = "utf-8"
    cd D:\\VISA\\visa_kit\\backend
    python -m app.scripts.migration_pack33_8

ИДЕМПОТЕНТНОСТЬ:
  - ALTER TABLE: проверка через information_schema.columns (если уже есть — skip)
  - INSERT: проверка по уникальному (region_code, code) — если запись есть, делаем UPDATE
  - UPDATE existing 3: безусловный SET coverage_keywords (перезаписывает, но
    содержимое детерминированное)

ROLLBACK:
  Если что-то пошло не так — coverage_keywords безопасно дропнуть:
    ALTER TABLE ifns_office DROP COLUMN IF EXISTS coverage_keywords;
  Старая логика _pick_ifns Tier B (Pack 31.1) продолжит работать.
"""
from __future__ import annotations

import json
import logging
import os
import sys

from sqlalchemy import text
from sqlmodel import Session, create_engine

log = logging.getLogger(__name__)


# ============================================================================
# DATA — обновления существующих записей (UPDATE)
# ============================================================================
# Структура: (code, region_code, coverage_keywords_list)
# Эти записи УЖЕ есть в ifns_office (Pack 18.0 + Pack 31.0).
# Мы только добавляем им coverage_keywords.

EXISTING_UPDATES = [
    # Сочи МИФНС №8 (Pack 31.0) — обслуживает Адлерский район Сочи и окрестности
    ("2367", "23", [
        "сочи", "адлер", "адлерский",
        "раздольное", "партизанская", "параллельная",
    ]),

    # Москва ИФНС №28 (Pack 18.0) — Академический, Гагаринский, Котловка,
    # Ломоносовский, Обручевский, Тропарёво-Никулино, Тёплый Стан, Ясенево
    ("7728", "77", [
        "винокурова", "академический", "каховка",
        "тёплый стан", "теплый стан", "ясенево",
        "коньково", "тропарёво", "тропарево",
    ]),

    # СПб МИФНС №25 (Pack 18.0) — Кировский район
    ("7841", "78", [
        "санкт-петербург", "петербург",
        "кировский",
    ]),
]


# ============================================================================
# DATA — новые записи (INSERT)
# ============================================================================
# Структура: (code, region_code, full_name, short_name, address,
#             is_default, coverage_keywords)
#
# Все записи is_default=False (специфические районные инспекции).
# Дефолтные УФНС в каждом регионе уже сидаются Pack 18.0.

NEW_RECORDS = [
    # ═══════════════════════════════════════════════════════════════════════
    # 16 — Республика Татарстан
    # ═══════════════════════════════════════════════════════════════════════
    # МИФНС №14 (Вахитовский район Казани, ул. Театральная 13а).
    # Адрес и код подтверждены: alta.ru/ifns/1655, nalogia.ru.
    # Покрывает применительно к Ся Инь (inn_kladr_code=16, ИНН выдан в РТ),
    # хотя её фактический home_address в Красногорске МО — keywords не
    # совпадут, но это всё равно лучше чем дефолтная УФНС-управление,
    # потому что Tier C даст эту запись (она единственная не-default в РТ).
    ("1655", "16",
     "Межрайонная инспекция Федеральной налоговой службы №14 по Республике Татарстан",
     "Межрайонная ИФНС России №14 по Республике Татарстан",
     "420111, Республика Татарстан, г. Казань, ул. Театральная, д. 13А",
     False,
     ["казань", "вахитовский", "татарстан"]),

    # ═══════════════════════════════════════════════════════════════════════
    # 61 — Ростовская область
    # ═══════════════════════════════════════════════════════════════════════
    # МИФНС №24 (Советский + Железнодорожный районы Ростова-на-Дону).
    # Адрес: 344058, Ростов-на-Дону, пр-кт Коммунистический, д. 23/4.
    # Источник: nalog.gov.ru, ИНН организации 6162500008, код инспекции 6194.
    # Покрытие: Советский район (где живёт Бабараджабов на ул. Содружества).
    ("6194", "61",
     "Межрайонная инспекция Федеральной налоговой службы №24 по Ростовской области",
     "Межрайонная ИФНС России №24 по Ростовской области",
     "344058, Ростовская область, г. Ростов-на-Дону, пр-кт Коммунистический, д. 23/4",
     False,
     ["ростов-на-дону", "ростов", "советский", "железнодорожный",
      "содружества"]),

    # ═══════════════════════════════════════════════════════════════════════
    # 77 — Москва (5 записей по округам, для матчинга по home_address)
    # ═══════════════════════════════════════════════════════════════════════

    # ИФНС №13 — САО (Северный АО). Адрес: 105064, ул. Земляной вал, 9.
    # Обслуживает: Аэропорт, Бескудниковский, Войковский, Восточное Дегунино,
    # Дмитровский, Западное Дегунино, Коптево, Савёловский, Тимирязевский.
    # Покрытие в БД: Алиев + Мустафаев (ул. Костякова, Тимирязевский).
    ("7713", "77",
     "Инспекция Федеральной налоговой службы №13 по г. Москве",
     "ИФНС №13 по г. Москве",
     "105064, г. Москва, ул. Земляной вал, д. 9",
     False,
     ["костякова", "тимирязевск", "савёловск", "савеловск",
      "коптево", "аэропорт", "бескудниковский", "войковский",
      "дмитровский", "дегунино"]),

    # ИФНС №15 — СВАО (Северо-Восточный АО). Адрес: 129110, ул. Большая
    # Переяславская, 16. Обслуживает: Алексеевский, Бабушкинский, Бутырский,
    # Лосиноостровский, Марфино, Марьина Роща, Останкинский, Отрадное,
    # Ростокино, Северное Медведково, Свиблово, Северный, Южное Медведково,
    # Ярославский.
    # Покрытие в БД: Шахин (ул. Снежная, Свиблово) + Шамилов (ул. Кибальчича,
    # Алексеевский).
    ("7715", "77",
     "Инспекция Федеральной налоговой службы №15 по г. Москве",
     "ИФНС №15 по г. Москве",
     "129110, г. Москва, ул. Большая Переяславская, д. 16",
     False,
     ["снежная", "свиблово", "алексеевский", "кибальчича",
      "ростокино", "марфино", "бутырский", "отрадное",
      "медведково", "ярославский"]),

    # ИФНС №24 — ЮАО (Южный АО). Адрес: 115201, Старокаширское ш., 4 к.11.
    # Обслуживает: Бирюлёво Восточное, Бирюлёво Западное, Братеево, Даниловский,
    # Донской, Зябликово, Москворечье-Сабурово, Нагатино-Садовники,
    # Нагатинский Затон, Нагорный, Орехово-Борисово Северное,
    # Орехово-Борисово Южное, Чертаново Северное, Чертаново Центральное,
    # Чертаново Южное.
    # Покрытие: Хайдаров (ул. Симоновский Вал, Даниловский) + Узоков
    # (ул. Лебедянская, Бирюлёво).
    ("7724", "77",
     "Инспекция Федеральной налоговой службы №24 по г. Москве",
     "ИФНС №24 по г. Москве",
     "115201, г. Москва, Старокаширское шоссе, д. 4, к. 11",
     False,
     ["симоновский", "даниловский", "лебедянская", "бирюлёво",
      "бирюлево", "нагатино", "донской", "чертаново",
      "зябликово", "орехово-борисово"]),

    # ИФНС №27 — ЮЗАО (Юго-Западный АО). Адрес: 117418, Новочеремушкинская,
    # 58 к.1. Обслуживает: Зюзино, Котловка, Северное Бутово, Южное Бутово,
    # Черёмушки.
    # Покрытие: Авьюзен (Адмирала Лазарева д.78) + Демир (Адмирала Лазарева д.39).
    # ВАЖНО: Академический + Тропарёво-Никулино + Тёплый Стан + Ясенево + Коньково
    # обслуживаются ИФНС №28 (см. EXISTING_UPDATES для 7728), их keywords
    # сюда НЕ кладём чтобы избежать конфликта.
    ("7727", "77",
     "Инспекция Федеральной налоговой службы №27 по г. Москве",
     "ИФНС №27 по г. Москве",
     "117418, г. Москва, ул. Новочеремушкинская, д. 58, к. 1",
     False,
     ["лазарева", "бутово", "зюзино", "котловка",
      "черёмушки", "черемушки"]),

    # ИФНС №31 — ЗАО (Западный АО). Адрес: 121351, Молодогвардейская, 23 к.1.
    # Обслуживает: Кунцево, Можайский, Фили-Давыдково, Крылатское, Внуково,
    # Дорогомилово, Ново-Переделкино, Очаково-Матвеевское, Проспект Вернадского,
    # Раменки, Солнцево, Тропарёво-Никулино, Филёвский парк.
    # Покрытие: Злобин + Мабутов (ул. Молодёжная, Кунцево).
    # ВАЖНО: keyword "молодёжная" с буквой ё, fallback "молодежная" с е —
    # оба варианта частые, добавляем обе.
    ("7731", "77",
     "Инспекция Федеральной налоговой службы №31 по г. Москве",
     "ИФНС №31 по г. Москве",
     "121351, г. Москва, ул. Молодогвардейская, д. 23, к. 1",
     False,
     ["молодёжная", "молодежная", "кунцево", "можайский",
      "фили", "давыдково", "крылатское", "вернадского"]),
]


# ============================================================================
# Migration steps
# ============================================================================

def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first()
    return row is not None


def _add_coverage_keywords_column(s: Session) -> bool:
    """Step 1: ALTER TABLE ADD COLUMN coverage_keywords (idempotent).

    Returns True if column was added, False if already existed.
    """
    conn = s.connection()
    if _column_exists(conn, "ifns_office", "coverage_keywords"):
        log.warning("[Pack 33.8] column ifns_office.coverage_keywords already exists, skip ALTER")
        return False

    log.warning("[Pack 33.8] adding column ifns_office.coverage_keywords (JSONB NOT NULL DEFAULT '[]')")
    conn.execute(text(
        "ALTER TABLE ifns_office "
        "ADD COLUMN coverage_keywords JSONB NOT NULL DEFAULT '[]'::jsonb"
    ))
    s.commit()
    return True


def _update_existing_records(s: Session) -> int:
    """Step 2: UPDATE coverage_keywords for existing 3 non-default records."""
    conn = s.connection()
    updated = 0
    for code, region_code, keywords in EXISTING_UPDATES:
        result = conn.execute(text(
            "UPDATE ifns_office "
            "SET coverage_keywords = CAST(:p_kws AS JSONB), "
            "    updated_at = NOW() "
            "WHERE code = :p_code AND region_code = :p_region"
        ), {
            "p_code": code,
            "p_region": region_code,
            "p_kws": json.dumps(keywords, ensure_ascii=False),
        })
        if result.rowcount > 0:
            log.warning(
                "[Pack 33.8] UPDATE existing %s/%s: %d keywords",
                region_code, code, len(keywords),
            )
            updated += 1
        else:
            log.warning(
                "[Pack 33.8] WARN: existing record %s/%s not found, skip update",
                region_code, code,
            )
    s.commit()
    return updated


def _insert_new_records(s: Session) -> tuple[int, int]:
    """Step 3: INSERT 7 new IFNS records.

    Returns (inserted, skipped_existing).
    """
    conn = s.connection()
    inserted = 0
    skipped = 0
    for row in NEW_RECORDS:
        code, region_code, full_name, short_name, address, is_default, keywords = row

        # Check if record with this (region_code, code) already exists
        existing = conn.execute(text(
            "SELECT id FROM ifns_office "
            "WHERE region_code = :p_region AND code = :p_code"
        ), {"p_region": region_code, "p_code": code}).first()

        if existing is not None:
            log.warning(
                "[Pack 33.8] record %s/%s already exists (id=%s), updating coverage_keywords only",
                region_code, code, existing[0],
            )
            conn.execute(text(
                "UPDATE ifns_office "
                "SET coverage_keywords = CAST(:p_kws AS JSONB), "
                "    updated_at = NOW() "
                "WHERE id = :p_id"
            ), {
                "p_kws": json.dumps(keywords, ensure_ascii=False),
                "p_id": existing[0],
            })
            skipped += 1
            continue

        conn.execute(text(
            "INSERT INTO ifns_office "
            "(code, region_code, full_name, short_name, address, is_default, "
            " is_active, coverage_keywords, created_at, updated_at) "
            "VALUES "
            "(:p_code, :p_region, :p_full_name, :p_short_name, :p_address, "
            " :p_is_default, TRUE, CAST(:p_kws AS JSONB), NOW(), NOW())"
        ), {
            "p_code": code,
            "p_region": region_code,
            "p_full_name": full_name,
            "p_short_name": short_name,
            "p_address": address,
            "p_is_default": is_default,
            "p_kws": json.dumps(keywords, ensure_ascii=False),
        })
        log.warning(
            "[Pack 33.8] INSERT %s/%s '%s' (%d keywords)",
            region_code, code, short_name, len(keywords),
        )
        inserted += 1
    s.commit()
    return inserted, skipped


def _verify_state(s: Session) -> None:
    """Final step: verify ifns_office state and print summary."""
    conn = s.connection()
    rows = list(conn.execute(text(
        "SELECT region_code, "
        "       COUNT(*) AS total, "
        "       SUM(CASE WHEN is_default THEN 1 ELSE 0 END) AS defaults, "
        "       SUM(CASE WHEN NOT is_default THEN 1 ELSE 0 END) AS specific, "
        "       SUM(CASE WHEN jsonb_array_length(coverage_keywords) > 0 THEN 1 ELSE 0 END) AS with_kws "
        "FROM ifns_office "
        "WHERE is_active = true "
        "GROUP BY region_code "
        "ORDER BY region_code"
    )))
    log.warning("[Pack 33.8] === Final ifns_office state ===")
    log.warning(
        "[Pack 33.8] %-8s %-8s %-10s %-10s %-10s",
        "region", "total", "default", "specific", "with_kws",
    )
    for r in rows:
        log.warning(
            "[Pack 33.8] %-8s %-8s %-10s %-10s %-10s",
            r.region_code, r.total, r.defaults, r.specific, r.with_kws,
        )


# ============================================================================
# Entry point
# ============================================================================

def run_migration() -> None:
    """Run Pack 33.8 migration: schema + data."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL not set. Set $env:DATABASE_URL='postgresql://...' first."
        )

    engine = create_engine(db_url)
    with Session(engine) as s:
        log.warning("[Pack 33.8] === Starting Pack 33.8 IFNS expansion migration ===")

        # Step 1: schema
        added = _add_coverage_keywords_column(s)
        if added:
            log.warning("[Pack 33.8] Step 1: column added")
        else:
            log.warning("[Pack 33.8] Step 1: column already present (idempotent skip)")

        # Step 2: update existing
        updated = _update_existing_records(s)
        log.warning("[Pack 33.8] Step 2: updated %d existing records", updated)

        # Step 3: insert new
        inserted, skipped = _insert_new_records(s)
        log.warning(
            "[Pack 33.8] Step 3: inserted %d new records, %d already existed (kws updated)",
            inserted, skipped,
        )

        # Step 4: verify
        _verify_state(s)

        log.warning("[Pack 33.8] === Done ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    run_migration()
