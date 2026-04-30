# VISA KIT — состояние проекта на конец сессии 10

**Дата:** 30 апреля 2026
**Статус:** 🚀 **PRODUCTION ЗАДЕПЛОЕН И РАБОТАЕТ**

---

## Что в production

### URLs

- **Frontend (Vercel):** https://visa-kit.vercel.app
- **Backend (Railway):** https://visa-kit-production.up.railway.app
- **API Docs:** https://visa-kit-production.up.railway.app/docs
- **Health:** https://visa-kit-production.up.railway.app/health
- **GitHub репо:** https://github.com/kopunch88-maker/visa-kit (private)

### Инфраструктура

- **GitHub** — monorepo (backend + frontend + templates), main branch
- **Railway** — backend (Docker, Python 3.12) + PostgreSQL
- **Vercel** — frontend (Next.js 16.2.4)
- **Cloudflare R2** — хранилище файлов (bucket `visa-kit-storage`)
- **Stack:** FastAPI + SQLModel + bcrypt JWT + Next.js + Tailwind

### Стоимость

- Vercel Hobby: $0
- Railway: ~$5-10/мес (Hobby plan, $5 кредит/мес)
- Cloudflare R2: $0 (до 10GB)
- GitHub: $0 (private)
- **Итого: $5-10/мес**

### Пользователи

- **panchenkoconstantin@gmail.com** — admin (Constantin)
- Остальные 3 менеджера — будут созданы по мере включения в команду

---

## Прогресс по плану

### Phase 1 — MVP (✅ ЗАВЕРШЁН)
- ✅ Pack 1-7 — Базовая архитектура, модели, DOCX, клиентский кабинет
- ✅ Pack 8 / 8.5 / 8.6 / 8.7 — Админка с двухпанельным layout, CRUD справочников
- ✅ Pack 9 — 4 испанские PDF-формы (MI-T, Designación, Compromiso, Declaración)
- ✅ Pack 9.1 — Скачивание по клику любого файла отдельно
- ✅ Pack 10 — Архив завершённых заявок
- ✅ Pack 10.1 — ФИО заявителя в таблице архива
- ✅ Pack 11 — Production deployment (bcrypt auth, R2, PostgreSQL, Docker)
- ✅ Pack 11.1 — Auth fix для существующей User модели (password_hash)
- ✅ Pack 11.2 — Optional поля в Applicant для пошагового сохранения
- ✅ Pack 12 — Mobile-аккордеон для клиентского кабинета (desktop не тронут)

### Phase 2 — Агенты автоматизации (НЕ НАЧАТА)
- ⬜ Pack 13 — OCR паспорта (Claude Vision API)
- ⬜ Pack 14 — Авто-проверка пакета перед скачиванием
- ⬜ Pack 15 — Email-агент
- ⬜ Pack 16 — Авто-распределение по компаниям
- ⬜ Pack 17 — Перевод-черновик на испанский
- ⬜ Pack 18 — Мониторинг статусов в UGE (хрупкое)

### Намеренно отложено
- ⏸️ Семейная подача (нужно сначала обкатать одиночные кейсы)
- ⏸️ Свой домен (visa-kit.com или подобное)
- ⏸️ Пункт о ПДн в шаблоне договора

---

## Что важно знать (НЕ ЗАБЫТЬ В СЛЕДУЮЩЕЙ СЕССИИ)

### 1. Известные мелкие баги

**A. `employer_letter` падает с `None.month`**
- В логах при генерации: `[employer_letter] render failed: UndefinedError: 'None' has no attribute 'month'`
- `08_Письмо.docx` не попадает в ZIP корректно
- Файл: `backend/app/templates_engine/render_employer_letter.py`
- Fix: где-то используется `.month` без проверки на None. Поставить fallback на `application.contract_sign_date` или сегодняшнюю дату.

**B. Чек-лист показывает «Все 10 документов сгенерированы»**
- Файл: `frontend/components/admin/BusinessChecksBlock.tsx`
- Должно быть «Все 14 документов» (10 DOCX + 4 PDF).
- Косметика, не блокирует.

### 2. Деплой workflow

Любые изменения теперь идут через git push:

```powershell
cd D:\VISA\visa_kit
git add .
git commit -m "Описание"
git push
```

**Vercel** и **Railway** автоматически передеплоятся. Через 2-5 минут изменения в production.

### 3. Создание пользователей в production

Используем DATABASE_PUBLIC_URL Railway. Сам URL — взять в Railway → Postgres → Variables → `DATABASE_PUBLIC_URL`. Формат:

```
postgresql://postgres:<password>@switchyard.proxy.rlwy.net:<port>/railway
```

Запуск:

```powershell
cd D:\VISA\visa_kit\backend
$env:DATABASE_URL="<значение из Railway DATABASE_PUBLIC_URL>"
python scripts/create_admin.py
$env:DATABASE_URL=$null  # сбросить после
```

**ВАЖНО:** Railway периодически ротирует пароль БД. Если перестанет работать — взять свежий `DATABASE_PUBLIC_URL`.

### 4. Локальная разработка после деплоя

После Vercel CLI link, локальный `.env.local` мог быть переписан. Если локальный фронт не работает, восстановить:

```
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

```
# backend/.env (создать заново если нет)
DATABASE_URL=sqlite:///./dev.db
FRONTEND_URL=http://localhost:3000
JWT_SECRET=dev-secret-change-in-production-please
SECRET_KEY=dev-secret-change-in-production-please
STORAGE_BACKEND=local
STORAGE_PATH=storage
```

### 5. Production env-переменные

**Все секреты хранятся ТОЛЬКО в Railway/Vercel UI**, не в репо и не в этом файле.

**Railway (visa-kit service Variables) — список имён:**
- `DATABASE_URL` (через `${{Postgres.DATABASE_URL}}`)
- `FRONTEND_URL` = `https://visa-kit.vercel.app`
- `JWT_SECRET` (длинная случайная строка)
- `SECRET_KEY` (то же значение что JWT_SECRET)
- `STORAGE_BACKEND` = `r2`
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME` = `visa-kit-storage`

**Vercel (Environment Variables):**
- `NEXT_PUBLIC_API_URL` = `https://visa-kit-production.up.railway.app`

Реальные значения секретов — в Railway/Vercel UI, в Bitwarden/1Password или в надёжном local notes у Constantin.

---

## Технический долг (НЕ КРИТИЧНО, можно копить)

1. **TypeScript ошибки игнорируются** в build (`next.config.js: ignoreBuildErrors: true`). Около 5-10 мест где параметры без типизации (например `(v) => ...` в `CompanyContractDrawer.tsx:145`).
2. **Чек-лист «10 документов»** — старый текст.
3. **Employer letter** падает на `None.month`.
4. **Vercel CLI** при `vercel link` переписал локальный `.env.local`. Учесть при следующем разворачивании.
5. **Next.js 16.2.4** — вместо стабильной 15.x. Могут быть скрытые несовместимости (хотя пока работает).
6. **eslint-ключ в next.config.js** даёт варнинг в Next 16 — некритично, но потом убрать.

---

## Технические детали

- Windows, Python 3.14 локально, Python 3.12-slim в Docker
- Проект: `D:\VISA\visa_kit\`
- Backend: FastAPI + SQLite (dev) / PostgreSQL (prod) + SQLModel
- Frontend: Next.js 16.2.4 + Tailwind
- LLM: Claude Sonnet (для рекомендаций должности)
- PDF: pypdf (AcroForm) + reportlab (с нуля)
- Шаблоны DOCX: `D:\VISA\visa_kit\templates\docx\`
- Шаблоны PDF: `D:\VISA\visa_kit\templates\pdf\`
- В Docker: `/app/templates/`

---

## Запуск локально

```powershell
# Backend
cd D:\VISA\visa_kit\backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Frontend (другое окно)
cd D:\VISA\visa_kit\frontend
npm run dev
```

Логин в админку: `http://localhost:3000/admin/login` (с email + пароль).

---

## История пакетов

| Pack | Что добавил |
|---|---|
| 1-7 | Базовая архитектура, модели, DOCX-шаблоны, клиентский кабинет |
| 8 | Админка с детальной страницей, LLM-рекомендации, ZIP-скачивание |
| 8.5 | Двухпанельный layout (список + детали) |
| 8.6 | 3 карточки, объединённая «Компания и договор», bilingual ФИО |
| 8.7 | Partial-update endpoint, CRUD справочников, settings page |
| 9 | 4 испанские PDF-формы (MI-T, Designación, Compromiso, Declaración) |
| 9.1 | Скачивание по клику любого файла отдельно |
| 10 | Архив завершённых заявок |
| 10.1 | ФИО в таблице архива |
| 11 | Production deployment (bcrypt, R2, PostgreSQL, Docker, Vercel/Railway) |
| 11.1 | Auth fix для существующей User модели (password_hash) |
| 11.2 | Optional поля в Applicant для пошагового сохранения + миграция PostgreSQL |
| 12 | Mobile-аккордеон для клиентского кабинета (desktop не тронут) |

---

## Цели после Phase 2

- Время менеджера на одну заявку: **с 4-6 часов → до 30 минут**
- Один менеджер ведёт: **с 50 → до 200+ заявок/мес**
- Возможные сценарии:
  - Рост выручки в 4-6 раз без увеличения штата
  - Снижение цены клиенту в 2-3 раза при сохранении маржи

## Что НЕ автоматизируем (намеренно)

1. Итоговое решение менеджера перед подачей (юр. ответственность)
2. Эмпатичная коммуникация в сложных кейсах (развод, отказы)
3. Оценка рисков отказа в нестандартных кейсах
4. Подача документов в UGE (нет API, серая зона)
5. Подписание документов (юр. действие)

---

## Что попросить у меня в следующей сессии

**Если хочешь чинить мелкие баги (опционально):**
1. Прислать `backend/app/templates_engine/render_employer_letter.py` — починю `None.month`
2. Прислать `frontend/components/admin/BusinessChecksBlock.tsx` — обновлю «10» на «14»

**Если сразу к Phase 2:**
- «Делаем Pack 13 (OCR паспорта)» — Claude Vision API + автозаполнение анкеты по скану
- Я начну с разработки клиентского портала загрузки паспорта + endpoint OCR

**Можно делать пакеты в любом порядке** — приоритеты выше всего лишь моя рекомендация.

**Если будет фидбек от команды:**
- Присылай скриншоты + описание поведения
- Любые изменения через git push автоматически попадут в production

---

## Финальный шаблон для следующей сессии

```
Привет! Я продолжаю работу над visa_kit. Production задеплоен и работает.
Прикрепляю PROJECT_STATE.md.

Сегодня делаем: ___ (выбрать)
- Чиним мелкие баги (employer_letter, чек-лист)
- Pack 13 — OCR паспорта  
- Pack 14 — Авто-проверка пакета
- Что-то другое из roadmap
- Реакция на фидбек команды (приложить детали)
```
