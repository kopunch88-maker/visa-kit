# VISA KIT — Project State

**Last updated:** Session 13 end (May 1, 2026)
**Status:** Pack 13.x complete. Ready to start Pack 14 (auto-validation of generated documents).

---

## КОНТЕКСТ БИЗНЕСА

- Spain Digital Nomad visa agency
- ~50 заявок/месяц
- 4 менеджера + 1 владелец (Костя)
- Локально: Windows, Python 3.14 (.venv), Node 24
- Production: Python 3.12 (Docker), PostgreSQL, Cloudflare R2

---

## INFRASTRUCTURE

| Сервис | Назначение | Стоимость |
|---|---|---|
| **Vercel Hobby** | Frontend (Next.js 16.2.4) | Free |
| **Railway** | Backend (FastAPI Docker) + PostgreSQL | $5-10/мес |
| **Cloudflare R2** | File storage (bucket: `visa-kit-storage`) | Free до 10GB |
| **GitHub** | Private monorepo | Free |
| **OpenRouter** | LLM API (Claude Sonnet 4.6) для OCR | ~$10/мес |

**URLs:**
- Frontend: https://visa-kit.vercel.app
- Backend: https://visa-kit-production.up.railway.app
- Admin: https://visa-kit.vercel.app/admin/login
- Cloudflare R2: account_id `93b044dabe95d0bf265540653ee681d2` (публичный)

---

## ЧТО УЖЕ В PRODUCTION (накопительно по всем сессиям)

### Базовая функциональность
- ✅ Управление заявками (CRUD, статусы, архив)
- ✅ Справочники: компании (10), должности (10+), представители (2), испанские адреса (3)
- ✅ Двухпанельный layout (список слева + детали справа)
- ✅ Bilingual ФИО (русский + латиница) во всём UI
- ✅ Status machine с правилами переходов

### Генерация документов
- ✅ DOCX: договор, 3 акта, 3 счёта, письмо работодателя, CV, выписка
- ✅ PDF испанские формы: MI-T, Designación, Compromiso, Declaración
- ✅ ZIP package для скачивания всех документов

### Финансы и валидация
- ✅ Bank statement generator с курсами ЦБ РФ
- ✅ Чек-лист бизнес-правил (договор > 90 дней, зарплата выше порога, и т.д.)
- ✅ Recommendation engine (auto-suggest assignment)

### Production deployment
- ✅ Vercel + Railway + R2 + OpenRouter
- ✅ JWT + bcrypt admin auth
- ✅ Magic-link для клиентов

### Pack 13.x — Клиентский кабинет с OCR (текущая сессия)

**Pack 13.0a/b** — инфраструктура:
- LLM service abstraction (`backend/app/services/llm/`)
- Модель ApplicantDocument (renamed enums чтобы не конфликтовать с DocumentType)
- Storage endpoints
- Frontend Step 0 «Документы» в ClientWizard.tsx (первый шаг, опциональный)
- 5 слотов документов с drag-drop, capture камерой

**Pack 13.1** — реальный OCR:
- Claude Sonnet 4.6 через OpenRouter
- 4 промпта (английские инструкции, native-language values)
- HEIC → JPEG конвертация (pillow-heif)
- Auto-resize больших изображений
- Endpoint POST /documents/{id}/recognize
- Endpoint POST /documents/apply-to-applicant

**Pack 13.1.1** — conflict resolution UI:
- 3 категории: auto_fill, conflicts, same
- Radio buttons для конфликтов (default: оставить ручной ввод)
- Education actions: skip / replace / add (default: skip)
- Endpoint POST /documents/preview-apply
- Smart matching: case-insensitive имена, digits-only номера

**Pack 13.1.2** — ГОСТ транслитерация:
- Файл `backend/app/services/transliteration.py` с таблицей ГОСТ 52535.1-2006
- Backend автоматически генерирует *_latin поля при apply OCR данных
- Решает: «Иван» → «IVAN» руками, потом OCR заменил на «Константин» — latin тоже обновится в Konstantin

**Pack 13.1.3** — поддержка PDF:
- Конвертация PDF → JPEG на клиенте через PDF.js (lazy load с unpkg/jsdelivr/cdnjs fallback)
- Версия PDF.js: 3.11.174 (последняя UMD-version, 5.x уже только ES modules)
- Многостраничный PDF — клиент выбирает нужную страницу через модалку
- Backend хранит ОБА файла: JPEG (для OCR + превью) + оригинальный PDF (для финальной отправки)
- Поля в applicant_document: `original_storage_key`, `original_file_name`, `original_file_size`, `original_content_type`

**Pack 13.2** — Админский UI документов клиента:
- Новый роутер `backend/app/api/client_documents_admin.py`
- Endpoints: GET /admin/applications/{id}/client-documents, POST .../recognize
- Frontend: компонент `AdminClientDocuments.tsx` встраивается в `ApplicationDetail.tsx`
- Менеджер видит миниатюры, статус OCR, распознанные поля (collapsed), может скачать оригинал PDF, может перезапустить OCR

**Sidebar fix** — приоритет имени:
- В ApplicationsList.tsx: applicant_name_native → internal_notes → "Заявка #N"
- Раньше показывался internal_notes даже когда есть ФИО клиента
- Добавлен subtitle с латинским ФИО под русским

**Миграция справочников из dev.db в production:**
- Скрипт `migrate_catalogs_to_prod.py` (одноразовый, удалён после использования)
- Перенесены: 9 компаний, 9 должностей, 1 представитель (ANASTASIIA KORENEVA), 2 адреса
- Решение проблемы SQLite int 0/1 → PostgreSQL bool

---

## RAILWAY ENV VARIABLES (13 шт., все настроены)

| Имя | Назначение |
|---|---|
| DATABASE_URL | PostgreSQL connection (internal) |
| FRONTEND_URL | https://visa-kit.vercel.app (для CORS) |
| JWT_SECRET | для admin auth |
| SECRET_KEY | общий секрет |
| STORAGE_BACKEND | `r2` |
| R2_ACCOUNT_ID | hex 32 chars (НЕ cfat_!) |
| R2_ACCESS_KEY_ID | API token access key |
| R2_SECRET_ACCESS_KEY | API token secret |
| R2_BUCKET_NAME | `visa-kit-storage` |
| LLM_PROVIDER | `openrouter` |
| OPENROUTER_API_KEY | sk-or-v1-... |
| OPENROUTER_MODEL | `anthropic/claude-sonnet-4.6` |
| LLM_VISION_MODEL | `anthropic/claude-sonnet-4.6` |

⚠️ **R2_ACCOUNT_ID** — это hex строка из Cloudflare Account details, НЕ API Token Identifier (cfat_...).

---

## DATABASE_PUBLIC_URL

```
postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway
```

⚠️ Может ротироваться — брать актуальное из Railway → Postgres → Variables → `DATABASE_PUBLIC_URL`

---

## PROJECT FILE STRUCTURE

```
D:\VISA\visa_kit\
├── backend\
│   ├── app\
│   │   ├── api\
│   │   │   ├── applicants.py
│   │   │   ├── applications.py            ← admin app endpoints (НЕ admin.py!)
│   │   │   ├── auth.py
│   │   │   ├── bank_transactions.py
│   │   │   ├── client_portal.py           ← Pack 13.1.1/.2/.3 — client OCR
│   │   │   ├── client_documents_admin.py  ← Pack 13.2 — admin UI for docs
│   │   │   ├── companies.py
│   │   │   ├── dependencies.py            ← require_manager отсюда
│   │   │   ├── positions.py
│   │   │   ├── render_endpoints.py
│   │   │   ├── representatives.py
│   │   │   └── spain_addresses.py
│   │   ├── models\
│   │   │   ├── applicant_document.py      ← Pack 13.1.3 (4 original_* fields)
│   │   │   └── ...
│   │   ├── services\
│   │   │   ├── llm\                       ← Pack 13.0a (5 файлов)
│   │   │   ├── ocr\                       ← Pack 13.1 (3 файла)
│   │   │   ├── storage\                   ← (5 файлов: base/factory/local/r2/__init__)
│   │   │   ├── transliteration.py         ← Pack 13.1.2 GOST
│   │   │   └── ...
│   │   ├── main.py                        ← FastAPI app + migrations
│   │   └── ...
│   ├── requirements.txt                   ← contains pillow-heif==0.18.0
│   └── dev.db                             ← локальная SQLite
├── frontend\
│   ├── components\
│   │   ├── admin\
│   │   │   ├── ApplicationDetail.tsx      ← включает AdminClientDocuments
│   │   │   ├── ApplicationsList.tsx       ← FIXED sidebar priority
│   │   │   ├── AdminClientDocuments.tsx   ← Pack 13.2
│   │   │   ├── DocumentsGrid.tsx          ← генерируемые DOCX/PDF
│   │   │   └── ...
│   │   └── wizard\
│   │       ├── ClientWizard.tsx           ← Step 0 first
│   │       ├── StepDocuments.tsx          ← Pack 13.1.1 conflict UI + 13.1.3 PDF
│   │       ├── StepPersonalInfo.tsx
│   │       ├── PdfPageSelector.tsx        ← Pack 13.1.3
│   │       └── ...
│   └── lib\
│       ├── api.ts                         ← все Pack 13 функции
│       └── pdfConverter.ts                ← Pack 13.1.3 + 3-CDN fallback
└── PROJECT_STATE.md                       ← этот файл
```

---

## ВАЖНЫЕ УРОКИ ИЗ ПРЕДЫДУЩИХ СЕССИЙ

### .gitignore / .dockerignore
- `**/storage/` ловит ВСЕ папки `storage` где угодно — включая `services/storage/`
- Правильно: `/storage/` (anchor к корню) и `/backend/storage/`

### R2 Account ID
- Cloudflare даёт **2 разных идентификатора**:
  - **Account ID** — hex 32 символа (для R2 endpoint URL)
  - **API Token Identifier** — начинается с `cfat_...` (для авторизации)
- Для `R2_ACCOUNT_ID` env нужен **первый**

### Renamed enums
- `applicant_document.py` использует `ApplicantDocumentType` / `ApplicantDocumentStatus`
- Конфликт с `_supporting.py` (DocumentType/DocumentStatus для GeneratedDocument)

### PDF.js
- Версия 3.11.174 — последняя UMD (через `<script>` тег). 5.x только ES modules
- 3-CDN fallback: unpkg → jsdelivr → cdnjs

### SQLite → PostgreSQL миграция
- SQLite хранит boolean как INTEGER (0/1)
- PostgreSQL требует настоящий BOOLEAN (true/false)
- Нужна явная конвертация при переносе данных

### PowerShell quirks
- `python -c "..."` с вложенными кавычками → проблемы. Использовать here-string `@"..."@`
- `$env:DATABASE_URL` может протекать в дочерние процессы — обнулять `$env:DATABASE_URL=$null`
- НЕ устанавливать в качестве пароля плейсхолдер `ПАРОЛЬ` — копировать значение целиком из Railway

### Railway Postgres
- Усыпляется при неактивности — клик на карточку Postgres в Railway будит его
- Нет встроенной вкладки Query — миграции через Python скрипт с DATABASE_PUBLIC_URL

### LF/CRLF warnings
- Windows + Git постоянно ругается — игнорировать, Git автоматически конвертирует

---

## RUN COMMANDS (LOCAL DEV)

```powershell
# Backend
cd D:\VISA\visa_kit\backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Frontend (другое окно)
cd D:\VISA\visa_kit\frontend
npm run dev

# Login: http://localhost:3000/admin/login
# Client portal: http://localhost:3000/client/<token>
```

---

## DEPLOY WORKFLOW

```powershell
cd D:\VISA\visa_kit
git add .
git commit -m "..."
git push
```

Vercel + Railway auto-redeploy за 2-5 минут.

---

## РОДМАП — ЧТО ОСТАЛОСЬ ИЗ СТАРОГО ПЛАНА (5 паков)

В порядке приоритета по окупаемости:

### 🚀 Pack 14 — Авто-проверка пакета документов (СЛЕДУЮЩИЙ)

ИИ читает все 10 сгенерированных DOCX + 4 PDF и проверяет согласованность:
- Даты в договоре совпадают с датами в актах?
- Суммы в счетах = суммам в актах?
- ФИО склоняется правильно (Им., Род., Дат., Вин., Тв., Пред.)?
- Номер паспорта в одном формате во всех документах?
- Орфография имён, склонения, формат дат?

**Окупаемость:** одна избегнутая ошибка = одобрение визы клиенту. Менеджер не пропустит ляп.
**Стоимость:** ~$0.10 за пакет (один LLM запрос).
**Сложность:** 3-4 дня. Parser DOCX/PDF → промпт для LLM → результат с пометкой проблем.

### Pack 15 — Перевод-черновик на испанский (быстрый, ~1-2 дня)

Claude переводит DOCX на испанский на уровне присяжного переводчика. **Черновик** — финальную проверку и подпись делает живой переводчик (юридическое требование UGE).
**Окупаемость:** ускоряет pipeline с 3-5 дней до 1 дня на этапе «у переводчика».

### Pack 16 — Авто-распределение по компаниям (~2 дня)

Балансировка нагрузки между 10 компаниями. Учёт географии и пересечений.
**Окупаемость:** убирает один шаг ручного распределения.

### Pack 17 — Email-агент (~5-7 дней)

Авто-ответы клиенту на типовые вопросы. Notify-уведомления. Модерация менеджером.
**Окупаемость:** освобождает 2-3 часа менеджера в день.
**Условие:** делать когда поток заявок вырастет до 100+/мес.

### Pack 18 — Мониторинг статусов в UGE (хрупкое, ~5-10 дней)

Browser-агент через Computer Use открывает портал UGE. **Только чтение**, не подача.
**Риски:** UGE может ломать UI, блокировать IP.
**Условие:** делать когда станет реально критично.

---

## ЧТО НЕ АВТОМАТИЗИРУЕМ (намеренно)

- **Итоговое решение менеджера перед подачей** — юридическая ответственность лежит на агентстве
- **Личная коммуникация в сложных кейсах** (развод с детьми, отказы в прошлом) — ИИ помогает, но решение и эмпатия за человеком
- **Оценка рисков отказа** — требует юридической экспертизы
- **Подача документов в UGE** — UGE не имеет API, серая зона
- **Подписание документов (ЭП)** — юридическое действие

---

## ЦЕЛИ АВТОМАТИЗАЦИИ

После всех Pack 14-18:
- Время менеджера на одну заявку: с 4-6 часов → до 30 минут
- Один менеджер ведёт: с 50 → до 200+ заявок/мес
- Возможные сценарии:
  - Рост выручки в 4-6 раз без увеличения штата
  - ИЛИ снижение цены клиенту в 2-3 раза при сохранении маржи
  - ИЛИ комбинация (умеренный рост штата + снижение цены + рост маржи)

---

## DECISION LOG (последние сессии)

- [DECISION] Промпты на английском, output в исходном языке (Cyrillic stays Cyrillic, Latin stays Latin)
- [DECISION] Soft warning policy: OCR fail → файл сохранён, менеджер проверит вручную
- [DECISION] Promo screen «Что мы извлекли» обязательный после OCR
- [DECISION] Conflict UI: только реальные конфликты, default «оставить ручной ввод»
- [DECISION] Education conflict: 3 опции (skip/add/replace), default skip
- [DECISION] Транслитерация на backend через ГОСТ 52535.1-2006
- [DECISION] PDF: гибрид (конвертация на клиенте) + клиент выбирает страницу + хранить оригинал PDF + DPI 200
- [DECISION] PDF.js: версия 3.11.174 UMD + 3-CDN fallback (unpkg → jsdelivr → cdnjs)
- [DECISION] Admin UI документов: базовый набор (просмотр, скачивание, перезапуск OCR), без upload/delete пока
- [DECISION] Sidebar list priority: applicant_name_native > internal_notes > "Заявка #N"
- [DECISION] PROJECT_STATE.md: НЕ хранить значения секретов
- [DECISION] Stack final: Vercel + Railway + R2 + OpenRouter
- [DECISION] Следующий пак — Pack 14 (авто-проверка пакета)

---

## USER PREFERENCES

- Язык общения: **русский**, casual technical tone («ок», «идём дальше»)
- Production-first deployment philosophy
- Команда: 4 менеджера + Костя (владелец)
- Reaction to manual diff edits: **«вообще ничего не понял»** → **готовые файлы целиком**
- Reaction to готовым файлам: «идём дальше» → значит работает
- Format предпочтений: концентрированные ответы, мало formatting, прямо к делу
- Ошибки и баги: показывать логи Railway (Build Logs vs Deploy Logs vs HTTP Logs)

---

## SESSION HISTORY

- Sessions 1-9: базовая разработка (модели, генерация, админка)
- Session 10: ZIP packaging
- Session 11: production deploy (Vercel + Railway + R2)
- Session 12: Pack 13.0/13.1/13.1.1 — клиентский кабинет с OCR
- **Session 13** (текущая):
  - Pack 13.1.2 — ГОСТ-транслит
  - Pack 13.1.3 — PDF поддержка через PDF.js на клиенте + хранение оригинала
  - Pack 13.2 — админский UI документов клиента
  - Sidebar fix (приоритет имени)
  - Миграция справочников (9 компаний + 9 позиций + 1 представитель + 2 адреса) из dev.db в production

---

**END OF STATE**
