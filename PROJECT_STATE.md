# VISA KIT — Project State

**Last updated:** Session 12 end (Apr 30, 2026)
**Status:** Pack 13.1.1 in production. Pack 13.1.2 ready for push (transliteration fix).

---

## КОНТЕКСТ БИЗНЕСА

- Spain Digital Nomad visa agency
- ~50 заявок/месяц
- 4 менеджера + 1 владелец
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

## CURRENT FEATURES

### Pack 1-9 (стабильные, в production)
- Управление заявками (CRUD, статусы, архив)
- Справочники: компании, должности, представители, испанские адреса
- Генерация PDF/DOCX документов из шаблонов (compromiso, declaracion, contract, и т.д.)
- Bank statement generator (CBR курсы)
- Recommendation engine (auto-suggest assignment)
- Admin auth (JWT + bcrypt)
- Status machine с правилами переходов

### Pack 10-11 (стабильные, в production)
- ZIP packaging для скачивания всех документов
- Production deployment на Railway + R2
- Admin user management

### Pack 13.0a (в production)
- LLM service abstraction (`backend/app/services/llm/`):
  - `base.py` — интерфейс
  - `openrouter.py` — клиент OpenRouter
  - `anthropic_direct.py` — клиент Anthropic API (резервный)
  - `factory.py` — выбор по env `LLM_PROVIDER`
- Модель `ApplicantDocument` (renamed enums: `ApplicantDocumentType`, `ApplicantDocumentStatus` чтобы не конфликтовать с `DocumentType`/`DocumentStatus` из `_supporting.py`)
- Endpoints для документов: `GET/POST/DELETE /api/client/{token}/documents/...`

### Pack 13.0b (в production)
- Frontend UI загрузки документов
- Шаг 0 «Документы» в `ClientWizard.tsx` (первый, опциональный)
- 5 слотов: passport_internal_main, passport_internal_address, passport_foreign, diploma_main, diploma_apostille
- Drag-drop, click upload, capture="environment" для камеры на mobile
- Thumbnails, replace/delete

### Pack 13.1 (в production)
- Реальный OCR через Claude Sonnet 4.6 (OpenRouter)
- 4 промпта (английские инструкции, native-language values):
  - RUSSIAN_PASSPORT_MAIN_PROMPT
  - RUSSIAN_PASSPORT_ADDRESS_PROMPT
  - FOREIGN_PASSPORT_PROMPT
  - DIPLOMA_PROMPT
- HEIC → JPEG конвертация (pillow-heif)
- Auto-resize больших изображений
- JSON parsing с обработкой markdown fences
- Endpoint `POST /documents/{id}/recognize`
- Endpoint `POST /documents/apply-to-applicant`

### Pack 13.1.1 (в production)
- Conflict resolution UI:
  - 3 категории: auto_fill, conflicts, same
  - Radio buttons для конфликтов (default: оставить ручной ввод)
  - Education actions: skip / replace / add (default: skip)
- Endpoint `POST /documents/preview-apply` — план применения
- Endpoint `POST /documents/apply-to-applicant` принимает body `{overrides, education_action}`
- Smart matching: case-insensitive для имён/адресов, digits-only для номеров

### Pack 13.1.2 (READY TO PUSH — НЕ В PRODUCTION)
- ГОСТ 52535.1-2006 транслитерация на сервере
- Файлы готовы в `/mnt/user-data/outputs/`:
  - `transliteration.py` (новый)
  - `client_portal.py` (заменить существующий)
- Логика: при apply OCR данных, если `*_native` поле обновляется и `*_latin` НЕ пришло из загранпаспорта — генерируем latin через ГОСТ
- Решает баг: «Иван» → «IVAN» руками, потом OCR заменил на «Константин», но latin остался «IVAN»

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

⚠️ **ВАЖНО:** R2_ACCOUNT_ID — это **hex строка из Cloudflare Account details**, НЕ API Token Identifier (cfat_...). Эта ошибка была причиной краша production в session 12.

---

## DATABASE_PUBLIC_URL (для create_admin.py)

```
postgresql://postgres:<password>@switchyard.proxy.rlwy.net:34408/railway
```

⚠️ Может ротироваться — брать актуальное из Railway → Postgres → Variables → `DATABASE_PUBLIC_URL`

---

## PROJECT FILE STRUCTURE

```
D:\VISA\visa_kit\
├── backend\
│   ├── app\
│   │   ├── api\
│   │   │   ├── admin.py                  ← admin endpoints
│   │   │   ├── auth.py                   ← JWT login
│   │   │   ├── client_portal.py          ← клиентский кабинет (Pack 13.1.1, ждёт 13.1.2)
│   │   │   └── ...
│   │   ├── models\
│   │   │   ├── applicant.py              ← основная модель клиента
│   │   │   ├── applicant_document.py     ← Pack 13.0a (renamed enums!)
│   │   │   ├── application.py
│   │   │   └── _supporting.py            ← DocumentType/Status (для GeneratedDocument)
│   │   ├── services\
│   │   │   ├── llm\                      ← Pack 13.0a (5 файлов)
│   │   │   ├── ocr\                      ← Pack 13.1 (3 файла)
│   │   │   ├── storage\                  ← (5 файлов: base, factory, local, r2, __init__)
│   │   │   ├── transliteration.py        ← Pack 13.1.2 (ЕЩЁ НЕ ДОБАВЛЕН локально!)
│   │   │   ├── rendering.py
│   │   │   ├── recommendation.py
│   │   │   ├── status_machine.py
│   │   │   ├── cbr_client.py
│   │   │   └── bank_statement_generator.py
│   │   ├── db\
│   │   ├── config.py
│   │   ├── main.py                       ← FastAPI app + migrations
│   │   └── migrations.py
│   ├── requirements.txt                  ← должен содержать pillow-heif==0.18.0
│   └── dev.db                            ← SQLite для локальной разработки
├── frontend\
│   ├── components\
│   │   ├── wizard\
│   │   │   ├── ClientWizard.tsx          ← Pack 13.1 (Step 0 first, async handleDocumentsContinue)
│   │   │   ├── StepDocuments.tsx         ← Pack 13.1.1 (с conflict resolution UI)
│   │   │   ├── StepPersonalInfo.tsx      ← имеет lastAutoFill ref + GOST translit map
│   │   │   ├── StepPassport.tsx
│   │   │   ├── StepAddress.tsx
│   │   │   ├── StepEducation.tsx
│   │   │   └── StepWorkHistory.tsx
│   │   └── admin\
│   ├── lib\
│   │   └── api.ts                        ← Pack 13.1.1 (preview/apply types)
│   └── ...
├── templates\
│   ├── pdf\
│   └── docx\
├── Dockerfile
├── .dockerignore                         ← /storage/ и /backend/storage/ (НЕ **/storage/!)
├── .gitignore                            ← /storage/ и /backend/storage/ (НЕ storage/!)
└── PROJECT_STATE.md                      ← этот файл
```

---

## ВАЖНЫЕ УРОКИ ИЗ ПРЕДЫДУЩИХ СЕССИЙ

### .gitignore / .dockerignore
- `**/storage/` ловит ВСЕ папки `storage` где угодно — включая `services/storage/`
- Правильно: `/storage/` (anchor к корню) и `/backend/storage/`
- Это случилось в session 12 — production упал, починилось через правку обоих ignore-файлов

### R2 Account ID
- Cloudflare даёт **2 разных идентификатора**:
  - **Account ID** — hex 32 символа (для R2 endpoint URL)
  - **API Token Identifier** — начинается с `cfat_...` (для авторизации API tokens)
- Для `R2_ACCOUNT_ID` env нужен **первый**, иначе boto3 падает на `create_endpoint`

### Renamed enums
- `applicant_document.py` использует `ApplicantDocumentType` / `ApplicantDocumentStatus`
- Если попробовать назвать их просто `DocumentType` / `DocumentStatus` — конфликт с `_supporting.py`
- При импорте всегда писать полное имя

### Docker layer cache на Railway
- Иногда Railway показывает `cached` для COPY слоя — это нормально если файлы не менялись
- Если папка не попала в коммит, добавление её через `git add -f` решает проблему
- Не надо мудрить с CACHEBUST — обычно достаточно правильно настроить ignore-файлы

### LF/CRLF warnings
- Windows + Git постоянно ругается на line endings
- Это **не ошибка**, можно игнорировать
- Git автоматически конвертирует при checkout

### PowerShell quirks
- `python -c "..."` с вложенными кавычками → проблемы. Использовать here-string `@"..."@ | Out-File`
- `$env:DATABASE_URL` может протекать в дочерние процессы — обнулять `$env:DATABASE_URL=$null`
- Перед командами Python убедиться что `.venv` активирован

### Pack 13.1.2 (transliteration) bug context
- В `StepPersonalInfo.tsx` есть `useEffect` который автотранслитерирует `*_native` → `*_latin`
- Логика «не перезаписывать если клиент редактировал» через `lastAutoFill` ref
- Когда OCR применяет данные, `lastAutoFill` остаётся со старым значением
- Решение: backend сам генерирует latin через ГОСТ при apply

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

## NEXT STEPS — что делать когда вернёшься

### Шаг 1. Применить Pack 13.1.2 (готов, не задеплоен)

Скачать из `/mnt/user-data/outputs/`:

| Файл | Куда |
|---|---|
| `transliteration.py` (новый) | `D:\VISA\visa_kit\backend\app\services\transliteration.py` |
| `client_portal.py` (заменить) | `D:\VISA\visa_kit\backend\app\api\client_portal.py` |

```powershell
cd D:\VISA\visa_kit
git add .
git commit -m "Pack 13.1.2: GOST-based auto-transliteration for *_latin fields on OCR apply"
git push
```

### Шаг 2. Тест транслитерации

Проверить сценарий:
1. Шаг 1 → написать «Иван» → latin auto = «IVAN»
2. Шаг 0 → загрузить паспорт РФ с именем «Константин»
3. «Распознать всё» → Review
4. В конфликте `first_name_native`: выбрать «Из документа»
5. Применить → проверить Шаг 1: должно быть «Константин» / «Konstantin»

### Шаг 3. Дальше — Pack 13.2 (планируется)

**Backend:**
- Интеграция с ФНС API для получения ИНН по паспортным данным
- Endpoint `POST /api/client/{token}/lookup-inn` — после OCR паспорта РФ
- Кеширование результата

**Frontend:**
- Кнопка «Получить ИНН автоматически» в StepPersonalInfo (рядом с полем ИНН)
- Auto-trigger после применения OCR с паспортными данными

**Admin UI документов клиента:**
- В `ApplicationDetail.tsx` — блок «Документы клиента»
- Миниатюры всех загруженных документов
- Кнопки скачивания через signed URL
- Возможность для менеджера запустить OCR из админки если клиент пропустил Шаг 0

---

## DECISION LOG (последние сессии)

- [DECISION] Промпты на английском, output в исходном языке (Cyrillic stays Cyrillic, Latin stays Latin)
- [DECISION] Soft warning policy: OCR fail → файл сохранён, менеджер проверит вручную
- [DECISION] PDF не распознаётся через OCR (только хранится). Только JPEG/PNG/WebP/HEIC.
- [DECISION] Promo screen «Что мы извлекли» обязательный после OCR (даёт клиенту контроль)
- [DECISION] Conflict UI: только реальные конфликты, default «оставить ручной ввод»
- [DECISION] Education conflict: 3 опции (skip/add/replace), default skip
- [DECISION] Транслитерация на backend через ГОСТ 52535.1-2006 (стандарт паспортов с 2010 года)
- [DECISION] PROJECT_STATE.md: НЕ хранить значения секретов, только имена env-переменных
- [DECISION] Stack final: Vercel + Railway + R2 + OpenRouter (никаких изменений в обозримом будущем)

---

## USER PREFERENCES

- Язык общения: **русский**, casual technical tone («ок», «идём дальше», «хорошо»)
- Production-first deployment philosophy (тестирование на проде ОК для maker stage)
- Команда: 4 менеджера, нужна админская роль
- Reaction to manual diff edits: **«вообще ничего не понял»** → всегда давать **готовые файлы целиком на замену**, не diff-инструкции
- Reaction to готовым файлам: **«идём дальше»** → значит работает
- Format predпочтений: концентрированные ответы, мало formatting, прямо к делу
- Ошибки и баги: показывать логи Railway (Build Logs vs Deploy Logs vs HTTP Logs — важно!)

---

## SESSION HISTORY (краткое)

- Sessions 1-9: базовая разработка (модели, генерация, админка)
- Session 10: ZIP packaging
- Session 11: production deploy (Vercel + Railway + R2)
- Session 12 (текущая): **Pack 13** family — клиентский кабинет с OCR
  - 13.0a/b: infrastructure + UI
  - 13.1: реальный OCR
  - 13.1.1: conflict resolution
  - 13.1.2: ГОСТ транслит (готов, не задеплоен)
  - Решённые проблемы: .dockerignore `**/storage/`, R2_ACCOUNT_ID `cfat_...`

---

**END OF STATE**
