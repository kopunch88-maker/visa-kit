# CLAUDE.md — entry point для AI-ассистентов

> Этот файл читают **первым делом** Claude Code, Cursor и другие AI-инструменты
> при открытии репо. Если ты работаешь над этим проектом через AI — начни здесь.

---

## 🛑 ОБЯЗАТЕЛЬНО — прочти ПЕРЕД любым ответом

**`./PROJECT_STATE.md`** — мастер-документ проекта (~360 КБ, 3300+ строк).

Это **единственный источник правды**. В нём:
- Архитектура и подсистемы (Position, Application, шаблоны, ИНН-пул, импорт пакетов)
- TL;DR каждой рабочей сессии (что сделано, какие Pack применены)
- 57 правил проекта (с номерами для быстрого grep)
- 34 разобранных инцидента («что пошло не так и почему»)
- Технический долг и Roadmap
- Применённые миграции БД
- Список активных шаблонов DOCX

**Без чтения PROJECT_STATE.md любой ответ будет содержать догадки и ошибки.**
Файл собирается за многие сессии и описывает реальное состояние, а не идеальное.

---

## Что это за проект

**Бизнес:** Spain Digital Nomad Visa агентство (~50 заявок/мес).

Команда: владелец (Костя) + 4 менеджера. Клиенты — россияне и не только, оформляют
визу через нас, нанимаются в наши российские юрлица (8 компаний) на типовых
должностях, мы готовим пакет документов (~14 файлов) для подачи в UGE Испании.

**Главный enemy** — рассинхронизация данных между документами. Если ИНН компании
введён один раз, он должен попасть в договор, акты, счета, выписку, EGRYL и
письмо одинаково. Поэтому архитектура:

```
Анкета клиента → Application (БД) → справочники (Company, Position, Address, Representative)
                ↓
                Шаблоны DOCX/PDF с {{ }} ← один источник истины ← Application
                ↓
                Готовый пакет (~14 файлов)
```

---

## Технический стек (актуальный)

| Слой | Технология | Где живёт |
|---|---|---|
| **Frontend** | Next.js 16, React, TypeScript strict, Tailwind, shadcn/ui | Vercel — `visa-kit.vercel.app` |
| **Backend** | FastAPI, Python 3.12, SQLModel, Pydantic | Railway — `visa-kit-production.up.railway.app` |
| **DB** | PostgreSQL | Railway managed |
| **Storage** | Cloudflare R2 (S3-compatible) | account `93b044dabe95d0bf265540653ee681d2`, bucket `visa-kit-storage` |
| **LLM** | OpenRouter `anthropic/claude-sonnet-4-5` | для OCR паспортов, классификации документов |
| **Templating** | docxtpl (Jinja2 в .docx) | `templates/docx/`, `templates/pdf/` |
| **Local repo** | git | `D:\VISA\visa_kit\`, GitHub `kopunch88-maker/visa-kit` |

**Чего НЕТ в проекте** (несмотря на ожидания):
- Нет alembic — миграции через `apply_packX_Y_migration()` функции в `backend/app/db.py`,
  вызываются из FastAPI lifespan при старте. Идемпотентны (`ADD COLUMN IF NOT EXISTS`).
- Нет pytest-инфраструктуры — тестов почти нет (см. Правило 53 ниже).
- Нет docker-compose / локального dev-окружения — всё на Railway/Vercel.
- Нет Alembic, Celery, Redis. FastAPI BackgroundTasks для асинхронной работы.
- Нет magic-link auth, нет JWT-сессий — другая схема (см. `backend/app/auth/`).
- Нет AWS S3 — Cloudflare R2 (через boto3 с custom endpoint).
- Нет `openapi-typescript` — типы в `frontend/lib/api.ts` пишутся вручную.

---

## Workflow проекта (КРИТИЧЕСКИ ВАЖНО)

### Pack-патчер pattern

Изменения вносятся **пакетами** с номерами: Pack 28.5, Pack 29.0, Pack 32.0.3, и т.д.
Pack — это связанный набор изменений (1-15 файлов в одной задаче).

**Каждый Pack применяется через self-contained `.ps1` патчер**, который:
1. Лежит в `Downloads/`, не в репо
2. Содержит встроенный (base64) Python-патчер
3. Поддерживает `--dry-run` (показывает что изменится) и `--apply` (применяет)
4. **Идемпотентен** через marker-комментарии (повторный запуск = `[skip]`)
5. Сохраняет `.bak_pre_packX_Y` рядом с каждым изменённым файлом
6. Сохраняет EOL (CRLF) — это Windows-репо

**Если ты Claude Code:** ты НЕ применяешь патчи через `.ps1`. Ты редактируешь файлы
напрямую (через свои tools). `.ps1` пакеты — это паттерн для Claude в чате
(Anthropic web), который не имеет прямого доступа к файлам Кости.

### Push-to-prod без локальных тестов (Правило 53)

После применения изменений и dry-run пайплайн такой:

```
patch применён → git status → git add → git commit → git push → ждём Railway/Vercel → проверка в браузере
```

**Никаких** `uvicorn локально`, `npm run dev`, `pytest`. Проверка идёт в проде.

**Когда правило НЕ работает** (нужно настоять на локальном тесте):
- Изменение **новых зависимостей** (не было `pip install`/`npm install` ранее)
- Изменение **ENV vars** или конфигов
- Любые **destructive миграции** (DROP COLUMN, RENAME COLUMN — Правило 18)
- Не было симуляции в sandbox-е

### Кириллица в комментариях

Кодовая база содержит много **русских комментариев** (исторически). Это нормально.
Не переписывать комментарии на английский без явной просьбы.

**Однако** при создании новых .ps1 / .py из чата (Anthropic web) — только ASCII,
потому что PowerShell ругается на кириллицу без BOM (Правило 50).

---

## 7 главных принципов (бизнес-логика)

### 1. Один источник истины — Application

Любое поле, которое появляется в двух документах, лежит в Application или в
связанном справочнике РОВНО ОДИН РАЗ. Не дублировать.

❌ Плохо: в Application есть `company_inn`, и в Company есть `inn`.
✅ Хорошо: в Application есть `company_id` → ссылка на Company, у которой `inn`.

### 2. Шаблоны — это файлы, а не код

Шаблоны лежат в `templates/docx/*.docx` и `templates/pdf/*.pdf`. Это **обычные
документы**, которые менеджер открывает в Word и редактирует. Переменные
обозначены как `{{ contract.salary_rub }}` (Jinja2 через docxtpl).

**Никогда** не зашиваем в Python код текст, который должен видеть клиент или UGE —
он всегда в шаблоне.

⚠️ Финальная проверка DOCX — **всегда в Word**, не в LibreOffice (Правило 25).

### 3. Бизнес-валидация перед рендером

В `Application.validate_business_rules()` проверяем правила UGE:
- Договор подписан ≥90 дней назад
- Зарплата в EUR ≥ минимума UGE
- Справки о несудимости не старше 90 дней
- Все обязательные файлы загружены

Если проверки не прошли — НЕ рендерим, возвращаем список проблем.

### 4. Переиспользование через справочники

Менеджер один раз создаёт `Company`, `Position`, `Representative`, `SpainAddress`
в админке — они переиспользуются во всех будущих заявках. При создании заявки
менеджер выбирает из списка, не вводит реквизиты заново.

### 5. Поддержка не-РФ клиентов

Не делать жёстких regex для ИНН (12 цифр), адресов («индекс РФ»), паспортов.
ИНН опциональный (только у россиян). Адрес — произвольная строка. Паспорт —
строка любого формата.

Гражданство и страна юрлица — обязательные поля.

### 6. Семейные подачи (~20% случаев)

В Application есть `family_members: List[FamilyMember]`. Если непустой — на
каждого члена семьи генерируется свой суб-пакет (MI-F форма, паспорт,
designación, тасса, банк. сертификат).

### 7. Position не привязан к Company (Pack 20.0)

Position определяется парой `(specialty_id, level)`. Связь Company↔Position идёт
**только через Application**: `application.company_id` + `application.position_id`
независимо. См. PROJECT_STATE раздел 3.1.

---

## Стиль кода

### Python (backend)

- Type hints везде, никаких голых dict
- **SQLModel** для всех БД-сущностей (не plain Pydantic, не dataclass)
- Pydantic для request/response схем
- `session.get(Model, id)` для связей — **не** `model.relationship` атрибут
  (Правило 52, см. PROJECT_STATE)
- Docstrings ОБЯЗАТЕЛЬНЫ для функций бизнес-логики и API endpoints
- Имена функций/переменных — английский. Комментарии — где как (исторически рус)

### TypeScript (frontend)

- Strict mode, никаких `any`
- Функциональные компоненты с типизированными props
- shadcn/ui компоненты копируются в `components/ui/`
- API-клиент в `lib/api.ts` — типы пишутся **вручную**, не через openapi-typescript
- Pack-нумерация в комментариях (`// Pack 32.0.2: ...`) — не стирать,
  это маркеры для будущего grep

---

## Что НЕ делаем

- ❌ Не пишем raw SQL — только через SQLModel (исключения в `db/raw_queries.py` если
  действительно нужно)
- ❌ Не сохраняем файлы клиентов на ФС сервера — только в R2
- ❌ Не отправляем persondata в LLM без явной задачи (OCR паспорта, классификация
  документа — OK; «расскажи что в этом досье» — нет)
- ❌ Не делаем синхронные вызовы LLM/OCR в HTTP-handler — только через
  `BackgroundTasks` (см. Pack 31.0)
- ❌ Не делаем DROP COLUMN, RENAME COLUMN без полного git grep по коду (Правило 18)
- ❌ Не используем `from app.models import *` — только конкретные импорты
  (Правило 40)
- ❌ Не делаем локальное dev-окружение — оно не настроено и не поддерживается

---

## Структура репо

```
D:\VISA\visa_kit\
├── CLAUDE.md                      ← этот файл
├── PROJECT_STATE.md               ← мастер-документ (читать первым)
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py                ← FastAPI app, lifespan, регистрация роутов
│   │   ├── db.py                  ← engine, миграции apply_packX_Y_migration()
│   │   ├── models/                ← SQLModel сущности (Application, Company...)
│   │   ├── api/                   ← FastAPI routes
│   │   ├── services/              ← бизнес-логика (рендер, OCR, ИНН-генератор)
│   │   ├── templates_engine/      ← docxtpl рендер, registry шаблонов
│   │   └── storage/               ← R2/local абстракция
│   ├── requirements.txt
│   └── railway.toml
├── frontend/
│   ├── components/
│   │   ├── ui/                    ← shadcn/ui (скопированы)
│   │   ├── admin/                 ← админка
│   │   └── client/                ← кабинет клиента
│   ├── lib/
│   │   └── api.ts                 ← типы + fetch-обёртки (вручную, не openapi-ts)
│   └── app/                       ← Next.js routes
└── templates/
    ├── docx/                      ← основные шаблоны (CV, contract, акт, счёт...)
    │   └── contracts/by_company/  ← компания-специфичные шаблоны
    └── pdf/                       ← UGE формы (MI-T, MI-F, Tasa 790-052...)
```

В подпапках `backend/app/api/`, `backend/app/models/`, `backend/app/services/` и
`templates/` лежат **локальные CLAUDE.md** с подсистемно-специфичным контекстом.
Если работаешь над конкретным модулем — открой соответствующий локальный
CLAUDE.md.

---

## Полезные команды

```bash
# Поиск по PROJECT_STATE (находит правила, инциденты, Pack-номера)
grep -n "Правило 53" PROJECT_STATE.md
grep -n "Pack 32" PROJECT_STATE.md
grep -n "Инцидент" PROJECT_STATE.md

# Backend
cd backend
pip install -r requirements.txt   # если нужно (обычно зависимости через Railway)
python -c "from app.main import app; print('OK')"   # smoke import-test

# Frontend
cd frontend
npm install
npm run build                     # production build (TypeScript check + Next compile)

# Git workflow для Pack-ов
git status
git diff backend/app/api/some_file.py
git add ...
git commit -m "Pack X.Y: краткое описание"
git push
# Дальше Railway пересобирает за ~1-2 мин, Vercel за ~30-60 сек
```

⚠️ **PowerShell не понимает bash-style continuation `\`** (Правило 48). При нескольких `git add` — каждый отдельной строкой, не через `\` в конце:
```powershell
git add backend/app/db/migrations.py
git add backend/app/main.py
git add backend/app/models/applicant.py
```

---

## Если ты Claude Code или Cursor — чек-лист первой сессии

1. ✅ Прочитал этот CLAUDE.md
2. ✅ Открыл и прочитал `./PROJECT_STATE.md` целиком (это **обязательно**)
3. ✅ Понял что у Кости push-to-prod workflow (Правило 53)
4. ✅ Понял что миграции БД через lifespan, не alembic
5. ✅ Понял Pack-нумерацию: каждое значимое изменение → новый Pack-номер
6. ✅ При работе над файлом — открой локальный CLAUDE.md в его папке если есть
7. ✅ После любого breaking change — обновляй PROJECT_STATE.md (TL;DR + правила
   + инциденты + техдолг)

**Не отвечай на вопросы пользователя пока эти 7 пунктов не выполнены.** В этом
проекте контекст важнее скорости.

---

**Версия документа:** 2.2 (11.05.2026 поздний вечер — Pack 35.x продолжение 35.6-35.10)
**Базируется на:** реальное состояние репо visa-kit на этот момент.
**Обновлять:** при значимых архитектурных изменениях (раз в 5-10 Pack-ов).
