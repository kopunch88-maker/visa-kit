"""
Pack 27.0 Stage A — Backend для Корзины с автоудалением через 7 дней.

Что делает:
1. Миграция БД — добавляет поле application.deleted_at (datetime nullable)
2. Расширяет модель Application полем deleted_at
3. В list_applications добавляет параметр trash: bool (по умолчанию False)
4. По умолчанию list_applications исключает удалённые (WHERE deleted_at IS NULL)
5. При trash=True — возвращает только удалённые + lazy cleanup записей старше 7 дней
6. Новые endpoints:
   - DELETE /admin/applications/{id} — soft delete (deleted_at = now)
   - POST /admin/applications/{id}/restore — восстановить (deleted_at = NULL)
   - DELETE /admin/applications/{id}/permanent — реальное удаление с R2 cleanup

При permanent delete:
- Удаляются файлы в R2 (applicant_document.storage_key/original_storage_key,
  generated_document.s3_key, uploaded_file.s3_key)
- Удаляются записи 7 связанных таблиц (CASCADE через session.exec)
- Удаляется сама application
- applicant НЕ удаляется (может быть привязан к другой заявке)

Запуск:
    cd D:\\VISA\\visa_kit\\backend
    python apply_pack27_0_stage_a.py
"""
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "app" / "models" / "application.py"
API_PATH = ROOT / "app" / "api" / "applications.py"

if not MODEL_PATH.exists() or not API_PATH.exists():
    print(f"ERROR: model or api file not found.")
    sys.exit(1)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
model_backup = MODEL_PATH.with_name(MODEL_PATH.name + f".bak_pre_pack27_0_{ts}")
api_backup = API_PATH.with_name(API_PATH.name + f".bak_pre_pack27_0_{ts}")
shutil.copy2(MODEL_PATH, model_backup)
shutil.copy2(API_PATH, api_backup)
print(f"[1/4] Бэкапы:")
print(f"      {model_backup.name}")
print(f"      {api_backup.name}")


# === 2. Миграция БД ===
print(f"\n[2/4] Миграция БД (добавление application.deleted_at)...")
import os
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print(f"      [!] DATABASE_URL не установлен — пропускаю миграцию.")
    print(f"      Установи и запусти отдельно:")
    print(f'        $env:DATABASE_URL = "postgresql://..."')
    print(f"        python -c \"from sqlalchemy import text; from app.db.session import engine; conn = engine.connect(); conn.execute(text('ALTER TABLE application ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL')); conn.execute(text('CREATE INDEX IF NOT EXISTS ix_application_deleted_at ON application(deleted_at)')); conn.commit(); conn.close(); print('migration done')\"")
else:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE application ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_application_deleted_at ON application(deleted_at)"))
            conn.commit()
        print(f"      ✓ Миграция применена: deleted_at + индекс")
    except Exception as e:
        print(f"      [!] Миграция упала: {e}")
        print(f"      Применишь отдельно — см. команду выше.")


# === 3. Patch model application.py ===
model_text = MODEL_PATH.read_text(encoding="utf-8")

old_model_block = '''    is_archived: bool = Field(default=False, index=True)
    archived_at: Optional[datetime] = Field(default=None)'''

new_model_block = '''    is_archived: bool = Field(default=False, index=True)
    archived_at: Optional[datetime] = Field(default=None)
    # Pack 27.0 — soft-delete с автоудалением через 7 дней
    deleted_at: Optional[datetime] = Field(default=None, index=True)'''

if "deleted_at: Optional[datetime]" in model_text:
    print(f"\n[3/4] application.py: deleted_at уже есть — пропуск")
else:
    if old_model_block in model_text:
        model_text = model_text.replace(old_model_block, new_model_block, 1)
        MODEL_PATH.write_text(model_text, encoding="utf-8")
        print(f"\n[3/4] application.py: добавлено поле deleted_at")
    else:
        print(f"\n[3/4] [!] WARN: блок is_archived в модели не найден точно")
        # Гибкий fallback
        if "archived_at: Optional[datetime]" in model_text:
            model_text = model_text.replace(
                "archived_at: Optional[datetime] = Field(default=None)",
                "archived_at: Optional[datetime] = Field(default=None)\n"
                "    # Pack 27.0 — soft-delete с автоудалением через 7 дней\n"
                "    deleted_at: Optional[datetime] = Field(default=None, index=True)",
                1,
            )
            MODEL_PATH.write_text(model_text, encoding="utf-8")
            print(f"      [fallback] поле добавлено")


# === 4. Patch api applications.py ===
api_text = API_PATH.read_text(encoding="utf-8")

# 4a. Изменить list_applications — добавить параметр trash + lazy cleanup
old_list = '''@router.get("")
def list_applications(
    session: Session = Depends(get_session),
    archived: bool = Query(False, description="Pack 10: показать архивные (по умолчанию false — только активные)"),'''

new_list = '''@router.get("")
def list_applications(
    session: Session = Depends(get_session),
    archived: bool = Query(False, description="Pack 10: показать архивные (по умолчанию false — только активные)"),
    trash: bool = Query(False, description="Pack 27.0: показать удалённые (корзина). При true — выполняется lazy cleanup записей старше 7 дней."),'''

if old_list in api_text:
    api_text = api_text.replace(old_list, new_list, 1)
    print(f"\n[4/4a] list_applications: параметр trash добавлен")
else:
    # Гибкий fallback по началу сигнатуры
    import re
    pattern = re.compile(
        r'@router\.get\(""\)\s*\ndef list_applications\(\s*\n\s*session: Session = Depends\(get_session\),\s*\n\s*archived: bool = Query\(False[^)]*\),',
        re.MULTILINE
    )
    m = pattern.search(api_text)
    if m:
        new_block = m.group(0) + '\n    trash: bool = Query(False, description="Pack 27.0: показать удалённые (корзина). При true — lazy cleanup старше 7 дней."),'
        api_text = api_text.replace(m.group(0), new_block, 1)
        print(f"\n[4/4a] list_applications: параметр trash добавлен (fallback)")
    else:
        print(f"\n[4/4a] [!] WARN: list_applications сигнатура не найдена")

# 4b. Изменить query внутри list_applications
old_query = "query = select(Application).where(Application.is_archived == archived)"

new_query = '''# Pack 27.0 — Корзина. Если trash=True, делаем lazy cleanup и возвращаем только удалённые.
    if trash:
        # Lazy cleanup: удаляем permanently записи в корзине старше 7 дней
        cutoff = datetime.utcnow() - timedelta(days=7)
        old_trashed = session.exec(
            select(Application).where(
                Application.deleted_at.is_not(None),
                Application.deleted_at < cutoff,
            )
        ).all()
        for old_app in old_trashed:
            _permanent_delete_application(session, old_app)
        if old_trashed:
            session.commit()

        query = select(Application).where(Application.deleted_at.is_not(None))
    else:
        query = select(Application).where(
            Application.is_archived == archived,
            Application.deleted_at.is_(None),
        )'''

if old_query in api_text:
    api_text = api_text.replace(old_query, new_query, 1)
    print(f"[4/4b] list_applications: query обновлён (lazy cleanup + filter)")
else:
    print(f"[4/4b] [!] WARN: query Application.is_archived == archived не найден")

# 4c. Импорт timedelta — нужен для cleanup
if "from datetime import" in api_text and "timedelta" not in api_text.split("\n")[0:30]:
    api_text = api_text.replace(
        "from datetime import date",
        "from datetime import date, datetime, timedelta",
        1,
    )
    if "from datetime import date, datetime, timedelta" not in api_text:
        # Может быть уже другой формат
        pass

# Простой и надёжный путь — добавить полную строку импорта если её нет
if "from datetime import" not in api_text[:2000]:
    api_text = "from datetime import datetime, timedelta\n" + api_text
elif "timedelta" not in api_text[:2000]:
    # Найти существующий datetime import и добавить timedelta
    import re
    m = re.search(r'from datetime import ([^\n]+)', api_text[:2000])
    if m:
        existing = m.group(1)
        if "timedelta" not in existing:
            api_text = api_text.replace(
                f"from datetime import {existing}",
                f"from datetime import {existing}, timedelta",
                1,
            )

# 4d. Добавить новые endpoints + helper в конец файла
endpoint_addition = '''


# ============================================================================
# Pack 27.0 — Корзина (soft-delete с автоудалением через 7 дней)
# ============================================================================

def _permanent_delete_application(session: Session, app: Application) -> None:
    """
    Pack 27.0 — Permanent delete заявки.

    Удаляет:
    1. Файлы в R2: applicant_document.storage_key + original_storage_key,
       generated_document.s3_key, uploaded_file.s3_key
    2. Записи 7 связанных таблиц
    3. Саму application

    Applicant НЕ удаляем — может быть привязан к другой заявке.
    """
    from app.services.storage import get_storage
    storage = get_storage()

    # 1. Собрать все ключи R2 для удаления
    keys_to_delete: list[str] = []

    # applicant_document — storage_key (JPEG для OCR) + original_storage_key (оригинал PDF)
    from sqlalchemy import text as sql_text
    rows = session.connection().execute(
        sql_text("SELECT storage_key, original_storage_key FROM applicant_document WHERE application_id = :aid"),
        {"aid": app.id}
    ).fetchall()
    for sk, osk in rows:
        if sk: keys_to_delete.append(sk)
        if osk: keys_to_delete.append(osk)

    rows = session.connection().execute(
        sql_text("SELECT s3_key FROM generated_document WHERE application_id = :aid"),
        {"aid": app.id}
    ).fetchall()
    for (sk,) in rows:
        if sk: keys_to_delete.append(sk)

    rows = session.connection().execute(
        sql_text("SELECT s3_key FROM uploaded_file WHERE application_id = :aid"),
        {"aid": app.id}
    ).fetchall()
    for (sk,) in rows:
        if sk: keys_to_delete.append(sk)

    # 2. Удалить файлы из R2 (best-effort, не падаем если уже нет)
    deleted_count = 0
    failed_count = 0
    for key in keys_to_delete:
        try:
            # Пробуем разные API в зависимости от storage backend
            if hasattr(storage, "delete"):
                storage.delete(key)
            elif hasattr(storage, "delete_object"):
                storage.delete_object(key)
            elif hasattr(storage, "client") and hasattr(storage, "bucket_name"):
                # R2Storage: прямой S3 API
                storage.client.delete_object(Bucket=storage.bucket_name, Key=key)
            else:
                raise AttributeError(f"Unknown storage delete API on {type(storage).__name__}")
            deleted_count += 1
        except Exception as e:
            failed_count += 1
            import logging
            logging.getLogger(__name__).warning(
                f"Pack 27.0: failed to delete R2 key {key}: {e}"
            )

    import logging
    logging.getLogger(__name__).info(
        f"Pack 27.0: permanent delete app {app.id} — R2 deleted {deleted_count}/{len(keys_to_delete)} (failed {failed_count})"
    )

    # 3. Удалить записи связанных таблиц
    related_tables = [
        "applicant_document",
        "generated_document",
        "uploaded_file",
        "family_member",
        "previous_residence",
        "timeline_event",
        "translation",
    ]
    for tbl in related_tables:
        session.connection().execute(
            sql_text(f"DELETE FROM {tbl} WHERE application_id = :aid"),
            {"aid": app.id}
        )

    # 4. Удалить саму application
    session.delete(app)


@router.delete("/{app_id}", status_code=200)
def soft_delete_application(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """
    Pack 27.0 — Soft-delete заявки (в корзину).

    Доступно из ЛЮБОГО статуса (включая DRAFT, ASSIGNED, DRAFTS_GENERATED).
    Если заявка в архиве — выводим из архива и удаляем.

    Через 7 дней запись будет permanent удалена (lazy cleanup при открытии корзины).
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    if app.deleted_at is not None:
        raise HTTPException(409, "Application is already in trash")

    # Если архивная — выводим из архива при удалении
    was_archived = app.is_archived
    if was_archived:
        app.is_archived = False
        app.archived_at = None

    app.deleted_at = datetime.utcnow()
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_deleted",
        f"Заявка перемещена в корзину (статус: {app.status}{'; была в архиве' if was_archived else ''})",
        {"status_at_delete": str(app.status), "was_archived": was_archived},
    )
    session.commit()
    session.refresh(app)
    return {"id": app.id, "deleted_at": app.deleted_at.isoformat()}


@router.post("/{app_id}/restore", status_code=200)
def restore_application(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """
    Pack 27.0 — Восстановить заявку из корзины.
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    if app.deleted_at is None:
        raise HTTPException(409, "Application is not in trash")

    app.deleted_at = None
    session.add(app)
    _log_event(
        session, app.id, "manager", user_id, "application_restored",
        "Заявка восстановлена из корзины",
    )
    session.commit()
    session.refresh(app)
    return _enrich(app, session)


@router.delete("/{app_id}/permanent", status_code=200)
def permanent_delete_application(
    app_id: int,
    session: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
) -> dict:
    """
    Pack 27.0 — Permanent delete заявки.

    Удаляет:
    - Файлы в R2 (applicant_document, generated_document, uploaded_file)
    - Все связанные записи (7 таблиц)
    - Саму application

    Applicant НЕ удаляется (может быть привязан к другой заявке).

    БЕЗ ВОЗВРАТА. Использовать только если точно нужно.
    """
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    # Сохраняем reference для лога перед удалением
    ref = app.reference

    _log_event(
        session, app.id, "manager", user_id, "application_permanently_deleted",
        f"Заявка удалена навсегда (reference: {ref})",
        {"reference": ref, "status": str(app.status)},
    )

    _permanent_delete_application(session, app)
    session.commit()

    return {"deleted": True, "reference": ref}
'''

if "_permanent_delete_application" in api_text:
    print(f"[4/4d] applications.py: permanent endpoints уже есть — пропуск")
else:
    api_text = api_text.rstrip() + endpoint_addition + "\n"
    print(f"[4/4d] applications.py: добавлены 3 endpoints + helper")

API_PATH.write_text(api_text, encoding="utf-8")


# === 5. Финальная проверка синтаксиса ===
errors = []
for p in (MODEL_PATH, API_PATH):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append(f"{p.name}: {e}")

if errors:
    print(f"\n[FAIL] синтаксические ошибки:")
    for e in errors:
        print(f"  - {e}")
    print(f"\nОткат:")
    print(f"  Copy-Item -Force '{model_backup}' '{MODEL_PATH}'")
    print(f"  Copy-Item -Force '{api_backup}' '{API_PATH}'")
    sys.exit(1)

print(f"\n[OK] оба файла валидны")
print(f"\n=== Pack 27.0 Stage A применён ===")
print()
print("Дальше:")
print("  cd D:\\VISA\\visa_kit")
print("  git add backend/app/models/application.py backend/app/api/applications.py")
print("  git status")
print("  git commit -m 'Pack 27.0 Stage A: trash with 7d auto-cleanup (backend)'")
print("  git push")
print()
print("После Railway-деплоя — Stage B (frontend: кнопка Удалить + страница Корзина)")
print()
print(f"Откат:")
print(f"  Copy-Item -Force '{model_backup}' '{MODEL_PATH}'")
print(f"  Copy-Item -Force '{api_backup}' '{API_PATH}'")
print(f"  # Откат миграции БД (если нужно):")
print(f"  # python -c \"from sqlalchemy import text; from app.db.session import engine; conn = engine.connect(); conn.execute(text('ALTER TABLE application DROP COLUMN deleted_at')); conn.commit(); conn.close()\"")
