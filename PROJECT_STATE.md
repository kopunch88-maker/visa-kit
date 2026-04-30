# VISA KIT — состояние проекта

**Последнее обновление:** 30 апреля 2026
**Статус:** 🚀 PRODUCTION работает, MVP + мобилка задеплоены

---

## Что в production

### URLs

- **Frontend:** https://visa-kit.vercel.app
- **Backend:** https://visa-kit-production.up.railway.app
- **API Docs:** https://visa-kit-production.up.railway.app/docs
- **GitHub:** https://github.com/kopunch88-maker/visa-kit (private)

### Стек

- **GitHub** — monorepo (backend + frontend + templates), main branch, deploy via push
- **Railway** — backend (Docker, Python 3.12) + PostgreSQL
- **Vercel** — frontend (Next.js 16.2.4)
- **Cloudflare R2** — хранилище файлов (bucket `visa-kit-storage`)
- **Stack:** FastAPI + SQLModel + bcrypt JWT + Next.js + Tailwind

### Стоимость

~$5-10/мес (Railway). Vercel/R2/GitHub бесплатно.

### Пользователи

- `panchenkoconstantin@gmail.com` — admin (Constantin)
- 3 менеджера будут добавлены позже

---

## Прогресс по плану

### Phase 1 — MVP (✅ ЗАВЕРШЁН + В PRODUCTION)

- ✅ Pack 1-7 — Базовая архитектура
- ✅ Pack 8.x — Админка (двухпанельный layout, CRUD справочников)
- ✅ Pack 9 — 4 испанские PDF-формы
- ✅ Pack 9.1 — Скачивание отдельных файлов
- ✅ Pack 10 + 10.1 — Архив с ФИО
- ✅ Pack 11 + 11.1 + 11.2 — Production deployment (bcrypt, R2, PostgreSQL, Optional поля)
- ✅ Pack 12 — Mobile-аккордеон клиентского кабинета (desktop не тронут)

### Phase 2 — Агенты автоматизации (⬜ НЕ НАЧАТА)

Roadmap (можно делать в любом порядке):
- Pack 13 — OCR паспорта (Claude Vision API)
- Pack 14 — Авто-проверка пакета перед скачиванием
- Pack 15 — Email-агент
- Pack 16 — Авто-распределение по компаниям
- Pack 17 — Перевод-черновик на испанский
- Pack 18 — Мониторинг статусов в UGE (хрупкое, последним)

### Намеренно отложено

- ⏸️ Семейная подача (после обкатки одиночных)
- ⏸️ Свой домен
- ⏸️ Пункт о ПДн в шаблоне договора

---

## Текущие мелкие баги (не блокируют)

1. **`employer_letter` падает с `None.month`** — `08_Письмо.docx` не попадает в ZIP. Файл `backend/app/templates_engine/render_employer_letter.py`. Fix: fallback `.month` на `application.contract_sign_date`.

2. **«Все 10 документов сгенерированы»** в `frontend/components/admin/BusinessChecksBlock.tsx`. Должно быть 14 (10 DOCX + 4 PDF).

3. **Эстетика мобилки** — может потребоваться полировка по фидбеку команды.

---

## Деплой workflow

```powershell
cd D:\VISA\visa_kit
git add .
git commit -m "Описание"
git push
```

Vercel + Railway автоматически передеплоятся за 2-5 минут.

**ВАЖНО:** GitHub Push Protection блокирует коммиты с секретами (Cloudflare/AWS keys и т.д.). Не вписывать реальные значения в код или markdown файлы. Всё хранится в Railway/Vercel UI.

---

## Создание пользователей в production

Используем `DATABASE_PUBLIC_URL` из Railway → Postgres → Variables.

```powershell
cd D:\VISA\visa_kit\backend
$env:DATABASE_URL="<DATABASE_PUBLIC_URL из Railway>"
python scripts/create_admin.py
$env:DATABASE_URL=$null  # обязательно сбросить
```

Railway периодически ротирует пароль БД — берём свежий URL каждый раз.

---

## Production env-переменные (имена)

**Railway (visa-kit service):**
- `DATABASE_URL` (через `${{Postgres.DATABASE_URL}}`)
- `FRONTEND_URL` = `https://visa-kit.vercel.app`
- `JWT_SECRET` (длинная случайная строка)
- `SECRET_KEY` (то же значение)
- `STORAGE_BACKEND` = `r2`
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME` = `visa-kit-storage`

**Vercel:**
- `NEXT_PUBLIC_API_URL` = `https://visa-kit-production.up.railway.app`

Реальные значения — в Railway/Vercel UI и в notes у Constantin.

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

Логин: `http://localhost:3000/admin/login`

**Если фронт ходит в production вместо локала** — Vercel CLI ранее переписал `.env.local`. Восстановить:
```
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Технический долг

1. **TypeScript ошибки игнорируются** при build (`ignoreBuildErrors: true`). ~5-10 мест с `any`.
2. **Next.js 16.2.4** — могут вылезти несовместимости.
3. **eslint-ключ** в next.config.js даёт варнинг в Next 16 — некритично.
4. **Vercel CLI** переписывает `.env.local` при `vercel link` — учесть.

---

## История пакетов

| Pack | Что добавил |
|---|---|
| 1-7 | Базовая архитектура, модели, DOCX, клиентский кабинет |
| 8.x | Админка (двухпанельная, CRUD справочников, settings) |
| 9 | 4 испанские PDF-формы (MI-T, Designación, Compromiso, Declaración) |
| 9.1 | Скачивание отдельных файлов |
| 10 | Архив завершённых заявок |
| 10.1 | ФИО в архиве |
| 11 | Production deployment (bcrypt, R2, PostgreSQL, Docker, Vercel/Railway) |
| 11.1 | Auth fix для существующей User модели |
| 11.2 | Optional поля Applicant + миграция PostgreSQL |
| 12 | Mobile-аккордеон клиентского кабинета (desktop не тронут) |

---

## Цели после Phase 2

- Время менеджера на одну заявку: **с 4-6 часов → до 30 минут**
- Один менеджер ведёт: **с 50 → 200+ заявок/мес**

---

## Что попросить в следующей сессии

**Чиним мелкие баги:**
- Прислать `backend/app/templates_engine/render_employer_letter.py` → починю `None.month`
- Прислать `frontend/components/admin/BusinessChecksBlock.tsx` → обновлю «10» на «14»

**Полируем мобилку (если будет фидбек):**
- Скриншоты проблем + описание

**Phase 2 — выбрать пакет:**
- Pack 13 OCR паспорта (рекомендую первым)
- Pack 14 Авто-проверка пакета
- Pack 15 Email-агент
- Что-то другое из roadmap

---

## Шаблон для следующей сессии

```
Привет! Production работает уже N дней. 
Прикрепляю PROJECT_STATE.md.

Сегодня делаем: ___
[фидбек от команды если есть]
```
