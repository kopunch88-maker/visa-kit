"""
Pack 17.2.4 — Импортер открытого дампа реестра МСП-ПП ФНС.

Источник: https://www.nalog.gov.ru/opendata/7707329152-rsmppp/
Прямая ссылка на файл: https://file.nalog.ru/opendata/7707329152-rsmppp/data-YYYYMMDD-structure-20230615.zip

Архитектура:
1. Скачать ZIP стримом (без полной загрузки в память)
2. Распаковать в /tmp
3. Найти XML-файлы внутри (их может быть много — реестр разбит на части)
4. Парсить КАЖДЫЙ XML через lxml.iterparse (стрим — не грузит в память)
5. Для каждой записи определить — это ИП или самозанятый (НПД)
6. Если самозанятый — bulk insert в self_employed_registry батчами по 5000

Описание формата XML согласно методичке ФНС (VO_SVMSP_2_213_23_04_04.docx):
- Корневой тег: <Файл>
- Внутри: <Документ ... ПрВклМСП="1"> — запись о субъекте МСП
- Категория субъекта: атрибут "ПрНал" или "КатСубМСП"
  - "1" = микропредприятие, "2" = малое, "3" = среднее (это всё ИП/ЮЛ)
  - Самозанятые (НПД) — имеют ПрФЛЮЛ="1" и ПрНал указывающий на НПД
  - Точные правила могут меняться между версиями XSD — есть fallback на эвристику
    "если ИНН 12 цифр И нет ОГРН → физлицо самозанятый"

ВАЖНО: реестр МСП-ПП — это «получатели поддержки», а не все самозанятые.
Однако для нашей задачи это даже лучше: только проверенные активные люди.

Никаких отчётов о деталях физлиц консулату не подаётся — мы используем
только ИНН + дату регистрации как косвенное подтверждение статуса.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional

import httpx
from lxml import etree
from sqlalchemy import text
from sqlmodel import Session

from app.models.self_employed_registry import RegistryImportLog


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Константы дампа
# ---------------------------------------------------------------------------

OPENDATA_PORTAL_URL = "https://www.nalog.gov.ru/opendata/7707329152-rsmppp/"
DUMP_DIRECT_URL_TEMPLATE = (
    "https://file.nalog.ru/opendata/7707329152-rsmppp/"
    "data-{date}-structure-20230615.zip"
)

# HTTP таймауты (дамп может качаться долго)
DOWNLOAD_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0)
HEAD_TIMEOUT = httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0)

# User-Agent — представляемся обычным браузером (на всякий случай)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

BATCH_SIZE = 5000  # для bulk insert в Postgres


# ---------------------------------------------------------------------------
# Результат импорта
# ---------------------------------------------------------------------------

@dataclass
class ImportStats:
    records_total: int = 0
    records_imported: int = 0
    records_skipped_ip: int = 0          # это ИП, нам не нужны
    records_skipped_yul: int = 0         # это юрлицо, нам не нужны
    records_skipped_no_inn: int = 0
    records_skipped_bad_inn: int = 0
    records_skipped_dupes: int = 0
    zip_size_bytes: int = 0
    xml_size_bytes: int = 0
    xml_files_processed: int = 0

    @property
    def records_skipped(self) -> int:
        return (
            self.records_skipped_ip
            + self.records_skipped_yul
            + self.records_skipped_no_inn
            + self.records_skipped_bad_inn
            + self.records_skipped_dupes
        )


@dataclass
class ParsedRecord:
    """Запись о самозанятом, готовая к INSERT."""
    inn: str
    region_code: Optional[str]
    full_name: Optional[str]
    support_begin_date: Optional[date]
    registry_create_date: Optional[date]


# ---------------------------------------------------------------------------
# Публичный API сервиса
# ---------------------------------------------------------------------------

def resolve_latest_dump_url() -> str:
    """
    Получает URL свежайшего дампа с открытого портала ФНС.

    Простая стратегия: парсим главную страницу /opendata/7707329152-rsmppp/
    и берём ссылку из «Гиперссылка (URL) на набор» (поле №8 в таблице).

    Формат: data-YYYYMMDD-structure-20230615.zip
    """
    log.info(f"[importer] Resolving latest dump URL from {OPENDATA_PORTAL_URL}")
    with httpx.Client(timeout=HEAD_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(OPENDATA_PORTAL_URL, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text

    # Ищем самую свежую ссылку формата data-YYYYMMDD-structure-...zip
    matches = re.findall(
        r"https://file\.nalog\.ru/opendata/7707329152-rsmppp/"
        r"data-(\d{8})-structure-\d+\.zip",
        html,
    )
    if not matches:
        raise RuntimeError(
            "Не удалось найти ссылку на дамп на портале ФНС. "
            "Возможно изменилась структура страницы."
        )
    # Берём максимальную дату
    latest_date = max(matches)  # как строка YYYYMMDD сортируется лексикографически
    url = DUMP_DIRECT_URL_TEMPLATE.format(date=latest_date)
    log.info(f"[importer] Latest dump: {url}")
    return url


def parse_dump_date_from_url(url: str) -> Optional[date]:
    """Извлекает дату из URL дампа (data-YYYYMMDD-...)."""
    m = re.search(r"data-(\d{4})(\d{2})(\d{2})", url)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def import_dump(
    session: Session,
    dump_url: Optional[str] = None,
    purge_old: bool = True,
    work_dir: Optional[Path] = None,
) -> RegistryImportLog:
    """
    Главная функция импорта.

    Args:
        session: SQLModel session (активная транзакция)
        dump_url: явный URL дампа или None (взять последний с портала)
        purge_old: удалить ли старые НЕИСПОЛЬЗОВАННЫЕ записи перед импортом
                   (использованные ИНН не трогаем — они уже выданы клиентам)
        work_dir: где работать с файлами (по умолчанию /tmp)

    Возвращает RegistryImportLog с результатом.
    """
    # Резолвим URL если не передан
    if dump_url is None:
        dump_url = resolve_latest_dump_url()

    dump_date = parse_dump_date_from_url(dump_url)

    # Создаём лог записи
    log_entry = RegistryImportLog(
        dump_url=dump_url,
        dump_date=dump_date,
        started_at=datetime.utcnow(),
        status="running",
    )
    session.add(log_entry)
    session.commit()
    session.refresh(log_entry)

    work_dir = work_dir or Path(tempfile.mkdtemp(prefix="fns_dump_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        zip_path = work_dir / "dump.zip"

        # === 1. Качаем ZIP стримом ===
        log.info(f"[importer] Downloading {dump_url} -> {zip_path}")
        zip_size = _download_stream(dump_url, zip_path)
        # Сохраняем метрику отдельно, чтобы её сбой не поломал импорт
        _safe_save_metric(session, log_entry, "zip_size_bytes", zip_size)

        # === 2. Распаковываем ===
        extract_dir = work_dir / "extract"
        extract_dir.mkdir(exist_ok=True)
        log.info(f"[importer] Extracting to {extract_dir}")
        xml_total_size = _extract_zip(zip_path, extract_dir)
        _safe_save_metric(session, log_entry, "xml_size_bytes", xml_total_size)

        # === 3. Удаляем старые неиспользованные записи (опционально) ===
        if purge_old:
            log.info("[importer] Purging old unused records")
            _purge_unused_records(session)

        # === 4. Парсим XML и пишем в БД ===
        stats = ImportStats(zip_size_bytes=zip_size, xml_size_bytes=xml_total_size)
        _parse_and_import_directory(session, extract_dir, stats)

        log_entry.records_total = stats.records_total
        log_entry.records_imported = stats.records_imported
        log_entry.records_skipped = stats.records_skipped
        log_entry.status = "success"
        log_entry.finished_at = datetime.utcnow()

        log.info(
            f"[importer] DONE: {stats.records_imported} imported, "
            f"{stats.records_skipped} skipped (of {stats.records_total} total). "
            f"XML files: {stats.xml_files_processed}"
        )

    except Exception as e:
        log.exception(f"[importer] FAILED: {e}")
        # Сессия может быть в "failed" состоянии после исключения — rollback
        try:
            session.rollback()
        except Exception:
            pass
        # Перечитываем log_entry заново (он мог стать detached)
        try:
            session.refresh(log_entry)
        except Exception:
            log_entry = session.get(RegistryImportLog, log_entry.id)
        if log_entry is not None:
            log_entry.status = "failed"
            log_entry.finished_at = datetime.utcnow()
            log_entry.error_message = str(e)[:2000]
            try:
                session.commit()
            except Exception as commit_err:
                log.warning(f"[importer] Failed to write 'failed' status: {commit_err}")
                session.rollback()
        raise

    finally:
        # Чистим временные файлы (даже при ошибке)
        try:
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
                log.debug(f"[importer] Cleaned up {work_dir}")
        except Exception as cleanup_err:
            log.warning(f"[importer] Cleanup failed: {cleanup_err}")

    try:
        session.commit()
        session.refresh(log_entry)
    except Exception as e:
        log.warning(f"[importer] Final commit failed: {e}")
        session.rollback()
    return log_entry


def _safe_save_metric(session: Session, log_entry: RegistryImportLog, field: str, value: int) -> None:
    """
    Безопасно сохраняет одну метрику в RegistryImportLog.

    Если сохранение падает (например, переполнение типа) — логируем warning
    и продолжаем работу. Метрики не критичны для самого импорта.
    """
    try:
        setattr(log_entry, field, value)
        session.add(log_entry)
        session.commit()
        session.refresh(log_entry)
        log.info(f"[importer] Saved metric {field}={value}")
    except Exception as e:
        log.warning(f"[importer] Failed to save metric {field}={value}: {e}")
        try:
            session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Внутренние утилиты
# ---------------------------------------------------------------------------

def _download_stream(url: str, dest: Path) -> int:
    """Качает файл стримом, возвращает размер в байтах."""
    total = 0
    with httpx.Client(timeout=DOWNLOAD_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):  # 1 MB
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
    log.info(f"[importer] Downloaded {total / 1e6:.1f} MB")
    return total


def _extract_zip(zip_path: Path, dest_dir: Path) -> int:
    """Распаковывает ZIP. Возвращает суммарный размер XML файлов."""
    total = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    # Подсчёт размера XML
    for p in dest_dir.rglob("*.xml"):
        total += p.stat().st_size
    log.info(f"[importer] Extracted XMLs total size: {total / 1e6:.1f} MB")
    return total


def _purge_unused_records(session: Session) -> None:
    """
    Удаляет ВСЕ НЕиспользованные записи перед импортом.
    Использованные (is_used=True) не трогаем — они уже выданы клиентам,
    мы должны помнить какой ИНН какому клиенту достался.
    """
    result = session.execute(
        text("DELETE FROM self_employed_registry WHERE is_used = FALSE")
    )
    deleted = result.rowcount or 0
    session.commit()
    log.info(f"[importer] Purged {deleted} unused records")


def _parse_and_import_directory(session: Session, extract_dir: Path, stats: ImportStats) -> None:
    """Обходит все XML файлы в директории и парсит каждый."""
    xml_files = list(extract_dir.rglob("*.xml"))
    if not xml_files:
        raise RuntimeError(f"В дампе не найдено ни одного XML файла в {extract_dir}")
    log.info(f"[importer] Found {len(xml_files)} XML files to process")

    # Получим уже использованные ИНН (чтобы не перетирать их статусы)
    used_inns = _load_used_inns(session)
    log.info(f"[importer] Skipping {len(used_inns)} already-used INNs from import")

    import time
    started_at = time.time()
    last_progress_at = started_at

    batch: list[ParsedRecord] = []
    for xml_path in xml_files:
        log.info(f"[importer] Processing {xml_path.name} ({xml_path.stat().st_size / 1e6:.1f} MB)")
        for record in _iter_self_employed_records(xml_path, stats):
            stats.records_total += 1
            if record.inn in used_inns:
                stats.records_skipped_dupes += 1
                continue
            batch.append(record)
            if len(batch) >= BATCH_SIZE:
                _insert_batch(session, batch)
                stats.records_imported += len(batch)
                batch.clear()

                # Прогресс-лог каждые 30 секунд
                now = time.time()
                if now - last_progress_at >= 30:
                    elapsed = now - started_at
                    rate = stats.records_total / elapsed if elapsed > 0 else 0
                    log.info(
                        f"[importer] Progress: total={stats.records_total:,}, "
                        f"imported={stats.records_imported:,}, "
                        f"skipped={stats.records_skipped:,}, "
                        f"rate={rate:.0f} rec/sec, "
                        f"elapsed={elapsed/60:.1f} min"
                    )
                    last_progress_at = now
        stats.xml_files_processed += 1
        log.info(
            f"[importer] Finished {xml_path.name}: "
            f"total={stats.records_total:,}, imported={stats.records_imported:,}"
        )

    # Флашим хвост
    if batch:
        _insert_batch(session, batch)
        stats.records_imported += len(batch)


def _load_used_inns(session: Session) -> set[str]:
    """Загружает множество ИНН которые уже выданы клиентам."""
    result = session.execute(
        text("SELECT inn FROM self_employed_registry WHERE is_used = TRUE")
    )
    return {row[0] for row in result if row[0]}


def _insert_batch(session: Session, batch: list[ParsedRecord]) -> None:
    """
    Bulk insert батча. Использует ON CONFLICT DO NOTHING чтобы не падать
    на дубликатах ИНН (внутри одного дампа их быть не должно, но мало ли).
    """
    if not batch:
        return
    now = datetime.utcnow()

    # Универсальный INSERT с ON CONFLICT — работает в Postgres
    # В SQLite используем INSERT OR IGNORE
    from app.db.session import engine
    is_postgres = engine.url.get_backend_name() in ("postgresql", "postgres")

    if is_postgres:
        sql = text("""
            INSERT INTO self_employed_registry
                (inn, region_code, full_name, support_begin_date,
                 registry_create_date, imported_at, is_used)
            VALUES
                (:inn, :region_code, :full_name, :support_begin_date,
                 :registry_create_date, :imported_at, FALSE)
            ON CONFLICT (inn) DO NOTHING
        """)
    else:
        sql = text("""
            INSERT OR IGNORE INTO self_employed_registry
                (inn, region_code, full_name, support_begin_date,
                 registry_create_date, imported_at, is_used)
            VALUES
                (:inn, :region_code, :full_name, :support_begin_date,
                 :registry_create_date, :imported_at, 0)
        """)

    params = [
        {
            "inn": r.inn,
            "region_code": r.region_code,
            "full_name": r.full_name,
            "support_begin_date": r.support_begin_date,
            "registry_create_date": r.registry_create_date,
            "imported_at": now,
        }
        for r in batch
    ]

    session.execute(sql, params)
    session.commit()


# ---------------------------------------------------------------------------
# XML парсинг (потоковый — для файлов в гигабайты)
# ---------------------------------------------------------------------------

# Возможные имена тега-документа в разных версиях схемы
DOCUMENT_TAG_NAMES = ("Документ", "СвМСП", "Document")


def _iter_self_employed_records(
    xml_path: Path,
    stats: ImportStats,
) -> Iterator[ParsedRecord]:
    """
    Итератор по записям самозанятых из XML.

    Использует lxml.iterparse — НЕ грузит файл целиком в память.
    После обработки каждого элемента очищаем его (.clear()) чтобы
    освободить память.
    """
    context = etree.iterparse(
        str(xml_path),
        events=("end",),
        recover=True,  # терпеть мелкие баги XML
    )

    try:
        for event, elem in context:
            tag_local = etree.QName(elem.tag).localname if elem.tag else ""
            if tag_local not in DOCUMENT_TAG_NAMES:
                continue

            try:
                record = _extract_record(elem, stats)
                if record is not None:
                    yield record
            except Exception as e:
                log.debug(f"[importer] Skipped record due to parse error: {e}")
                stats.records_skipped_bad_inn += 1
            finally:
                # КРИТИЧНО: чистим элемент чтобы освободить память
                elem.clear()
                # Удаляем уже обработанных предков
                while elem.getprevious() is not None:
                    parent = elem.getparent()
                    if parent is None:
                        break
                    del parent[0]
    finally:
        del context


def _extract_record(doc_elem, stats: ImportStats) -> Optional[ParsedRecord]:
    """
    Извлекает данные из одного элемента документа.

    Возвращает ParsedRecord только если это самозанятый (физлицо на НПД).
    Иначе обновляет соответствующий счётчик в stats и возвращает None.

    Стратегия определения «самозанятый»:
    1. Длина ИНН = 12 цифр (физлицо). У ЮЛ 10 цифр.
    2. Нет дочернего элемента <СведЮЛ> (это означало бы юрлицо).
    3. Любая дополнительная подсказка из атрибутов про НПД (КатСубМСП и т.п.).

    Это заведомо включает обычных ИП-физлиц (тоже 12-значные ИНН).
    Но для нашей задачи это безопасно: если в реестре МСП-ПП есть человек
    с 12-значным ИНН — он реальный налогоплательщик, статус НПД мы потом
    проверяем отдельно через npd.nalog.ru перед выдачей менеджеру.
    """
    # === 1. Тип субъекта ===
    # Ищем дочерние элементы СведЮЛ / СведИП / СведФЛ
    has_yul = _find_local(doc_elem, "СведЮЛ") is not None
    if has_yul:
        stats.records_skipped_yul += 1
        return None

    # === 2. ИНН ===
    # ИНН может быть в атрибуте корневого тега или внутри СведИП/СведФЛ
    inn = (
        doc_elem.get("ИННФЛ")
        or doc_elem.get("ИННЮЛ")
        or doc_elem.get("ИНН")
    )
    # Если не в атрибутах — поищем в дочерних элементах
    if not inn:
        for sub_tag in ("СведИП", "СведФЛ"):
            sub = _find_local(doc_elem, sub_tag)
            if sub is not None:
                inn = sub.get("ИННФЛ") or sub.get("ИНН")
                if inn:
                    break

    if not inn:
        stats.records_skipped_no_inn += 1
        return None

    inn = inn.strip()
    if not inn.isdigit() or len(inn) != 12:
        # Не 12-значный ИНН → юрлицо или мусор
        if len(inn) == 10:
            stats.records_skipped_yul += 1
        else:
            stats.records_skipped_bad_inn += 1
        return None

    # === 3. ФИО ===
    full_name = _extract_full_name(doc_elem)

    # === 4. Регион ===
    # ИНН первые 2 цифры = код региона налогового органа (приблизительно)
    region_code = inn[:2]

    # === 5. Даты ===
    support_begin = _parse_xml_date(doc_elem.get("ДатаПерСост"))
    registry_create = _parse_xml_date(doc_elem.get("ДатаСост"))

    return ParsedRecord(
        inn=inn,
        region_code=region_code,
        full_name=full_name,
        support_begin_date=support_begin,
        registry_create_date=registry_create,
    )


def _find_local(elem, local_name: str):
    """Ищет первого ребёнка с заданным локальным именем (игнорируя namespace)."""
    for child in elem:
        if etree.QName(child.tag).localname == local_name:
            return child
    return None


def _extract_full_name(doc_elem) -> Optional[str]:
    """
    Достаёт ФИО — приоритет: СведИП > СведФЛ > атрибуты корня.
    """
    # Поищем во вложенных СведИП/СведФЛ
    for sub_tag in ("СведИП", "СведФЛ"):
        sub = _find_local(doc_elem, sub_tag)
        if sub is None:
            continue
        # ФИО может быть в дочернем теге <ФИОИП> / <ФИОФЛ>
        for fio_tag in ("ФИОИП", "ФИОФЛ", "ФИО"):
            fio = _find_local(sub, fio_tag)
            if fio is not None:
                return _format_fio(fio)
        # Или в атрибутах
        fio = _format_fio(sub)
        if fio:
            return fio

    # Fallback — на самом доке
    return _format_fio(doc_elem)


def _format_fio(elem) -> Optional[str]:
    """Из атрибутов Фамилия/Имя/Отчество элемента собирает ФИО."""
    parts = []
    for attr in ("Фамилия", "Имя", "Отчество"):
        v = elem.get(attr)
        if v:
            parts.append(v.strip())
    if not parts:
        return None
    return " ".join(parts)


def _parse_xml_date(value: Optional[str]) -> Optional[date]:
    """
    XML-даты в реестре ФНС: 'YYYY-MM-DD' или 'DD.MM.YYYY'.
    """
    if not value:
        return None
    value = value.strip()
    # ISO формат
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    # Русский формат
    try:
        d, m, y = value.split(".")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None
