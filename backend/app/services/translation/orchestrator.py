"""
Pack 15 — translation orchestrator.

Управляет переводом всего пакета (или одного документа) для заявки:
1. Создаёт записи Translation со статусом PENDING (если ещё нет)
2. Параллельно (с ограничением concurrency=3) переводит каждый kind:
   - рендерит русский DOCX через templates_engine
   - прогоняет через docx_translator.translate_docx
   - сохраняет в R2
   - обновляет запись Translation: DONE + storage_key, или FAILED + error_message
3. Если перевод одного документа упал — остальные продолжают

Используется из api/translations.py через FastAPI BackgroundTasks.
Создаёт собственную Session(engine) — за пределами HTTP-контекста.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.db.session import engine
from app.models import Application, Translation, TranslationKind, TranslationStatus
from app.services.storage import get_storage
from app.templates_engine import (
    render_contract, render_act, render_invoice,
    render_employer_letter, render_cv, render_bank_statement,
)

from .docx_translator import translate_docx

log = logging.getLogger(__name__)


# Параллелизм: одновременно не больше 3 переводов чтобы не упереться
# в OpenRouter rate limit (особенно если несколько менеджеров жмут кнопку)
MAX_CONCURRENT = 3


# Маппинг kind → (рендер-функция, имя файла на испанском)
KIND_CONFIG: dict[TranslationKind, dict] = {
    TranslationKind.CONTRACT: {
        "filename": "01_Contrato.docx",
        "render": lambda app, sess: render_contract(app, sess),
    },
    TranslationKind.ACT_1: {
        "filename": "02_Acta_1.docx",
        "render": lambda app, sess: render_act(app, sess, 1),
    },
    TranslationKind.ACT_2: {
        "filename": "03_Acta_2.docx",
        "render": lambda app, sess: render_act(app, sess, 2),
    },
    TranslationKind.ACT_3: {
        "filename": "04_Acta_3.docx",
        "render": lambda app, sess: render_act(app, sess, 3),
    },
    TranslationKind.INVOICE_1: {
        "filename": "05_Factura_1.docx",
        "render": lambda app, sess: render_invoice(app, sess, 1),
    },
    TranslationKind.INVOICE_2: {
        "filename": "06_Factura_2.docx",
        "render": lambda app, sess: render_invoice(app, sess, 2),
    },
    TranslationKind.INVOICE_3: {
        "filename": "07_Factura_3.docx",
        "render": lambda app, sess: render_invoice(app, sess, 3),
    },
    TranslationKind.EMPLOYER_LETTER: {
        "filename": "08_Carta_de_la_empresa.docx",
        "render": lambda app, sess: render_employer_letter(app, sess),
    },
    TranslationKind.CV: {
        "filename": "09_CV.docx",
        "render": lambda app, sess: render_cv(app, sess),
    },
    TranslationKind.BANK_STATEMENT: {
        "filename": "10_Extracto_bancario.docx",
        "render": lambda app, sess: render_bank_statement(app, sess),
    },
}


# Все типы по умолчанию для «Перевести пакет»
ALL_KINDS = list(KIND_CONFIG.keys())


def _r2_key(application_id: int, kind: TranslationKind) -> str:
    """Уникальный R2-ключ. Timestamp в имени — чтобы при retry старые не перетирались."""
    ts = int(time.time())
    return f"translations/app_{application_id}/{kind.value}_{ts}.docx"


async def _translate_one(
    application_id: int,
    kind: TranslationKind,
    semaphore: asyncio.Semaphore,
) -> None:
    """
    Переводит один документ одного типа.
    Открывает свою Session — нельзя шарить sessions между корутинами.
    """
    async with semaphore:
        log.info(f"[translation:orch] Starting {kind.value} for app {application_id}")
        config = KIND_CONFIG[kind]

        # Используем отдельную сессию для каждого таска
        with Session(engine) as session:
            # Найдём запись Translation (она уже создана в start_translation)
            tr = session.exec(
                select(Translation)
                .where(Translation.application_id == application_id)
                .where(Translation.kind == kind)
            ).first()

            if not tr:
                log.error(f"[translation:orch] Translation row missing for app={application_id} kind={kind.value}")
                return

            tr.status = TranslationStatus.IN_PROGRESS
            session.add(tr)
            session.commit()
            session.refresh(tr)

            try:
                application = session.get(Application, application_id)
                if not application:
                    raise ValueError(f"Application {application_id} not found")

                # 1. Рендерим русский DOCX
                log.info(f"[translation:orch] Rendering RU docx for {kind.value}...")
                ru_bytes = config["render"](application, session)
                log.info(f"[translation:orch] RU docx rendered: {len(ru_bytes)} bytes")

            except Exception as e:
                log.error(f"[translation:orch] Render failed for {kind.value}: {e}", exc_info=True)
                tr.status = TranslationStatus.FAILED
                tr.error_message = f"Render failed: {str(e)[:500]}"
                tr.completed_at = datetime.utcnow()
                session.add(tr)
                session.commit()
                return

        # 2. Переводим (вне сессии — долгая LLM-операция, не держим коннект)
        try:
            log.info(f"[translation:orch] Translating {kind.value} via LLM...")
            es_bytes = await translate_docx(ru_bytes)
            log.info(f"[translation:orch] Translation done for {kind.value}: {len(es_bytes)} bytes")
        except Exception as e:
            log.error(f"[translation:orch] LLM translation failed for {kind.value}: {e}", exc_info=True)
            with Session(engine) as session:
                tr = session.exec(
                    select(Translation)
                    .where(Translation.application_id == application_id)
                    .where(Translation.kind == kind)
                ).first()
                if tr:
                    tr.status = TranslationStatus.FAILED
                    tr.error_message = f"Translation failed: {str(e)[:500]}"
                    tr.completed_at = datetime.utcnow()
                    session.add(tr)
                    session.commit()
            return

        # 3. Сохраняем в R2
        try:
            storage = get_storage()
            key = _r2_key(application_id, kind)
            storage.save(
                key,
                es_bytes,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            log.info(f"[translation:orch] Saved to R2: {key}")
        except Exception as e:
            log.error(f"[translation:orch] R2 save failed for {kind.value}: {e}", exc_info=True)
            with Session(engine) as session:
                tr = session.exec(
                    select(Translation)
                    .where(Translation.application_id == application_id)
                    .where(Translation.kind == kind)
                ).first()
                if tr:
                    tr.status = TranslationStatus.FAILED
                    tr.error_message = f"Storage save failed: {str(e)[:500]}"
                    tr.completed_at = datetime.utcnow()
                    session.add(tr)
                    session.commit()
            return

        # 4. Помечаем успех
        with Session(engine) as session:
            tr = session.exec(
                select(Translation)
                .where(Translation.application_id == application_id)
                .where(Translation.kind == kind)
            ).first()
            if tr:
                tr.status = TranslationStatus.DONE
                tr.storage_key = key
                tr.file_name = config["filename"]
                tr.file_size = len(es_bytes)
                tr.error_message = None
                tr.completed_at = datetime.utcnow()
                session.add(tr)
                session.commit()
                log.info(f"[translation:orch] DONE {kind.value} for app {application_id}")


async def translate_package(
    application_id: int,
    kinds: Optional[list[TranslationKind]] = None,
) -> None:
    """
    Главная функция оркестратора.

    Переводит указанные типы документов (по умолчанию — все 10).
    Записи Translation должны быть уже созданы в БД (status=PENDING) до вызова.

    Запускает параллельно с ограничением MAX_CONCURRENT,
    при ошибке одного — продолжает остальные.

    Эта функция async, но вызывается из FastAPI BackgroundTasks как обычная
    функция — поэтому в api/translations.py мы оборачиваем её в asyncio.run().
    """
    target_kinds = kinds or ALL_KINDS
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    log.info(
        f"[translation:orch] Starting package translation "
        f"for app {application_id}, kinds={[k.value for k in target_kinds]}"
    )

    # Параллельно с return_exceptions=True — одна ошибка не убивает остальные
    tasks = [_translate_one(application_id, kind, semaphore) for kind in target_kinds]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Логируем сводку
    failures = [r for r in results if isinstance(r, Exception)]
    if failures:
        log.warning(
            f"[translation:orch] Package finished with {len(failures)} unhandled exceptions "
            f"out of {len(target_kinds)} kinds (already saved as FAILED in DB)"
        )
    else:
        log.info(f"[translation:orch] Package finished for app {application_id}")


def run_translate_package(
    application_id: int,
    kinds: Optional[list[TranslationKind]] = None,
) -> None:
    """
    Sync wrapper для запуска из BackgroundTasks.
    BackgroundTasks ожидает обычную функцию, а translate_package — async.
    """
    asyncio.run(translate_package(application_id, kinds))
