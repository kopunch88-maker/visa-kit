"""
Pack 17.2.5 — Импортер открытого дампа SNRIP ФНС.

Источник: https://www.nalog.gov.ru/opendata/7707329152-snrip/
«Сведения о специальных налоговых режимах, применяемых ИП»

Прямая ссылка: https://file.nalog.ru/opendata/7707329152-snrip/data-YYYYMMDD-structure-20241025.zip
Обновляется ежемесячно 25-го числа.

Структура XML (подтверждена через diagnose_snrip + count_modes):
<Файл ВерсФорм="..." ИдФайл="..." КолДок="..." ТипИнф="..." ВерсПрог="...">
  <ИдОтпр><ФИООтв Имя="..." Фамилия="..."/></ИдОтпр>
  <Документ ИдДок="..." ДатаДок="25.04.2026" ДатаСост="01.04.2026">
    <СведНП ИННФЛ="773127952793" ОГРНИП="318774600221632">
      <ФИО Фамилия="..." Имя="..." Отчество="..."/>
    </СведНП>
    <СведСНР ПризнСНР="5"/>     ← код режима (5 = НПД)
    <СведСНР ПризнСНР="1"/>     ← у одного ИП может быть несколько режимов
  </Документ>
  ... ещё ~899 <Документ>
</Файл>

Коды ПризнСНР (подтверждены статистикой):
  1 = УСН  (~65%)
  2 = ЕСХН (~4%)
  3 = АУСН (~1%)
  4 = ПСН  (~20%)
  5 = НПД  (~10%) ← НАШ КОД

Объёмы (на 25.04.2026):
- ZIP:               ~265 МБ
- XML распакованный: ~1.81 ГБ (5251 файлов × 900 ИП = ~4.7 млн ИП)
- ИП с НПД:          ~565,000 записей
- ИП ТОЛЬКО на НПД:  ~580,000 (only_5)

Стратегия импорта (Pack 17.2.5):
  Берём только ИП у которых ПризнСНР=5 (любой — даже если есть другие режимы).
  Эти 565k ИП — реальные плательщики НПД, проходят проверку через
  npd.nalog.ru/check-status. ОГРНИП у них есть, в ЕГРИП они видны,
  но это компромисс который мы приняли (см. PROJECT_STATE.md).
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional, Set

import httpx
from lxml import etree
from sqlalchemy import text
from sqlmodel import Session

from app.models.self_employed_registry import RegistryImportLog


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Константы дампа
# ---------------------------------------------------------------------------

OPENDATA_PORTAL_URL = "https://www.nalog.gov.ru/opendata/7707329152-snrip/"
DUMP_DIRECT_URL_TEMPLATE = (
    "https://file.nalog.ru/opendata/7707329152-snrip/"
    "data-{date}-structure-20241025.zip"
)

DOWNLOAD_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0)
HEAD_TIMEOUT = httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

BATCH_SIZE = 500  # уменьшен с 5000 для работы через медленный Railway proxy

# Код режима НПД в реестре snrip
NPD_CODE = "5"


# ---------------------------------------------------------------------------
# Результат импорта
# ---------------------------------------------------------------------------

@dataclass
class ImportStats:
    records_total: int = 0          # всего <Документ> разобрано
    records_imported: int = 0       # с НПД и сохранены
    records_skipped_no_npd: int = 0 # без режима НПД (не наша цель)
    records_skipped_no_inn: int = 0
    records_skipped_bad_inn: int = 0
    records_skipped_used: int = 0   # ИНН уже выдан клиенту ранее
    zip_size_bytes: int = 0
    xml_size_bytes: int = 0
    xml_files_processed: int = 0

    @property
    def records_skipped(self) -> int:
        return (
            self.records_skipped_no_npd
            + self.records_skipped_no_inn
            + self.records_skipped_bad_inn
            + self.records_skipped_used
        )


@dataclass
class ParsedRecord:
    inn: str
    region_code: Optional[str]
    full_name: Optional[str]
    support_begin_date: Optional[date]      # ДатаДок (когда запись попала в дамп)
    registry_create_date: Optional[date]    # ДатаСост (на какую дату актуальны данные)


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

def resolve_latest_dump_url() -> str:
    """Ищет URL свежайшего дампа SNRIP на портале ФНС."""
    log.info(f"[importer] Resolving latest dump URL from {OPENDATA_PORTAL_URL}")
    with httpx.Client(timeout=HEAD_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(OPENDATA_PORTAL_URL, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text

    matches = re.findall(
        r"https://file\.nalog\.ru/opendata/7707329152-snrip/"
        r"data-(\d{8})-structure-\d+\.zip",
        html,
    )
    if not matches:
        raise RuntimeError(
            "Не удалось найти ссылку на дамп SNRIP на портале ФНС. "
            "Возможно изменилась структура страницы."
        )
    latest_date = max(matches)
    url = DUMP_DIRECT_URL_TEMPLATE.format(date=latest_date)
    log.info(f"[importer] Latest dump: {url}")
    return url


def parse_dump_date_from_url(url: str) -> Optional[date]:
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
    *,
    local_zip_path: Optional[Path] = None,
) -> RegistryImportLog:
    """
    Главная функция импорта.

    Args:
        session: SQLModel session
        dump_url: явный URL дампа или None (взять последний с портала)
        purge_old: удалить ли старые НЕИСПОЛЬЗОВАННЫЕ записи перед импортом
        work_dir: рабочая директория (по умолчанию /tmp)
        local_zip_path: путь к УЖЕ скачанному ZIP (если задан — не качаем заново)

    Возвращает RegistryImportLog с результатом.
    """
    if dump_url is None and local_zip_path is None:
        dump_url = resolve_latest_dump_url()

    # Если есть локальный ZIP — реконструируем dump_url по имени файла
    if local_zip_path is not None and dump_url is None:
        dump_url = f"local://{local_zip_path.name}"

    dump_date = parse_dump_date_from_url(dump_url) if dump_url else None

    log_entry = RegistryImportLog(
        dump_url=dump_url or "<unknown>",
        dump_date=dump_date,
        started_at=datetime.utcnow(),
        status="running",
    )
    session.add(log_entry)
    session.commit()
    session.refresh(log_entry)

    work_dir = work_dir or Path(tempfile.mkdtemp(prefix="fns_snrip_"))
    work_dir.mkdir(parents=True, exist_ok=True)
    cleanup_work_dir = local_zip_path is None  # чистим только если сами скачали

    try:
        if local_zip_path is not None:
            zip_path = local_zip_path
            if not zip_path.exists():
                raise FileNotFoundError(f"local_zip_path does not exist: {zip_path}")
            log.info(f"[importer] Using local ZIP: {zip_path}")
        else:
            zip_path = work_dir / "dump.zip"
            log.info(f"[importer] Downloading {dump_url} -> {zip_path}")
            zip_size = _download_stream(dump_url, zip_path)
            _safe_save_metric(session, log_entry, "zip_size_bytes", zip_size)

        zip_size = zip_path.stat().st_size
        _safe_save_metric(session, log_entry, "zip_size_bytes", zip_size)

        # === 3. Удаляем старые неиспользованные записи ===
        if purge_old:
            log.info("[importer] Purging old unused records")
            _purge_unused_records(session)

        # === 4. Парсим XML ПРЯМО ИЗ ZIP (без распаковки на диск!) ===
        # Это критично — экономит 1.8 ГБ места и время на распаковку
        stats = ImportStats(zip_size_bytes=zip_size)
        _parse_zip_directly(session, zip_path, stats)
        _safe_save_metric(session, log_entry, "xml_size_bytes", stats.xml_size_bytes)

        # === 5. Финальные метрики ===
        try:
            session.refresh(log_entry)
        except Exception:
            log_entry = session.get(RegistryImportLog, log_entry.id)
        log_entry.records_total = stats.records_total
        log_entry.records_imported = stats.records_imported
        log_entry.records_skipped = stats.records_skipped
        log_entry.status = "success"
        log_entry.finished_at = datetime.utcnow()

        log.info(
            f"[importer] DONE: {stats.records_imported:,} imported, "
            f"{stats.records_skipped:,} skipped (of {stats.records_total:,} total). "
            f"XML files: {stats.xml_files_processed}"
        )

    except Exception as e:
        log.exception(f"[importer] FAILED: {e}")
        try:
            session.rollback()
        except Exception:
            pass
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
        if cleanup_work_dir:
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
    try:
        setattr(log_entry, field, value)
        session.add(log_entry)
        session.commit()
        session.refresh(log_entry)
        log.info(f"[importer] Saved metric {field}={value:,}")
    except Exception as e:
        log.warning(f"[importer] Failed to save metric {field}={value}: {e}")
        try:
            session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Скачивание и парсинг
# ---------------------------------------------------------------------------

def _download_stream(url: str, dest: Path) -> int:
    total = 0
    last_log = 0
    with httpx.Client(
        timeout=DOWNLOAD_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=4 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
                        if total - last_log >= 50 * 1024 * 1024:
                            log.info(f"[importer] Downloaded {total / 1e6:.1f} MB...")
                            last_log = total
    log.info(f"[importer] Downloaded {total / 1e6:.1f} MB total")
    return total


def _purge_unused_records(session: Session) -> None:
    """Удаляет НЕиспользованные записи. is_used=TRUE не трогаем."""
    result = session.execute(
        text("DELETE FROM self_employed_registry WHERE is_used = FALSE")
    )
    deleted = result.rowcount or 0
    session.commit()
    log.info(f"[importer] Purged {deleted:,} unused records")


def _load_used_inns(session: Session) -> Set[str]:
    result = session.execute(
        text("SELECT inn FROM self_employed_registry WHERE is_used = TRUE")
    )
    return {row[0] for row in result if row[0]}


def _parse_zip_directly(session: Session, zip_path: Path, stats: ImportStats) -> None:
    """
    Парсит XML файлы ПРЯМО ИЗ ZIP, без распаковки на диск.

    zipfile.open() возвращает stream — lxml.iterparse читает поэлементно.
    Память не растёт, диск не нужен дополнительно.
    """
    import time
    started_at = time.time()
    last_progress_at = started_at
    last_file_log_at = started_at

    used_inns = _load_used_inns(session)
    log.info(f"[importer] {len(used_inns):,} used INNs will be skipped")

    with zipfile.ZipFile(zip_path, "r") as zf:
        xml_files = [f for f in zf.namelist() if f.lower().endswith(".xml")]
        if not xml_files:
            raise RuntimeError(f"В ZIP нет XML файлов: {zip_path}")

        log.info(f"[importer] Found {len(xml_files):,} XML files to process")

        # Аккумулируем размер xml для статистики
        for fn in xml_files:
            stats.xml_size_bytes += zf.getinfo(fn).file_size

        batch: list[ParsedRecord] = []

        log.info(f"[importer] Starting to process XMLs (batch_size={BATCH_SIZE})...")

        for i, xml_name in enumerate(xml_files, 1):
            # Лог каждые 5 секунд: на каком файле сейчас
            now = time.time()
            if now - last_file_log_at >= 5:
                elapsed = now - started_at
                rate_docs = stats.records_total / elapsed if elapsed > 0 else 0
                log.info(
                    f"[importer] At file {i}/{len(xml_files)}, "
                    f"docs={stats.records_total:,}, "
                    f"NPD={stats.records_imported + len(batch):,} "
                    f"(buffered={len(batch)}), "
                    f"rate={rate_docs:.0f} doc/sec, "
                    f"elapsed={elapsed/60:.1f} min"
                )
                last_file_log_at = now

            with zf.open(xml_name) as raw:
                # КРИТИЧНО: читаем XML целиком в BytesIO.
                # lxml.iterparse некорректно работает со stream от zipfile.open()
                # (в некоторых случаях зависает потому что пытается seek() который не поддерживается).
                # Каждый XML всего ~350 КБ, читать его целиком в память безопасно.
                xml_bytes = raw.read()

            # Парсим из BytesIO (полностью в памяти)
            xml_stream = io.BytesIO(xml_bytes)
            for record in _iter_npd_records(xml_stream, stats):
                if record.inn in used_inns:
                    stats.records_skipped_used += 1
                    continue
                batch.append(record)
                if len(batch) >= BATCH_SIZE:
                    log.debug(f"[importer] Inserting batch of {len(batch)} records...")
                    t_insert = time.time()
                    _insert_batch(session, batch)
                    insert_time = time.time() - t_insert
                    if insert_time > 5:
                        log.warning(
                            f"[importer] SLOW INSERT: {len(batch)} records "
                            f"took {insert_time:.1f}s"
                        )
                    stats.records_imported += len(batch)
                    batch.clear()

            stats.xml_files_processed += 1

            # Гарантированный лог после первого файла — чтобы убедиться что парсер живой
            if i == 1:
                log.info(
                    f"[importer] FIRST FILE PROCESSED: "
                    f"docs={stats.records_total}, NPD found={len(batch)}, "
                    f"skipped_no_npd={stats.records_skipped_no_npd}"
                )

        # Хвост
        if batch:
            log.info(f"[importer] Inserting final batch of {len(batch)} records...")
            _insert_batch(session, batch)
            stats.records_imported += len(batch)

        log.info(
            f"[importer] Parsing complete. "
            f"Files processed: {stats.xml_files_processed}/{len(xml_files)}, "
            f"docs total: {stats.records_total:,}, "
            f"NPD imported: {stats.records_imported:,}"
        )


def _iter_npd_records(stream, stats: ImportStats) -> Iterator[ParsedRecord]:
    """
    Стримово парсит XML и yield-ит только ИП с режимом НПД.

    Логика:
    - При входе в <Документ> сбрасываем буфер
    - Внутри ловим <СведНП> (ИНН, ОГРНИП), <ФИО>, <СведСНР ПризнСНР=...>
    - При закрытии <Документ>:
      - если в собранных режимах есть NPD_CODE → yield
      - иначе stats.records_skipped_no_npd
    """
    inn: Optional[str] = None
    full_name: Optional[str] = None
    modes: list[str] = []
    doc_date: Optional[date] = None      # ДатаДок
    state_date: Optional[date] = None    # ДатаСост

    in_document = False

    for event, elem in etree.iterparse(
        stream,
        events=("start", "end"),
        recover=True,
    ):
        local = etree.QName(elem.tag).localname if elem.tag else ""

        if event == "start" and local == "Документ":
            in_document = True
            inn = None
            full_name = None
            modes = []
            doc_date = _parse_date(elem.get("ДатаДок"))
            state_date = _parse_date(elem.get("ДатаСост"))
            continue

        if event == "end":
            if local == "СведНП" and in_document:
                inn_value = elem.get("ИННФЛ")
                if inn_value and inn_value.isdigit() and len(inn_value) == 12:
                    inn = inn_value

                # ФИО — дочерний тег
                for child in elem:
                    if etree.QName(child.tag).localname == "ФИО":
                        parts = []
                        for attr in ("Фамилия", "Имя", "Отчество"):
                            v = child.get(attr)
                            if v:
                                parts.append(v.strip())
                        if parts:
                            full_name = " ".join(parts)
                        break
                elem.clear()
                continue

            if local == "СведСНР" and in_document:
                code = elem.get("ПризнСНР")
                if code:
                    modes.append(code)
                elem.clear()
                continue

            if local == "Документ":
                stats.records_total += 1

                if not inn:
                    stats.records_skipped_no_inn += 1
                elif NPD_CODE not in modes:
                    stats.records_skipped_no_npd += 1
                else:
                    yield ParsedRecord(
                        inn=inn,
                        region_code=inn[:2] if inn else None,
                        full_name=full_name,
                        support_begin_date=doc_date,
                        registry_create_date=state_date,
                    )

                in_document = False
                inn = None
                full_name = None
                modes = []
                doc_date = None
                state_date = None

                # Чистим память
                elem.clear()
                while elem.getprevious() is not None:
                    parent = elem.getparent()
                    if parent is None:
                        break
                    del parent[0]


def _parse_date(value: Optional[str]) -> Optional[date]:
    """XML-даты ФНС: 'DD.MM.YYYY' или 'YYYY-MM-DD'."""
    if not value:
        return None
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        d, m, y = value.split(".")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _insert_batch(session: Session, batch: list[ParsedRecord]) -> None:
    if not batch:
        return
    now = datetime.utcnow()

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

    # Retry up to 3 times если timeout/connection error
    last_error = None
    for attempt in range(1, 4):
        try:
            session.execute(sql, params)
            session.commit()
            return
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            is_retriable = any(
                marker in err_msg
                for marker in (
                    "timeout", "timed out", "connection", "ssl", "broken pipe",
                    "could not", "operationalerror",
                )
            )
            log.warning(
                f"[importer] INSERT batch attempt {attempt}/3 failed "
                f"({type(e).__name__}): {str(e)[:200]}"
            )
            try:
                session.rollback()
            except Exception:
                pass
            if not is_retriable or attempt == 3:
                raise
            import time as _time
            _time.sleep(2 * attempt)  # backoff: 2s, 4s

    if last_error:
        raise last_error
