# 🚀 Запуск на Windows (без Docker)

Эта инструкция — как поднять бэкенд visa-kit на чистой Windows за 5 минут.
Никакого Docker, WSL, виртуализации — только Python.

## Что делаем

1. Распаковать обновлённый проект в `D:\VISA\visa_kit\` (поверх старого)
2. Активировать виртуальное окружение (уже создано из прошлого раза)
3. Поставить зависимости
4. Запустить seed (заполнит БД 8 компаниями и т.д.)
5. Запустить сервер
6. Открыть браузер на `http://localhost:8000/docs`

---

## Шаг 1: Распаковать новый zip

Скачайте `visa_kit.zip` из чата. Распакуйте в `D:\VISA\` так, чтобы заменить
существующие файлы. Если спросит «заменить ли существующие файлы» — отвечайте **да**.

## Шаг 2: Открыть PowerShell и активировать venv

Откройте PowerShell (Win + X → Терминал). Выполните:

```powershell
cd D:\VISA\visa_kit\backend
.venv\Scripts\Activate.ps1
```

Если ругается на политику выполнения скриптов:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

После активации в начале строки должно появиться `(.venv)`.

## Шаг 3: Установить зависимости

```powershell
pip install -e ".[dev]"
```

Это займёт 1-2 минуты — pip скачает FastAPI, SQLModel, Anthropic SDK и др.

## Шаг 4: Заполнить БД начальными данными

```powershell
python scripts/seed.py
```

Должно вывести:
```
🌱 Seeding database...
📦 Companies: ✓ Created company 'СК10' ... (всего 8)
💼 Positions: ✓ Created position ... (всего 9)
👤 Representatives: ✓ Created representative ANASTASIIA KORENEVA
📍 Spain Addresses: ✓ Created address ... (всего 2)
🔑 Admin user: ✓ Created admin user 'admin@visa-kit.local'
✅ Seed complete!
```

После этого в папке `backend/` появится файл `dev.db` — это SQLite база данных.

## Шаг 5: Запустить сервер

```powershell
uvicorn app.main:app --reload
```

Должно вывести что-то вроде:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Started reloader process
📦 Database ready at sqlite:///...
📁 Local file storage: ...
INFO:     Application startup complete.
```

## Шаг 6: Открыть Swagger UI

Откройте в браузере: **http://localhost:8000/docs**

Это интерактивная документация API. Здесь видно все эндпоинты, можно их тыкать.

### Как залогиниться через Swagger

1. Найдите раздел **auth** → `POST /api/auth/login`
2. Нажмите **Try it out**
3. В теле запроса введите:
   ```json
   {"email": "admin@visa-kit.local"}
   ```
4. Нажмите **Execute**
5. В ответе скопируйте `access_token`

Теперь нажмите кнопку **Authorize** в правом верхнем углу страницы, вставьте токен. После этого все защищённые эндпоинты будут работать.

### Что попробовать

- `GET /api/admin/companies` — увидите список 8 ваших компаний
- `POST /api/admin/applications` — создать тестовую заявку
- `GET /api/admin/applications` — увидеть созданную заявку

---

## Что делать дальше

Если всё работает — пишите в чат **"Этап 1 готов, всё запустилось"**, и пойдём
дальше: добавим CRUD для остальных справочников (Position, Representative,
SpainAddress) и начнём делать шаблоны документов.

Если что-то не работает — копируйте полный текст ошибки из консоли в чат, разберёмся.

## Что лежит в проекте

```
backend/
├── app/
│   ├── main.py              ← точка входа FastAPI
│   ├── config.py            ← настройки
│   ├── api/
│   │   ├── auth.py          ← логин (магия — без пароля в dev)
│   │   ├── companies.py     ← CRUD компаний
│   │   └── applications.py  ← CRUD заявок + назначение + статусы
│   ├── models/              ← все 12 сущностей БД
│   ├── services/
│   │   ├── recommendation.py  ← LLM-рекомендация
│   │   └── status_machine.py  ← переходы статусов
│   └── db/                  ← подключение к БД
├── scripts/
│   └── seed.py              ← залить начальные данные
├── pyproject.toml           ← зависимости
└── dev.db                   ← БД (создаётся автоматически)
```

## Полезные команды

```powershell
# Перезаливка БД с нуля (если что-то накосячили)
Remove-Item dev.db
python scripts/seed.py

# Запуск тестов
pytest

# Форматирование кода
black .

# Запуск сервера в фоне (если нужно)
Start-Process powershell -ArgumentList "-NoExit","-Command","uvicorn app.main:app --reload"
```
