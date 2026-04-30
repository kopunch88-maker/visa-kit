# Visa kit

Система автоматизации подачи документов на испанскую digital nomad визу
(Teletrabajador de carácter internacional, RD 1155/2024).

Поток ~50 заявок/месяц. Команда менеджеров + клиенты заполняют анкеты сами.

## Что делает система

1. Клиент заполняет короткую анкету в кабинете (личные данные, опыт, документы)
2. Менеджер в админке распределяет ему компанию-заказчика, должность, адрес в Испании, представителя
3. Система генерирует пакет документов (договор, акты, счета, выписку, MI-T форму и др.)
4. Документы отправляются на присяжный перевод и подпись (вне системы)
5. Подписанные сканы загружаются обратно
6. Представитель ставит ЭЦП в Autofirma и подаёт в UGE

## Стек

- **Backend**: Python 3.12, FastAPI, SQLModel, PostgreSQL 16
- **Frontend**: Next.js 15 (App Router), TypeScript, react-hook-form, Tailwind, shadcn/ui
- **Хранилище файлов**: S3-совместимое (MinIO локально, Cloudflare R2 в проде)
- **Документы**: docxtpl (DOCX-шаблоны), pypdf (PDF-формы)
- **LLM**: Anthropic API (рекомендация должностей, OCR паспорта)
- **Деплой**: Docker Compose на VPS (Hetzner Cloud)

## Структура

```
visa_kit/
├── backend/              # FastAPI приложение
│   ├── app/
│   │   ├── models/       # SQLModel сущности (БД и API одновременно)
│   │   ├── api/          # HTTP эндпоинты
│   │   ├── services/     # Бизнес-логика (рекомендации, OCR, рендер)
│   │   ├── templates_engine/  # Подстановка данных в DOCX/PDF шаблоны
│   │   └── db/           # Соединение с БД, миграции
│   └── tests/
├── frontend/             # Next.js приложение
│   ├── src/
│   │   ├── app/
│   │   │   ├── client/   # Кабинет клиента (анкета)
│   │   │   └── admin/    # Админка команды
│   │   ├── components/   # Переиспользуемые UI-компоненты
│   │   └── lib/          # Утилиты, API-клиент
├── templates/            # DOCX/PDF шаблоны документов
│   ├── docx/             # contract, act, invoice, employer_letter, cv, bank_statement
│   └── pdf/              # mit, mif, designacion, declaracion_penales, compromiso_reta
├── infra/                # docker-compose, конфиги nginx, скрипты деплоя
├── examples/             # JSON-примеры заявок для тестов
├── scripts/              # Утилиты разработчика (сид БД, миграции и т.п.)
└── docs/                 # Архитектура, API, бизнес-логика
```

## Быстрый старт

```bash
# 1. Поднимаем PostgreSQL и MinIO в Docker
cd infra && docker compose up -d

# 2. Настраиваем backend
cd ../backend
cp .env.example .env       # затем правим .env (см. ниже)
python -m venv .venv && source .venv/bin/activate
pip install -e .
alembic upgrade head       # создаёт таблицы
python scripts/seed.py     # загружает справочники компаний/должностей

# 3. Запускаем backend
uvicorn app.main:app --reload  # http://localhost:8000

# 4. Настраиваем и запускаем frontend
cd ../frontend
cp .env.local.example .env.local
npm install
npm run dev                # http://localhost:3000
```

Открываем http://localhost:3000 — попадаем в админку (после логина).
http://localhost:3000/client/<token> — кабинет клиента (токен генерится менеджером).

## Переменные окружения

См. `backend/.env.example` и `frontend/.env.local.example`. Главное:
- `DATABASE_URL` — Postgres
- `S3_*` — реквизиты MinIO/R2
- `ANTHROPIC_API_KEY` — для рекомендаций и OCR
- `JWT_SECRET` — секрет для авторизации команды

## Работа с Claude Code / Cursor

В каждой важной папке лежит `CLAUDE.md` — инструкция для LLM, что в этой папке,
какие соглашения, какие паттерны копировать. **Открывая Cursor, начните с прочтения
корневого `CLAUDE.md` — это сэкономит часы.**

При добавлении нового шаблона документа, новой сущности, нового эндпоинта — всегда
начинайте с фразы "Прочитай CLAUDE.md в этой папке". Тогда LLM поймёт паттерн и
сделает по аналогии.

## Документация

- `docs/architecture.md` — архитектура системы, диаграммы данных
- `docs/business_rules.md` — правила UGE для подачи (90 дней, минимум зарплаты и т.п.)
- `docs/templates_guide.md` — как редактировать шаблоны документов в Word
- `docs/api.md` — основные эндпоинты бэкенда (или см. /docs FastAPI Swagger)
