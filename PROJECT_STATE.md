# VISA KIT — PROJECT_STATE (мастер-документ)

> **🔴 КРИТИЧЕСКАЯ ИНСТРУКЦИЯ для нового Claude:**
> 1. Прочитать **этот файл целиком** перед первым ответом.
> 2. **НЕ дозагружать** старые PROJECT_STATE_*.md, _PATCH.txt, _копия*.md и пр. — этот файл единственный источник правды.
> 3. У Кости (владельца) контекст плотный — отвечать **по делу, без воды**.
> 4. **Перед любыми DROP COLUMN или breaking changes** — Правило 18 (глобальный grep).
> 5. **Перед SQL** — Правило 20 (dump схемы таблицы).
> 6. **Финальная проверка DOCX** — ВСЕГДА в Word, не в LibreOffice (Правило 25).

> **Дата последнего обновления:** 10.06.2026 (поздний вечер) — **Pack 54 (Sber v2) FULLY DEPLOYED, серия fix1..fix10**. Sber v2 выписка финализирована: Ч/Б шаблон + подпись Кирьянова Е.В. (floating 25мм) + круглая печать Сбера (floating 35мм, повёрнута на 25° по часовой) + линия подписи убрана (val=nil) + spacer 30мм перед footer + перевод RU→ES (combined PDF, та же инфраструктура Pack 53). Расширен `_add_floating_picture`: новые kwargs `z_order` (детерминированный relativeHeight) и `rotation_deg` (поворот через `a:xfrm@rot`). fix10 — критический: layout-правки перенесены ДО проверки `mode=markers_only`, иначе ES-версия в combined PDF отличалась от RU. **Следующая выписка — Pack 55.x ВТБ/Открытие** (см. Roadmap). Pack 53 (перевод RU→ES) — DEPLOYED ранее в этот же день. Предыдущее: 10.06.2026 — **Pack 51 (append-выписка) + Pack 52 серия (Ч/Б Альфа v2 + позиционирование 22 fix-итерации, финал fix22)**. Предыдущее: 03.06.2026 — **Pack 50.40 + 50.41**: разбег реестровых номеров + подсветка непросмотренных документов. Предыдущее: 30.05.2026 — Pack 50.32–50.39. Предыдущее: 29.05.2026 — Pack 50.12–50.31. Предыдущее: 26.05.2026 Pack 41.0-H..Q + 50.0/50.7/50.1 + 47/48/49.

---

# 📑 Оглавление

1. [Контекст проекта](#контекст-проекта)
2. [TL;DR — что сделано в каждой сессии](#tldr)
3. [Архитектура и ключевые подсистемы](#архитектура)
4. [Активные данные в БД](#бд)
5. [Pipeline генерации документов](#pipeline)
6. [Правила проекта (МАСТЕР-СПИСОК)](#правила)
7. [Применённые миграции БД](#миграции)
8. [Активные шаблоны DOCX/PDF](#шаблоны)
9. [Технический долг и Roadmap](#долг)
10. [Что точно работает (smoke-tested)](#работает)
11. [Критические инциденты — НЕ повторять (lessons learned)](#инциденты)

---

<a id="контекст-проекта"></a>

# 1. Контекст проекта

**Бизнес:** Spain Digital Nomad visa агентство (~50 заявок/месяц).
**Костя Панченко** — владелец (panchenkoconstantin@gmail.com). 4 менеджера работают с заявками.

**Стек:**
- **Frontend:** [visa-kit.vercel.app](https://visa-kit.vercel.app), Next.js 16.2.4, React 19, Tailwind, lucide-react
- **Backend:** [visa-kit-production.up.railway.app](https://visa-kit-production.up.railway.app), FastAPI, Python 3.12
- **Storage:** Cloudflare R2 (account `93b044dabe95d0bf265540653ee681d2`, bucket `visa-kit-storage`)
- **LLM:** OpenRouter `anthropic/claude-sonnet-4.6` (OCR + перевод + AI-аудит), `claude-sonnet-4-5` (final submission), `claude-haiku-4-5` (классификатор)
- **DB:** PostgreSQL на Railway, миграции через `apply_packXX_migration()` функции в `backend/app/db/migrations.py` + lifespan

**Ключевые URL/пути:**
- **GitHub:** `kopunch88-maker/visa-kit`
- **Local repo:** `D:\VISA\visa_kit\`
- **DOCX templates:** `D:\VISA\visa_kit\templates\docx\` (⚠️ НЕ `backend/templates/`)
- **PDF templates:** `D:\VISA\visa_kit\templates\pdf\`
- **DATABASE_URL:** `postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway`

**Workflow деплоя:**
- Изменения через apply-скрипты `apply_pack*.py` в стиле точечных правок с backup и идемпотентностью (Правило 34).
- После `git push origin main` — Railway автодеплоит backend, Vercel автодеплоит frontend.

---

<a id="tldr"></a>

# 2. TL;DR — что сделано в каждой сессии

## История до Pack 30 (02-08.05.2026) — основа проекта

Сжатое summary первых 6 сессий: клиентский кабинет + OCR через Claude Vision + GOST транслит + PDF.js (Pack 13.x); bulk import + AI classifier + EGRYL + 60+ стран + nationality (Pack 14.x); испанский перевод документов через LLM (Pack 15.x); банки + генерация банковской выписки + сокращения адресов по Минфину 171н (Pack 16.x, финал 16.5e/16.7); ИНН самозанятого через SNRIP-дамп ФНС 546k+ записей (Pack 17.x); индикаторы ИНН + fallback при блокировке Railway-IP в ФНС API + парсинг паспортов + апостиль НПД + birth_country (Pack 18.x); справочник вузов 38 + специальностей 30 ОКСО + 111 паттернов маппинга должность→специальность + генератор work_history с LegendCompany 71 запись (Pack 19.x); Position отвязан от Company, 28 должностей, work_history_generator на Position с duties-snapshot, профессиональный двухколонный CV-шаблон (Pack 20.x); seed представителей 5 + испанских адресов 11 (Pack 21.0); починка bank_statement + abbreviate_address во ВСЕХ документах + нумерация акт/счёт по месяцу + DN-наниматель первой записью в CV (Pack 25.x); переработка bank_statement_generator + миграция bank_statement_date + UI секция в ApplicantDrawer + DIPLOMA_MAIN всегда замещает applicant.education (Pack 25.8-25.12); DOCX-импорт реквизитов компании через LLM (Pack 26.0); корзина с автоудалением через 7 дней (Pack 27.0); npd_candidate таблица + EgrulChecker + npd_pool.refill_pool_for_region + CLI refill_npd_pool (Pack 28 Часть 1, Часть 2 отложена — ФНС урезали NPD API, Инцидент 19).

## Сессия 09.05.2026 — Pack 30.0 — фикс 404 на «Подобрать опыт работы»

Pack 19.1a и 20.3 числились «работают», но endpoint забыли зарегистрировать → 5 дней 404 в проде. См. Инцидент 20.

## Сессия 10.05.2026 — Pack 33.x (10 пакетов)

- **33.0-33.6.2** — page-break перед «Адреса и реквизиты Сторон» через runtime postprocess, NBSP в long-form датах, honest 422, Position seed 21 specialty × Middle, починка per-company договоров, cleanup `.gitignore` + 22 stray файла

## Сессия 11.05.2026 — Pack 34.x (УТРО) + 35.x (ВЕЧЕР)

- **Pack 34.x** — каскад багов вокруг РЕНКОНС (wrap в выписке, в адресе договора, justify-растяжку, hard line break)
- **Pack 34.2** — кнопка «Готово к получению»
- **Pack 35.0-35.10** — bank statement NPD-фикс, passport_issuer_ru локализация + миграция, кнопка ✨ Сгенерировать, СБП-получатель, hotfix Pack 35.4 (Инцидент 31), разбиение шапки «город+дата» (Инцидент 33), копирование rPr + латинские инициалы в подписи

## Сессия 15-16.05.2026 — Pack 36.0/36.1 (PDF flatten + EX-17)

- **Pack 36.0** — `flatten_pdf_form()`, фикс рендера PDF AcroForm на iOS/Telegram preview, заменён `MI_T.pdf` на чистый (Инцидент 35, Правило 58)
- **Pack 36.1** — EX-17 TIE форма, новое поле `Application.fingerprint_date`

## Сессия 18.05.2026 — Pack 37.x — AI Document Audit (10 подпаков)

Симуляция приёма документов в консульстве через LLM. Менеджер собирает пакет 16+ документов → нажимает «🛂 Симуляция приёма» → ИИ-аудитор находит несоответствия → менеджер принимает/отклоняет/правит. Стоимость ~$0.17 за прогон, 30-200 сек.

Главные паки: **37.0-A/B/C/D** (БД, prompts, auditor, UI), **37.1** (DOCX export), **37.2/37.6/37.7/37.8** (sync work_history с БД), **37.3** (passport_expiry_date), **37.5** (ГОСТ-чек → info severity).

5 паттернов багов в собственных данных, выявленных самим аудитом, починены отдельными подпаками.

## Сессия 19-20.05.2026 — Pack 39.0 — Final Submission Audit (6 подпаков A-F)

Финальная проверка **физических документов** клиента перед подачей в консульство (в отличие от Pack 37.0 — проверяет реальные сканы, а не сгенерированные DOCX).

Главные паки: **39.0-A/A2** (БД, 3 таблицы, привязка к applicant_id), **39.0-B** (upload pipeline, дедуп SHA256, ZIP), **39.0-C** (extraction: pypdf+Vision, classifier Haiku-4-5), **39.0-D** (визовый инспектор Sonnet-4-5, 8 категорий A-H, ~80 правил), **39.0-E1/E2** (frontend drag&drop + findings UI), **39.0-F** (DOCX-экспорт отчёта).

Стоимость ~$0.10 за прогон, ~$15-25/мес на 50 заявок × 3 прогона.

## Сессия 20-21.05.2026 — Pack 40.x (autogen реквизитов заявки)

- **Pack 40.0-G** — автогенерация `outgoing_number` и `outgoing_date` для работодательского письма перенесена с API endpoint в `build_context()` в `context.py`. Если в `application` пусто — генерируется на лету: `max(employer_letter_number) + 1 / year`, дата = сегодня.

## Сессия 21-22.05.2026 — Pack 41.0 + Pack 42.x — multi-passport + UX-полировка

### Pack 41.0 A-G — мультипаспорты на applicant (главная фича)

Бизнес-задача: клиенту нужно показать в разных документах **разные паспорта** одновременно. Например иностранец получил новый паспорт — но договор подписан на старый (исторический документ). А выписка банка, испанские формы, апостиль — должны использовать новый (актуальный) паспорт.

| Pack | Что | Результат |
|---|---|---|
| **41.0-A** | Миграция БД: `applicant.passports JSONB` + `applicant.passport_id_for_ru_docs VARCHAR(36)`. 35 applicant'ов получили legacy_backfill записи | ✅ В проде |
| **41.0-B** | `backend/app/services/applicant_passports.py` — функции `normalize_number`, `make_passport_record`, `upsert_by_number`, `recompute_primary`, `get_primary`, `sync_primary_to_legacy_fields`, `reconcile_applicant_passports`. Скаляры `applicant.passport_*` остаются зеркалом primary. Поле `passport_id_for_ru_docs` на applicant. Расширён `_PATCHABLE_FIELDS` в `applicants.py` API | ✅ В проде |
| **41.0-C** | Бэкфилл `passport_type` + RU_INTERNAL эксклюзия из primary. `detect_passport_type` эвристика по nationality. OCR pipeline auto-добавление в `passports[]` через `upsert_by_number` в `import_package.py` | ✅ В проде |
| **41.0-D** | UI Drawer: новый компонент `PassportsSection.tsx` (~430 строк) с inline-редактированием, бейджами, dropdown «🇷🇺 Паспорт для договора», кнопкой «Использовать внутренний РФ», кнопкой «Резолв issuer_ru». Костя руками сделал 5 правок в `ApplicantDrawer.tsx` | ✅ В проде |
| **41.0-E + fix1/fix2/fix3_v2** | Русские DOCX-рендеры. Helper `get_passport_dict_for_ru_docs(applicant)` с 3-уровневым приоритетом. **Инцидент 42, Правило 64** | ✅ В проде |
| **41.0-G + fix1/fix2** | БИЗНЕС-ЛОГИКА ИЗМЕНЕНА: `passport_id_for_ru_docs` применяется ТОЛЬКО для договора. В `docx_renderer.py render_contract()` добавлен override блок. fix2 СРОЧНЫЙ — конвертация ISO-string в date через `date.fromisoformat()`. **Инцидент 43, Правило 65** | ✅ В проде |

**Логика после Pack 41.0-G:**
- **01_Договор.docx** → `passport_id_for_ru_docs` (выбранный менеджером, может быть устаревший)
- **Все остальные русские/испанские документы** → primary (свежий паспорт через скаляр-зеркало `applicant.passport_*`)

### Pack 41.0 H-Q (26.05.2026, вечер) — финал multi-passport + НПД-справка ИФНС + UX

Бизнес-задача №1: для **русских клиентов** с двумя паспортами (RU_INTERNAL + RU_FOREIGN) во всех русских документах (договор, акты, счета, выписка, письмо работодателя, CV, тех. заключение, командировка, трудовой договор, НПД-справка) должен подставляться **внутренний паспорт РФ**, а не загран. Раньше Pack 41.0-G делал это только для договора.

Бизнес-задача №2: для НПД-справки нужна правильная **ИФНС**. Раньше система определяла регион по `inn_kladr_code` (где выдан ИНН). Но клиент может иметь ИНН выданный в Калининграде (39), а проживать и стоять на учёте самозанятым в Москве (77) — справка показывала неправильную инспекцию. Решено двумя слоями:
1. **Auto-resolve** из `home_address` (Pack 41.0-L) — для типичных случаев
2. **Ручной override** через official сервис ФНС [service.nalog.ru/addrno.do](https://service.nalog.ru/addrno.do) (Pack 41.0-M/N) — для гарантированной точности

| Pack | Что | Результат |
|---|---|---|
| **41.0-H** | passport_id_for_ru_docs override блок в `render_bank_statement` (зеркало 41.0-G для выписки). UI dropdown переименован «Паспорт для договора» → «Паспорт для русских документов» | ✅ В проде |
| **41.0-I** | Сужение 41.0-H override: применяется ТОЛЬКО для `nationality=RUS` AND `passport_type=RU_INTERNAL`. Для иностранцев с 2 загранами выбор работает только для договора | ✅ В проде |
| **41.0-J** | Bugfix `hourly_rate_rub`/`hours_per_month` для компаний с `archetype=vozmezdnoe_hourly` (ООО КНС ГРУПП, Buki Vedi). Шаблоны использовали `contract.hourly_rate_rub` и `contract.hours_per_month`, но context не заполнял. Fix в `build_context`: `hours_per_month=160` (ТК РФ), `hourly_rate_rub = salary_rub / 160` | ✅ В проде |
| **41.0-K** | Централизация: override RUS+RU_INTERNAL перенесён в `build_context` (5 точечных замен). Покрывает ВСЕ 8 русских документов идущих через `build_context` (договор, акты, счета, employer_letter, CV, tech_opinion, business_trip, employment_contract, bank_statement) + НПД-справка через отдельный override в `context_npd_certificate.py`. Pack 41.0-H/I в `render_bank_statement` **откачен** (стал избыточным) | ✅ В проде |
| **41.0-L** | `_resolve_region_code` теперь сначала пытается извлечь регион из `home_address` (Tier 0): Москва (77), МО (50), СПб (78), ЛО (47), Краснодарский край (23 включая Сочи/Анапа/Новороссийск), Ростовская обл (61). Только если не найдено → старая логика (inn_kladr_code → inn[:2]). Plus seed: INSERT ИФНС № 29 по г. Москве (Раменки/Очаково/Солнцево/Внуково/Тропарёво-Никулино/Проспект Вернадского) в `ifns_office` Railway prod | ✅ В проде. Инна Лясковец получила правильную № 29 |
| **41.0-M** | Backend для ручного override ИФНС. Миграция: `applicant.npd_ifns_name VARCHAR(500) NULL`. SQLModel поле в `models/applicant.py`. Whitelist в `api/applicants.py`. Логика в `build_npd_certificate_context`: если `applicant.npd_ifns_name` непустой → используется в шаблоне НПД (full_name + short_name), иначе старая auto-resolve логика. Менеджер копирует точное название из официального сервиса ФНС | ✅ В проде |
| **41.0-N** | UI в `ApplicantDrawer.tsx`: useState `npd_ifns_name` + поле в payload PATCH. Под полем «Адрес проживания» — 2 кнопки: 📋 «Скопировать адрес» (clipboard API + alert) и 🔗 «Определить ИФНС в сервисе ФНС →» (target="_blank" на service.nalog.ru/addrno.do). После блока СНИЛС — текстовое поле «Название ИФНС для НПД-справки» с hint про workflow | ✅ В проде |
| **41.0-O** | UX-полировка: поле «Название ИФНС для НПД-справки» перенесено выше — сразу после `<NpdCheckBadge>`, перед `inn_registration_date`. Логически ближе к ИНН/НПД | ✅ В проде |
| **41.0-P** | UX: кнопка «📋 Скопировать адрес» — убран блокирующий `alert("Адрес скопирован")`. Заменён на inline-фидбек: useState `addressCopied` + setTimeout 2000ms. Кнопка на 2 сек становится зелёной с текстом «✓ Скопировано», потом возвращается. Fallback `alert()` остаётся только при ошибке clipboard API | ✅ В проде |
| **41.0-Q** | UX: блок `<PassportsSection>` обёрнут в `<div>` со стилями `<Section>` компонента (rounded-md p-4, --color-bg-secondary, 0.5px border). Без title (внутри PassportsSection уже свой заголовок «Паспорта» + кнопка «+ Добавить паспорт»). Блок больше не «висит в воздухе» | ✅ В проде |

**Финальная логика multi-passport (после Pack 41.0-K):**
- **Русские клиенты** (`nationality=RUS`) с выбранным внутренним паспортом (`passport_id_for_ru_docs` → `passport_type=RU_INTERNAL`) → **внутренний паспорт во ВСЕ русские документы** (договор + акты + счета + выписка + employer_letter + CV + tech_opinion + business_trip + employment_contract + НПД-справка)
- **Русские клиенты без выбора внутреннего** → primary паспорт во все документы
- **Иностранцы** (`nationality≠RUS`) → выбор `passport_id_for_ru_docs` работает ТОЛЬКО для договора (Pack 41.0-G, исторический документ), все остальные русские документы → primary
- **Испанские PDF формы** (MI-T, EX-17, designacion, compromiso, declaracion, mi_tie) → ВСЕГДА primary (не зависит от dropdown)
- **Апостиль** → не использует passport_* в шаблоне → не затрагивается

**Финальная логика НПД-справки ИФНС (после Pack 41.0-M):**
1. Если `applicant.npd_ifns_name` непустой → используется ручное название (приоритет, точно из сервиса ФНС)
2. Иначе → auto-resolve через `_resolve_region_code(applicant)`:
   - Tier 0 (Pack 41.0-L): извлечение региона из `home_address` (по keyword-таблице, длинные ключи раньше коротких)
   - Tier 1: `inn_kladr_code[:2]`
   - Tier 2: `inn[:2]`
3. Дальше `_pick_ifns(session, region_code)` через Tier A/B/C-prime/C (Pack 33.8)

### Pack 42.x — UX-полировка админки

| Pack | Что | Результат |
|---|---|---|
| **42.0** | Убран авто-статус «Документы готовы» после `render_package`. Менеджер сам выставляет статус через dropdown | ✅ В проде |
| **42.1** | Кнопка 🗑 «Удалить» документ клиента (БД + R2) с `window.confirm()` | ✅ В проде |
| **42.2** | Паспорта НЕ перезаписываются при загрузке (каждый паспорт = отдельная запись в `applicant_document`) | ✅ В проде |
| **42.3** | Drag-and-drop в секцию «Документы клиента»: бросил файлы → открывается ImportPackageDialog с pre-loaded файлами | ✅ В проде |

## Сессия 24.05.2026 — Pack 43.0 + 44.0 + 45.0 — Position editor с LLM-генерацией

Бизнес-задача: при добавлении новой должности менеджер раньше вручную писал 9-15 русских полей (обязанности, теги, описание, тех. заключение). Теперь — заполняет 4 обязательных поля и жмёт одну кнопку → LLM генерирует профиль за ~40 сек, менеджер только проверяет.

### Pack 43.0 — кнопка «✨ Сгенерировать испанский» в TechOpinionSection

Триггер: исходный документ Цацая (Position id=74 «Аналитик производственных процессов»). В испанской части документа `17_Техническое_заключение.docx` зияли дыры в §1, §2, §3, §4 — потому что у новой должности ES-поля пустые, а seed-должности (Алиев) были заполнены вручную через БД.

Решение — кнопка ✨ в `TechOpinionSection` (рядом с вкладками RU/ES) делает один LLM-вызов `Sonnet 4.6 → OpenRouter` и переводит 5 ES-полей сразу (`description_es`, `tools_es`, `steps_es`, `grounds_es`, `contract_clause_es`).

| Pack | Что | Результат |
|---|---|---|
| **43.0-A** | Backend: `backend/app/services/position_translator.py`, endpoint `POST /admin/positions/{id}/translate-spanish`. Pydantic-валидация выхода | ✅ В проде |
| **43.0-B** | Frontend: `translatePositionToSpanish()` в `api.ts`, кнопка ✨ + state + `handleTranslate` в `TechOpinionSection.tsx`, prop `positionId` пробросом из `PositionDrawer` | ✅ В проде |
| **fix1** | Идемпотентный маркер был слишком общий — apply-скрипт молча skip'нул 2 правки (endpoint + handleTranslate). **Инцидент 44, Правило 66** | ✅ Применено |
| **fix2** | `API_BASE` → `API_BASE_URL` (автодетект соседних fetch'ей) | ✅ Применено |
| **fix3** | Префикс `/api` в URL (все остальные fetch'и в api.ts его явно прописывают) | ✅ Применено |
| **fix4** | `Authorization: Bearer ${getToken()}` в headers | ✅ Применено |

Стоимость: ~$0.02-0.05 за прогон.

### Pack 44.0 — фикс `_short_latin_from_full` для русского порядка ФИО

Триггер: подпись директора в испанской части `17_Техническое_заключение.docx` Цацая выходила как `K. PETROVICH`, у Алиева как `V. Vadimovna`. Должно быть `K.P. KAYTUKTI` и `A.V. VASILEVSKAIA`.

Причина: функция `_short_latin_from_full()` в `context.py` строки 1452-1462 была написана для **западного порядка** имён («First Middle Last» → берётся инициал первого слова + последнее целиком). У вас в БД хранится **русский порядок** «Фамилия Имя Отчество» (`KAYTUKTI KONSTANTIN PETROVICH`). На выходе функция выдавала «инициал ИМЕНИ + ОТЧЕСТВО целиком», фамилия терялась.

Фикс — одна правка функции:
```python
def _short_latin_from_full(full_latin: str) -> str:
    parts = full_latin.strip().split()
    if not parts: return ""
    if len(parts) == 1: return parts[0].upper()
    last_name = parts[0]                                # фамилия — первая (русский порядок)
    given_names = parts[1:]                              # имя + отчество
    initials = ".".join(p[0] for p in given_names if p) + "."
    return f"{initials} {last_name.upper()}"             # → "K.P. KAYTUKTI"
```

Использовалось **только** в tech_opinion. После фикса все ранее сгенерированные `17_Техническое_заключение.docx` перерендерятся правильно.

### Pack 45.0 — кнопка «✨ Сгенерировать всё» в шапке PositionDrawer

Менеджер заполняет **4 обязательных** поля (title_ru, title_es, primary_specialty_id, level) → жмёт кнопку ✨ «Сгенерировать всё» в шапке Drawer → за ~30-50 сек один LLM-вызов (`max_tokens=6144`) генерирует **9 русских полей**: `duties`, `tags`, `profile_description`, `tech_opinion_description_ru`, `tech_opinion_tools_ru`, `tech_opinion_steps_ru`, `tech_opinion_grounds_ru`, `tech_opinion_contract_clause_ru`, `international_analog_ru`.

`title_ru_genitive` и `salary_rub_default` остаются менеджеру (язык/рыночная величина).

| Pack | Что | Результат |
|---|---|---|
| **45.0** | Backend: `services/position_generator.py` + endpoint `POST /admin/positions/generate-russian`. Frontend: `generatePositionRussian()` в `api.ts`, кнопка ✨ в шапке `PositionDrawer.tsx` (рядом с крестиком), `handleGenerateAll` + `canGenerateAll` + state `generatingAll` | ✅ В проде |

После «Сгенерировать всё» менеджер проверяет/правит русские, далее жмёт «✨ Сгенерировать испанский» (Pack 43.0 кнопка в TechOpinionSection). Workflow: 4 поля вручную → 30 сек RU → 30 сек ES → сохранить. Стоимость ~$0.05-0.08 за прогон.

### Pack 46.0 — Диплом для хурадо (PDF + LLM-генерация полей)

**Бизнес-задача:** клиент пока не прислал скан диплома, но менеджеру нужен **рабочий документ-аналог** для передачи присяжному переводчику (хурадо) в Испании — чтобы хурадо имел структурированный source для перевода и заверения апостилем реального диплома. Документ **НЕ гербовый**, без печатей, без герба — только текстовые поля в правильной раскладке как на титульном листе бланка Госзнака.

**Архитектурное отличие от других документов:** PDF собирается **с нуля через ReportLab** прямо в коде (координаты прописаны явно как `x, y, font, size`). НЕТ DOCX/PDF-шаблонного файла. Раскладка подбиралась 10 итераций по эталону Кости (Джабраи_ллы_диплом-12.pdf). Размер страницы 708.96 × 497.76 pt (landscape), две колонки.

**6 новых полей в JSONB `applicant.education[]`** (без миграции — JSONB принимает новые ключи):
- `diploma_number` (строка, «107724 0170246») — номер бланка Госзнака
- `registration_number` (строка, «2.10.3-13.1/423») — внутренний рег. номер ВУЗа
- `protocol_number` (строка, «1») — номер итогового заседания ГЭК
- `protocol_date` (ISO date, «2015-06-17») — дата заседания
- `issue_date` (ISO date, «2015-06-28») — дата выдачи диплома
- `signers` (массив `[{name, position}]`) — подписанты на бланке

**Не попадает в общий ZIP** — отдельная кнопка «📄 Скачать диплом» в разделе Образование. Открывается в новой вкладке через blob (так как PDF требует Authorization header — прямой `<a href>` не работает).

| Pack | Что | Результат |
|---|---|---|
| **46.0 / A** | Backend: `services/diploma_pdf_renderer.py` (ReportLab, координаты из эталона, шрифты Liberation Serif из `backend/app/fonts/`) + `services/diploma_field_generator.py` (Sonnet 4.6 — генерирует 6 полей в правильном формате конкретного ВУЗа, не реальные идентификаторы). `requirements.txt` +`reportlab>=4.0` | ✅ В проде |
| **46.0 / B** | 2 endpoint'а в `applicants.py`: `POST /admin/applicants/{id}/education/{idx}/generate-fields` (LLM, в БД не пишет) + `GET /admin/applicants/{id}/education/{idx}/diploma.pdf` (inline PDF с RFC 5987 для кириллического filename) | ✅ В проде |
| **46.0 / C** | Frontend: функции `generateDiplomaFields()` + `openDiplomaPdf()` в `api.ts`. В `ApplicantDrawer.tsx` блок `education.map((edu, i) => ...)` расширен подсекцией «📄 Диплом для хурадо»: 6 inputs (diploma_number, registration_number, protocol_number, protocol_date, issue_date, signers как textarea) + 2 кнопки ✨ Сгенерировать и 📄 Скачать диплом | ✅ В проде |
| **fix1** | После ✨ Сгенерировать — автосохранение в БД через `updateApplicant({education: next}) + onSaved()`. Без этого PDF читал старые данные из БД, не свежие из state. **Инцидент 47** | ✅ В проде |
| **fix2** | В системном промпте `protocol_number`: сужен диапазон с «1-30, чаще всего 1-10» до «1-3, чаще всего 1». На реальных дипломах указывается номер ИТОГОВОГО заседания ГЭК (о присвоении квалификации), а не номер защиты ВКР — это всегда 1-3 | ✅ В проде |

**Проблемы по пути:**
- **Инцидент 46** — `git add backend/app/services/diploma_*.py` молча не добавил файлы потому что их **физически не было на диске** (скрипт A упал на скачивании шрифтов до создания .py). PowerShell не падает на `git add несуществующий_файл`, поэтому коммит ушёл без сервисов → прод упал с `ModuleNotFoundError`. Hotfix — положил файлы вручную, повторный коммит. **Правило 69.**
- **Шрифты Liberation Serif** — скачивать в скрипте через `urllib.request` оказалось ненадёжно (GitHub отдаёт tar.gz архив, а не отдельные TTF). Финальный путь: Костя скачал архив вручную, распаковал в `backend/app/fonts/` (~1.5 МБ закоммичены).

Стоимость LLM ~$0.01-0.02 за прогон (короткий промпт, выход ~500 токенов).

## Сессия 24.05.2026 (поздний вечер) — Pack 47 серия (47.0–47.23) — Sber statement template + runtime PNG плашки ЭП

Бизнес-задача: до этой сессии генерация банковской выписки работала только для Альфа-банка (`bank_id=1`, BIK 044525593). Клиенты Сбербанка (`bank_id=2`, BIK 044525225) получали Альфа-шаблон, что было визуально некорректно. Нужен второй шаблон, выглядящий 1-в-1 с реальной выпиской Сбера.

### Архитектурные изменения

| Подсистема | До | После |
|---|---|---|
| Bank template resolution | Жёстко `bank_statement_template.docx` | `_resolve_bank_statement_template_path(bik)` switch'ит по BIK на правильный шаблон |
| Поле applicant в контексте | `applicant.bank_account` (без форматирования) | + `applicant.bank_account_formatted` (формат "XXXXX XXX X XXXX XXXXXXX" = 5-3-1-4-7) для Сбера через `_fmt_bank_account_groups` |
| Плашка ЭП в шаблоне | 4 вложенные таблицы (top-band, blue-header, cert-table, outer-frame) — попытка нарисовать всё в DOCX | Static PNG asset + runtime PIL overlay реквизитов сертификата |
| Фазы render_bank_statement | 1) docxtpl Jinja, 2) python-docx tx-row cloning | + 3) `_replace_ep_badge_marker` (runtime PNG), 4) `_ensure_paragraphs_at_tc_end` (OOXML compliance) |

### Главные паки (47.0–47.23)

| Pack | Что | Результат |
|---|---|---|
| **47.0** | `_resolve_bank_statement_template_path` switch по BIK; новый шаблон `bank_statement_template_044525225.docx` | ✅ |
| **47.2** | category поле + running_balance + Sber-formatter в context.py | ✅ |
| **47.3–47.14** | 12 итераций косметической полировки шаблона Сбера: borders, padding, spacing, ширины колонок, цвет ИТОГО, формат номера счёта, зелёная линия, пунктир под ФИО, header tx-таблицы | ✅ |
| **47.7** | `_fmt_bank_account_groups` helper + `bank_account_formatted` поле | ✅ |
| **47.9, 47.10** | `_strip_empty_paragraphs_before_tables` — убирает невидимые пустые параграфы которые python-docx ставит перед вложенными таблицами в ячейках | ✅ |
| **47.12** | line=10pt exact для ИТОГО, split header line через pBdr на параграфах (отказались — линии на разных высотах), dashed sz=2, зелёная линия sz=12 | ✅ |
| **47.13** | line height для ИТОГО, header tx-таблицы — bottom border на ячейке + trHeight=1100 exact + white right border для разрыва между колонками. Колонки tx [28,80,36,36] → [28,65,50,37] | ✅ |
| **47.14** | Колонка ДАТА с 28 → 38mm (чтобы "(МСК)" не переносилось). Финальная ширина [38, 55, 50, 37] = 180mm | ✅ |
| **47.15** | АРХИТЕКТУРНОЕ ИЗМЕНЕНИЕ: runtime PNG плашки ЭП. Новый модуль `backend/app/templates_engine/ep_badge_renderer.py`. В шаблоне плашка заменена на маркер `__EP_BADGE__`. ФАЗА 3 — `_replace_ep_badge_marker` заменяет на inline-картинку через `add_picture` | ⚠️ v1 промежуточный (PIL рисовал с нуля — шрифты на Linux Railway не совпадали с брендом Сбера) |
| **47.16** | v2 ep_badge_renderer: использует static PNG asset `templates/docx/sber_ep_card.png`, PIL дорисовывает только 4 строки реквизитов поверх в нижней пустой зоне | ✅ |
| **47.17–47.18** | Фикс дубликата `<pic:cNvPr id="0">` — python-docx ставит id=0 по умолчанию, что конфликтует с sber_logo в шапке. Pack 47.18 расширил: проходит по всему документу и заменяет ВСЕ id="0" на уникальные 1002, 1003, ... | ✅ |
| **47.19** | ФАЗА 4: `_ensure_paragraphs_at_tc_end` гарантирует что каждая `<w:tc>` заканчивается на `<w:p>`. OOXML schema требует это; Word без этого выдаёт "Обнаружено неоднозначное сопоставление ячеек". Проблема была в `cell_right` ("ИТОГО ПО ОПЕРАЦИЯМ") которая заканчивалась на `<w:tbl>` | ✅ |
| **47.16 (real)** | Catchup-коммит: ep_badge_renderer.py v2 + sber_ep_card.png реально попали в git. Pack 47.16 первоначально закоммитил только PNG (без .py файла) | ✅ |
| **47.20** | Финальная замена `sber_ep_card.png` на свежую (1134×537, белый фон изначально). Пересчитанные координаты overlay: LABEL_X=76, VALUE_X=347, START_Y=310, ROW_GAP=45, шрифт 24pt | ✅ |
| **47.21–47.23** | Финальная косметика: фикс отображения категорий tx, цвет лейблов, выравнивание totals блока | ✅ |

### Известные проблемы Pack 47 серии

**Серия багов с git add/commit** (см. Инцидент 47.A в §11):
- Pack 47.16 закоммитил только PNG без `ep_badge_renderer.py` (git silently skip когда apply скопировал v1 поверх v1)
- Потеряли 4 сессии (~1 час) на дебаге "почему плашка не обновляется"
- Решение: `git status` ПЕРЕД `git commit` обязателен (**Правило 69** + расширено в Pack 47 серии)

**Серия багов с OOXML валидностью** (см. Инцидент 47.B в §11):
- Pack 47.17 — Word ругался на дубликат `pic:cNvPr id="0"` (python-docx ставит 0 по умолчанию)
- Pack 47.19 — Word ругался на отсутствие `<w:p>` в конце `<w:tc>`
- Решение: после ЛЮБЫХ манипуляций с picture/table через python-docx прогонять через `_ensure_paragraphs_at_tc_end` и `_normalize_picture_ids` (**Правило 70**)

LibreOffice headless игнорирует ряд OOXML нарушений. Финальная проверка ВСЕГДА в Word (Правило 25).

## Сессия 25.05.2026 — Pack 48 серия (48.0 v2 – 48.4) — ТБанк statement template

Бизнес-задача: после закрытия Альфы (Pack 16) и Сбера (Pack 47) последний крупный российский банк который нужен в проде — ТБанк (АО «ТБанк», BIK 044525974, бывший Тинькофф). Большое количество клиентов агентства имеют ТБанк-счета, особенно фрилансеры и иностранцы. До Pack 48 ТБанк-клиенты получали Альфа-шаблон.

### Архитектурные особенности ТБанка относительно Альфы/Сбера

- **Format суммы tx:** `+574.00 ₽` / `-964.00 ₽` (знак ВСЕГДА, **точка** как десятичный разделитель, NBSP+₽).
- **Format итогов внизу:** `799 033,00 ₽` (БЕЗ знака, **запятая** как разделитель). Намеренная несовместимость стилей внутри одного банка — повторяем 1-в-1 как в эталоне.
- **tx-таблица 6 колонок:** дата+время операции / дата+время списания / сумма в валюте операции / сумма в валюте карты / описание / номер карты.
- **Дата+время** в первой/второй колонке — multiline ячейка `"DD.MM.YYYY\nHH:MM"` (две строки в одной ячейке через `_replace_marker_with_multiline`).
- **Номер карты** — 4 последние цифры; у нас в БД не хранится → генерируем детерминированно по `applicant.bank_account` через SHA1[:8] mod 10000.

### Главные паки (48.0 v2 – 48.4)

| Pack | Что | Результат |
|---|---|---|
| **48.0 (v2)** | `_TBANK_BIK`, `fmt_amount_tbank`, `fmt_amount_tbank_totals`, `_is_tbank_applicant`, `_generate_tbank_card_number`, `_apply_tbank_postprocess` в `context.py` + 3 новых маркера `__TX_DATE_SETTLE__`, `__TX_AMOUNT_CARD__`, `__TX_CARD__` в `docx_renderer.py`. Применяется в `build_context` после `_apply_sber_postprocess`. **Инцидент 48.A** — v1 упал на проде из-за SyntaxError (apply-скрипт писал escape-sequences вместо литералов). v2 использует `r'''...'''` raw-strings + CRLF-aware read/write + pre-write `py_compile` check (атомарный apply). | ✅ |
| **48.1** | TBank DOCX template + 2 PNG ассета: `bank_statement_template_044525974.docx` (122 KB), `tbank_signature.png` (84 KB, печать + подпись Е.С. Шадриной), `tbank_logo.png` (4 KB, жёлтый щит с T). Build-скрипт `build_tbank_template_v1.py` через python-docx. Resolver (`_resolve_bank_statement_template_path`) generic — не требует изменений | ✅ |
| **48.2** | TBank template v2 — **Jinja-условия для адаптации блока паспорта по гражданству**. Для `applicant.nationality == "RUS"`: 4-колоночный паспорт (Серия / Номер / Дата выдачи / Код подразделения) + 2 адреса (места жительства + регистрации). Для иностранцев: компактный паспорт (Номер + Дата выдачи в одну строку) + один "Адрес". Helper `_add_jinja_marker_paragraph` вставляет параграфы с `{%p if %}` / `{%p else %}` / `{%p endif %}`. 8 Jinja-маркеров сбалансированы (3 if, 3 endif, 2 else) | ✅ |
| **48.2.1** | Фикс 4 имён полей: `{{ passport_series }}` → `{{ applicant.passport_series }}`, аналогично для `passport_issue_date_str`, `passport_issuer`. Также `{{ bank.outgoing_number }}` → `{{ application.outgoing_number }}` (поле в `application` словаре, не в `bank`). Бонус: переключение `&quot;RUS&quot;` → `'RUS'` в Jinja-условиях (одинарные кавычки, надёжнее для docxtpl) | ✅ |
| **48.3.0** | Жирные линии между tx-строками. Точечная XML-правка `bank_statement_template_044525974.docx`. По замерам пикселей реальных линий в эталоне (RGB ~126-150 = #7E7E7E-#969696) заменены 12 bottom-границ внутри tx-таблицы (идентифицируется по маркеру `__TX_DATE__`): `sz=4 color=E5E5E5` → `sz=8 color=909090`. ТОЛЬКО внутри tx-таблицы | ✅ |
| **48.3.1** | Context enrichment в `context.py`: импорт `from datetime import date` → `from datetime import date, timedelta`. 2 новых helper'а: **`_generate_tbank_contract`** (детерминированно по `applicant.id` — дата заключения 18-24 мес. назад через SHA1, номер договора = 10 цифр); **`_generate_tbank_tx_times`** (детерминированно `(time_op, time_settle)`, op в диапазоне 06:00-23:30, settle = op + задержка по сумме: <1000₽ +1..15мин, <10000₽ +15..60мин, >=10000₽ +60..360мин). Расширение `_apply_tbank_postprocess`: шаги 5 (`bank["contract_date_formatted"]`, `bank["contract_number"]`) и 6 (`tx["date_formatted"]` → multiline, `tx["settle_date_formatted"]` аналогично) | ✅ |
| **48.4** | Header repeat + смена шрифта. Две правки XML: A) Добавлен `<w:tblHeader/>` в `<w:trPr>` первой строки tx-таблицы → заголовок повторяется на каждой новой странице. B) Замена шрифта **Arial → PT Sans** везде: 180 замен в `document.xml` (60 runs × 3 атрибута rFonts: ascii/hAnsi/cs), 2 в `styles.xml`, добавлен PT Sans entry в `fontTable.xml` | ✅ |

### Архитектурные правила Pack 48 серии

- **Apply-скрипты пишущие Python код**: ВСЕГДА `r'''...'''` raw-strings + pre-write `py_compile` + CRLF-aware (см. Pack 48.0 v2 template). **Правило 71**.
- **Sentinel design**: должен быть специфичен к post-apply состоянию, не пересекаться с pre-existing паттернами. Pack 48.0 v1 имел sentinel `_apply_tbank_postprocess(bank_data` — совпадал и с определением функции `def _apply_tbank_postprocess(bank_data, ...)`, и с вызовом → второй str_replace silent-skip'нулся, в результате на проде функция была добавлена но никогда не вызывалась. Pack 48.0 v2 sentinel — `bank_data = _apply_tbank_postprocess(bank_data,` (с `bank_data =` слева, специфично к вызову).

### Стоимость и метрики

- ТБанк шаблон: ~122kb DOCX + 84kb signature.png + 4kb logo.png
- Build-скрипт `build_tbank_template_v2.py` (~700 строк) детерминированный — повторный прогон даёт байт-в-байт идентичный document.xml

## Сессия 25.05.2026 (вечер) — Pack 49 серия (49.0 + 49.1) — Sber tblHeader repeat + footer IF-field

Бизнес-задача: сравнение нашей сгенерированной Сбер-выписки с эталоном (Ляшенко Инна Михайловна, 3 страницы) показало два косяка которые не были видны ранее:
1. **Шапка tx-таблицы** ("ДАТА ОПЕРАЦИИ (МСК) / КАТЕГОРИЯ / СУММА В ВАЛЮТЕ СЧЁТА / ОСТАТОК СРЕДСТВ" + подзаголовки) — повторяется на каждой странице в эталоне, у нас была только на странице 1.
2. **"Продолжение на следующей странице"** — в эталоне видна внизу каждой страницы кроме последней. У нас сидела как обычный параграф в теле документа сразу после tx-таблицы → попадала только на последнюю страницу (в обратном порядке от эталона).

### Главные паки

| Pack | Что | Результат |
|---|---|---|
| **49.0** | `<w:tblHeader/>` добавлен в существующий `<w:trPr>` первой строки tx-таблицы Сбера (внутрь `<w:trHeight w:val="1100" w:hRule="exact"/>` блока). Точечная XML-правка через `str_replace` на старом trPr → новом trPr с tblHeader перед trHeight. +25 байт XML. Та же логика что в Pack 48.4 для ТБанка | ✅ |
| **49.1** | Compound Word field в footer'е: `{ IF { PAGE } = { NUMPAGES } "" "Продолжение на следующей странице" }`. **Cached значения намеренно ПУСТЫЕ** — если Word/LibreOffice/Google Docs не пересчитают поля при открытии, пользователь увидит пусто (не литеральную фразу на всех страницах включая последнюю — это было бы хуже). Добавлен `<w:updateFields w:val="true"/>` в `settings.xml`. Создан `word/footer1.xml`, зарегистрирован в `<w:sectPr>` через `<w:footerReference>`. Параграф "Продолжение..." удалён из тела документа | ✅ |

### Поведение по платформам (компромисс варианта A)

| Платформа | Что увидит |
|---|---|
| Microsoft Word (Windows/Mac) | Стр.1..N-1: "Продолжение..." / Стр.N: пусто (~70-90% случаев) |
| LibreOffice | Везде пусто (но не сломано) |
| Google Docs | Скорее всего пусто (не сломано) |

Выбран осознанный компромисс: лучше пусто на всех страницах в части клиентов, чем литеральная фраза на ВСЕХ страницах включая последнюю в той же части.

### Pack 49.0 предохранитель

Сначала запушили Pack 49.0 (только tblHeader — безопасная правка, та же что в Pack 48.4 для ТБанка). После подтверждения что не сломалось — пуш Pack 49.1 (рискованный IF-field). Если 49.1 пришлось бы откатить — Pack 49.0 на проде остался бы как улучшение.

---

## Сессии 25-26.05.2026 — Pack 50.0 / 50.7 / 50.1 серия — Найм (NAIM/EMPLOYMENT) — линия трудового договора

⚠️ **Коллизия нумерации:** Pack 50.x в моём (Костином) Roadmap был зарезервирован под выписки ВТБ/Открытие. По факту в новых сессиях номер 50 ушёл на NAIM-линию (типизация заявок + трудовой договор + Т-9). Выписки переехали в Pack 51.x (см. Roadmap).

### Pack 50.0 — Типизация заявок Самозанятый/Найм

**Бизнес-задача:** до Pack 50.0 все заявки считались одного типа («самозанятый») — рендерился договор самозанятого + акты + счета. Появился клиент по трудовому договору — нужна развилка типов на уровне Application.

| Pack | Что | Результат |
|---|---|---|
| **50.0 / A-B** | Backend: `Application.application_type: SAMOZANYATYI \| EMPLOYMENT` (миграция + Pydantic). Default SAMOZANYATYI для обратной совместимости | ✅ В проде |
| **50.0 / C3** | Модалка выбора типа открывается **первой** при создании новой заявки на `/admin/applications/new` | ✅ В проде |
| **50.0 / C4** | Badge «НАЙМ» в шапке ApplicationDetail + кнопка «Сменить тип» с modal-подтверждением | ✅ В проде |
| **50.0 / C5** | `ImportPackageDialog` принимает `application_type` (импорт пакета с правильным типом) | ✅ В проде |

### Pack 50.7 — Приказ Т-9 о командировке

**Бизнес-задача:** для NAIM-заявок консульство требует приказ о направлении в командировку (Т-9) на бланке организации. Раньше не генерировался.

| Pack | Что | Результат |
|---|---|---|
| **50.7-A** | Поля `business_trip_start_date`, `business_trip_end_date`, `business_trip_destination` на Application | ✅ В проде |
| **50.7-B** | LLM-генератор `business_trip_purpose` (OpenRouter Sonnet) в `services/business_trip_generator.py` | ✅ В проде |
| **50.7-C** | Шаблон `templates/docx/orders/T-9_business_trip_template.docx` + `render_business_trip_order` + регистрация в pipeline. Фильтр: видна только при EMPLOYMENT | ✅ В проде |
| **50.7-C-prep** | `applicant.full_name_accusative` — миграция БД + LLM-автогенерация (для «направить в командировку **кого**») | ✅ В проде |
| **50.7-D** | UI поля Т-9: в ApplicantDrawer (full_name_accusative) + в Application/Company drawers (даты/назначение/цель) | ✅ В проде |
| **50.7-D2** | `business_trip_purpose` UI в PositionDrawer с кнопкой ✨ генерации через LLM | ✅ В проде |

### Pack 50.1 серия — Трудовой договор + per-company customization (финал серии — 26.05.2026)

**Бизнес-задача:** аналог `01_Договор.docx` для NAIM. Шаблон трудового договора, привязка к компании, шрифт, модалка выбора (как у самозанятых).

| Pack | Что | Результат |
|---|---|---|
| **50.1-A** | `company.ogrn VARCHAR(13)` + `company.email` (требуется в шапке трудового договора для ЭДО). Миграция + Pydantic + UI секция «Налоговые ID» (Pack 50.1-E) | ✅ В проде |
| **50.1-C** | `render_employment_contract` + шаблон `templates/docx/contracts/naim/by_company/factor_stroy/employment_contract_template.docx` + `employment_contracts_registry.py` (аналог Pack 29.0 contracts_registry но для NAIM). `NeedsEmploymentContractTemplateError` (409) | ✅ В проде |
| **50.1-F1+F3** | F1: фикс шаблона ФАКТОР СТРОЙ (плейсхолдеры city/date в правильном формате). F3: фильтр документов в `DocumentsGrid` — `naimOnly` / `selfEmployedOnly` карточки | ✅ В проде |
| **50.1-F2** | `applicant.snils VARCHAR(14)` (формат `XXX-XXX-XXX XX`) + UI поле + кнопка 🎲 генерации валидного СНИЛС (контрольная сумма: позиции 9..1 справа налево от 9 цифр, mod 101, если ≥100 → "00") | ✅ В проде |
| **50.1-F2-UX** | Кнопки 🎲 «Сгенерировать» переехали из отдельной строки **внутрь input** справа (absolute `right-1 top-1/2 -translate-y-1/2`). Затронуло ИНН, СНИЛС, дату выписки. Для textarea (Адрес проживания) кнопка осталась сверху | ✅ В проде |
| **50.1-H + fix1** | `company.contract_font_family VARCHAR(64)` + post-processor `_replace_fonts_in_docx(docx_bytes, font_name) -> bytes` (zip+regex по `<w:rFonts>`). Whitelist 4 шрифта: Times New Roman / Arial / Calibri / Microsoft Sans Serif. Применяется в `render_contract`. **fix1: `str.replace()` 3 раза с одним якорем добавил поле 3 раза в CompanyCreate вместо Create/Update/Read — см. Инцидент 49** | ✅ В проде |
| **50.1-G** | **Финал серии 50.1.** `company.employment_contract_template_slug` + `company.employment_contract_font_family`. Реестр расширен (приоритет slug → ИНН → None, helpers, **большой docstring «как добавить новый шаблон»** прямо в файле). `NeedsEmploymentContractTemplateError` теперь содержит `available_templates`. `ContractTemplatePickerModal` универсальная — `kind?: "contract" \| "employment"`. **CompanyDrawer**: единая секция «Шаблоны договоров» с табами `[Самозанятый][Найм]`, каждый таб = свой dropdown шаблона + свой dropdown шрифта | ✅ В проде |

**Серия Pack 50.1 закрыта** коммитом `0f3d684` от 26.05.2026.

**Архитектурные паттерны (важно для будущих сессий):**

1. **Реестр шаблонов трудового** (`employment_contracts_registry.py`) — структурно аналог `contracts_registry.py` (Pack 29.0) но без `default` (NAIM требует явный выбор):
   - `EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY: dict[slug, {label, path, description}]`
   - `EMPLOYMENT_COMPANY_INN_TO_SLUG: dict[ИНН, slug]` — fallback
   - `resolve_employment_contract_template_path(company)` — приоритет `employment_contract_template_slug` → ИНН → `None` (→ 409)
   - `get_available_employment_template_options()` — для UI dropdown, поле `archetype: "employment"`
   - `is_employment_template_slug_valid(slug)`
   - **1 шаблон сейчас:** factor_stroy (ИНН 7727286316)
   - **Как добавить новый шаблон:** см. inline-docstring файла (5 шагов: положить docx → запись в registry → опц. ИНН-маппинг → менеджер выбирает в модалке если нет ИНН → тест)

2. **Post-processor шрифтов** `_replace_fonts_in_docx` в `docx_renderer.py` (Pack 50.1-H/G):
   - Распаковывает docx (zip), читает `word/document.xml`
   - Regex заменяет `w:ascii|hAnsi|cs|eastAsia` в `<w:rFonts>` на новый шрифт
   - Whitelist 4 шрифта (fallback если не в whitelist → исходные байты)
   - Применяется в `render_contract` (через `company.contract_font_family`) и `render_employment_contract` (через `company.employment_contract_font_family`)

3. **Универсальная модалка** `ContractTemplatePickerModal` (`kind: "contract" | "employment"`):
   - kind переключает endpoint списка (`/contract-templates` vs `/employment-contract-templates`)
   - kind переключает поле company при сохранении (`contract_template_slug` vs `employment_contract_template_slug`)
   - Заголовок меняется автоматически
   - Используется и для модалки выбора при 409, и из CompanyDrawer

4. **Workflow apply-скриптов с симуляцией** (новое в этих сессиях):
   - Помимо Правил 34/66/71 — теперь **каждый apply-скрипт прогоняется на симуляции** в `/home/claude/work/prod_sim/` (зеркальная копия репо) перед отдачей пользователю
   - Это поймало баг Pack 50.1-H (str.replace × 3 с одним якорем добавил поле 3 раза в один класс) — см. Инцидент 49
   - Костя присылает дамп файлов через PowerShell-скрипт по запросу — Клод распаковывает в `repoXX/` через regex `^={20,}\nFILE: (.+?)\n={20,}\n`

### Известные капризы окружения (всплыли в этих сессиях)

- **Railway query interface** выполняет только **один запрос** за раз (если в SQL Editor 3 запроса подряд — покажет результат только последнего); не понимает `LIMIT N` в некоторых случаях (синтаксическая ошибка); может таймаутить агрегаты на больших таблицах
- **ФНС API `rmsp-pp.nalog.ru`** блокирует не-российские IP на уровне TLS handshake (DNS работает, HTTPS handshake разрывается). Если у Кости включён зарубежный VPN — Pool Filler накапливает `rejected_ip` в `npd_candidate`. Решение: выключить VPN или гонять refill через Railway backend (он в правильной геозоне)
- **Mojibake в `DocumentsGrid.tsx`** — битая кириллица в комментариях Pack 29.4. Артефакт старых правок, не влияет на работу, но мешает grep'ам по русским словам. Чистка отложена



## Сессия 28-29.05.2026 — Pack 50.12 – 50.31 — Найм: документы СФР + СТД-Р вёрстка + выписка найма

⚠️ **Эта сессия не была отражена в PROJECT_STATE до 29.05** — все паки ниже добавлены постфактум. Среда: docxtpl **доступен** в окружении Клода (pypi работает) → apply-скрипты тестировались рендером end-to-end, не только структурно.

### Блок A — документы найма (50.12 – 50.20)

| Pack | Что | Результат |
|---|---|---|
| **50.12-C (r4→r8)** | `soo_template.docx` (Свидетельство об отъезде, СОО) — итеративная доводка вёрстки: шапка 8pt + заголовки разделов 8pt + тело 10pt. Подход — таблицы (эталон Регины на textbox'ах) | ✅ В проде |
| **50.12-B-fix2** | СОО «Документ удостоверяющий личность» брал внутренний паспорт из RU_INTERNAL записи passports[] (был загран) | ✅ В проде |
| **50.13** | Перенос ОКТМО + Телефон из drawer заявки в карточку компании (поля okpo/oktmo/phone принадлежат модели company) | ✅ В проде |
| **50.14** | Дата приказа Т-9 (`business_trip_order_date`) = today−7 дней, фиксируется в БД при первой генерации | ✅ В проде |
| **50.15-A/B** | `applicant.phone_ru` (рус. телефон). A: миграция + модель + API whitelist + 3 места в context (`phone_ru or phone`). B: поле «Телефон (рус.)» в ApplicantDrawer. Русские документы → phone_ru, испанские PDF → phone | ✅ В проде |
| **50.16→50.17→50.18** | Конец командировки (`business_trip_end_date` авто). 50.17: `_bt_auto_end_date` = start+3года+6мес, обход выходных вперёд. 50.18 КЛЮЧЕВОЕ: в context.py ДВА независимых вычисления end_date — build_business_trip_context (Т-9) И build_soo_context (раздел 3 СОО, своя копия). Применено в обоих | ✅ В проде |
| **50.19** | Скрыть `13_Compromiso_RETA.pdf` для найма. A: builder.py (pdf_forms_engine) блок RETA обёрнут в `if application_type != EMPLOYMENT`. B: DocumentsGrid карточка compromiso `selfEmployedOnly` | ✅ В проде |
| **50.20** | Апостиль Минфина/СФР для найма (`25_Апостиль_СФР.docx`). Эталон `Апостиль_минфина_СФР.docx`. Файлы: build_apostille_sfr_template.py, context_apostille_sfr.py (опорная дата soo_date→приказ→today, +5-7 раб.дней seed=applicant.id, номер 77-NNNNN/26), apostille_sfr_renderer.py. Регистрация в 5 точках (__init__, rendering naimOnly, applications _DOWNLOAD, DocumentsGrid naimOnly). docxtpl. Применён v2 (якоря # Pack 50.12-D) | ✅ В проде |

### Блок B — ОКЗ-код для СТД-Р (50.21 – 50.22 + заполнение)

| Pack | Что | Результат |
|---|---|---|
| **50.21** | Поле «🔢 Код ОКЗ» в карточке должности (PositionDrawer, ручной ввод). Backend УЖЕ был готов (Pack 50.9-A: position.okz_code в модели + автоподстановка в build_stdr_context для DN-работы wh_index==0). Не хватало UI — 4 вставки (стейт, чтение, save, JSX) | ✅ В проде |
| **50.22** | ОКЗ-код в кнопку «Сгенерировать» (LLM). A: position_generator.py — okz_code в схему _GeneratedFields (Optional), 10-й пункт промпта (4-знач. код ОКЗ-2014 с примерами), в JSON-формат, в result. B: PositionDrawer handleGenerateAll +setOkzCode. positions.py не тронут (возвращает result напрямую) | ✅ К деплою |
| **Заполнение ОКЗ** | Скрипт `fill_okz.py` (DRY-RUN + --apply, только пустые okz_code). 68 кодов подобраны вручную по ОКЗ ОК 010-2014. ЗАПИСАНО в БД | ✅ Выполнено |

### Блок C — СТД-Р вёрстка под эталон Орлова (50.23 – 50.29)

Эталон успешной сдачи: `ЭТК_Орлов.docx`. Тестовая заявка #2026-0065 (Доценко). Шаблон `stdr_template.docx`: T0 (после 2019, 15 слотов table1_rows, кол.6=okz_code), T1 (до 2019, 8 слотов table2_rows), T2 подпись. STDR_CUTOFF=2020-01-01.

| Pack | Что | Результат |
|---|---|---|
| **50.23** | Разрыв страницы перед «до 31 декабря 2019» (page_break_before) + нумерация «Страница X из Y» в footer (поля PAGE/NUMPAGES). Патч шаблона | ✅ В проде (2809f11) |
| **50.24** | Рег.номер СФР работодателя с новой строки, без переноса по дефисам. Хелпер `_stdr_sfr_nbr` (дефисы → U+2011). 3 места company_with_sfr: пробел → `\n` (docxtpl сам в `<w:br/>`) | ✅ К деплою |
| **50.25** | Шрифт таблиц СТД-Р 5.5pt (как Орлов — решает переносы дат + заголовок «Наименование документа») + doc_name «Приказ»→«ПРИКАЗ» заглавными (context 2 места). Патч шаблона + context | ✅ К деплою |
| **50.26** | Центрирование всех ячеек данных (гориз.+верт.) + название компании ЗАГЛАВНЫМИ (`.upper()` в 3 местах, номер СФР не тронут, полное название). Патч шаблона + context | ✅ К деплою |
| **50.27** | Убрать пустые строки СТД-Р (документ заканчивается на последней записи). Row-loop docxtpl `{%tr%}` ОКАЗАЛСЯ НЕНАДЁЖЕН в 0.20.2 (ошибка «unknown tag endfor» при тегах в разных ячейках) — ОТКАЗ. Решение: ПОСТОБРАБОТКА. `_render` получил опц. `post_process` callback (как `_apply_page_break_before_requisites` в render_contract); хелпер `_stdr_strip_empty_rows(doc)` удаляет строки где все ячейки пустые (T0 с R4, T1 с R2); render_stdr передаёт его. **Финальная версия v3 — построчная вставка post_process (устойчива к пустым строкам между функциями)** | ✅ К деплою |
| **50.28** | Ширины колонок таблицы до-2019 (T1): было 4/67/14/14% (работодатель раздут), стало 2/33/33/33% как Орлов. Патч tblGrid + tcW каждой ячейки | ✅ К деплою |
| **50.29** | Воздух в шапке таблиц: отступы параграфов (space_before/after = 4pt) в строках заголовков (T0 R0-R2, T1 R0-R1). У Орлова воздух = отступы параграфов, НЕ фикс. высота строк | ✅ К деплою |

**Урок 50.26/50.27:** фиксированная высота строк 1320 раздула ПУСТЫЕ слоты → 5 пустых страниц. У Орлова высота НЕ задана (auto по содержимому), воздух — через отступы параграфов (50.29). После 50.27 (удаление пустых) высоту убрали, оставили auto.

### Блок D — Выписка для найма (50.30 – 50.31)

**Бизнес-задача:** у самозанятого выписка = «Оплата услуг по договору» + НПД 6% + комиссия. У найма другая логика: переводы от работодателя 2 раза/мес (аванс + зарплата) по трудовому договору, суммы за вычетом 13% НДФЛ, без НПД/комиссий. Эталон `Выписка_по_счету_Орлов.docx` (Сбер-формат, прошёл приём).

| Pack | Что | Результат |
|---|---|---|
| **50.30** | Ветка найма в `bank_statement_generator.py`. Хелпер `_split_salary_employment(gross)` → (аванс, зарплата): на_руки = оклад×0.87; аванс ≈40% округл. вниз до 10тыс; зарплата = остаток. Эталон 310000→269700→100000+169700. Параметр `is_employment` в generate_default_transactions. В цикле по месяцам: если найм → аванс (20-25 число тек. месяца) + зарплата (5-9 след. месяца) с формулировками «Аванс/Заработная плата за {месяц} {год}г. по Трудовому договору №{N} от {дата}» + `continue` (минуя KWIKPAY/НПД/комиссию). context.py передаёт `is_employment=(application_type==EMPLOYMENT)`. Самозанятый НЕ изменён | ✅ К деплою |
| **50.31** | Кнопка «Перегенерировать выписку» (api/bank_transactions.py `_generate_for_app`) — отдельный вызов generate_default_transactions, в 50.30 не попал → кнопка генерила как самозанятый. Добавлен `is_employment` тем же способом | ✅ К деплою |

### Отложенные задачи (ждут консультации Кости)

- **ОКЗ для прошлых работ в СТД-Р**: okz_auto подставляется ТОЛЬКО для текущей DN-работы (wh_index==0). Для прошлых работ пусто (нет привязки к Position). Вариант «оставить как есть» пока принят. Костя консультируется.
- **Двойная запись 2019/2020 в СТД-Р**: запись пересекающая 01.01.2020 целиком попадает в T0 (после 2019). Нужно ли авто-дублировать в обе таблицы — не решено, ждёт ответа.

### Капризы окружения / уроки этой сессии

- **docxtpl row-loop `{%tr%}` НЕНАДЁЖЕН** в версии 0.20.2 когда for/endfor разнесены по ячейкам строки (jinja «unknown tag endfor»). Альтернатива — постобработка python-docx после рендера (Pack 50.27).
- **docxtpl конвертирует `\n` в `<w:br/>`** автоматически (перенос строки в ячейке) — использовано в 50.24.
- **Частая ошибка деплоя:** Костя кладёт apply/build-скрипты и шаблоны в подпапки (`backend\`, `templates\docx\`) вместо КОРНЯ репо → «No such file» / git «did not match». Все apply/build/context/renderer .py + эталоны DOCX → в КОРЕНЬ `D:\VISA\visa_kit\`.
- **`.gitignore` блокирует `apply_*.py`** — их можно не коммитить (`git add -f` если нужно), коммитить только рабочие файлы.
- **PowerShell here-string `@'...'@`**: нельзя `\"` экранирование в f-строках — выносить в переменные и собирать через `+`. БД-запросы через `with engine.begin() as conn:`.
- **`Get-ChildItem -Filter` НЕ принимает массив** `"*a*","*b*"` — использовать `Where-Object {$_.Name -match "a|b"}`.
- **Якоря для регистрации новых документов** в проде: rendering.py / applications.py используют комментарий `# Pack 50.12-D` (НЕ -B). Между `_render` и `_render_from_repo_path` в docx_renderer.py НЕТ пустых строк (вплотную).

### Тестовая заявка #2026-0065 (Доценко Сергей, applicant.id=56)

Найм, КНС ГРУПП. order_date=2026-05-21, order_number=2/к. Паспорта: RU_INTERNAL 1822870736 (issuer ГУ МВД по Волгоградской обл, div 340-004), RU_FOREIGN 775551037. Телефон рус +79264444444. Зарплата 340000 ₽/мес. work_history: Корпоративные Стратегии (Младший бизнес-аналитик 2019-2021), Профит Групп (Бизнес-аналитик 2021-2025), КНС ГРУПП (текущая, Специалист по координации IT-проектами, okz 1213.9).

---

## Сессия 29-30.05.2026 — Pack 50.32 – 50.39 — СТД-Р правка юриста + перевод найма + ФИЧА «автозаполнение заявки из текста менеджера»

⚠️ Большая сессия. Среда: docxtpl **доступен** у Клода → apply-скрипты тестировались рендером/логикой end-to-end. Все паки ниже **в проде**.

### Блок A — СТД-Р двойная запись + правка юриста (50.32, 50.37)

| Pack | Что | Результат |
|---|---|---|
| **50.32** | СТД-Р: запись, пересекающая 01.01.2020, дублируется — ВЕРХНЯЯ таблица (после 2019) приём+увольнение, НИЖНЯЯ (до 2019) период start..31.12.2019. `build_stdr_context` в context.py | ✅ В проде |
| **50.37** | **Правка ЮРИСТА** (отменяет часть 50.32): в п.1 ОБЯЗАТЕЛЬНО первая строчка ПРИЁМ даже если приём в 2019; данные о приёме ДУБЛИРУЮТСЯ. Для компании пересекающей 2020 — ПОЛНОЕ дублирование: верхняя ПРИЁМ(реальная дата 2019)+УВОЛЬНЕНИЕ, нижняя период start..31.12.2019. В ветке пересечения вернул `_t1_priem()`. Тест Доценко Корп.Стратегии 01.01.2019-31.05.2021 ✓ | ✅ В проде |

### Блок B — Перевод найма: запрет остаточной кириллицы (50.36)

| Pack | Что | Результат |
|---|---|---|
| **50.36** | Фикс «DOTSENKO S.С.» (смешанная кириллица в транслит. инициалах). ПРИЧИНА: НЕ баг кода (`_short_latin_from_full`/`_initials_native` в context.py дают native кириллицей — это правильно), а ошибка LLM-переводчика-хурадо: транслитерировал Доценко→DOTSENKO, первый С→S, второй С оставил кириллицей (U+0421, визуально как C). Фикс — правило 1b в SYSTEM_PROMPT хурадо (`backend/app/services/translation/docx_translator.py`): транслитерировать ВСЕ буквы, ZERO Cyrillic, внимание похожим С/Р/О/А/Е/Н/К/М/Т/В/Х/У→S/R/O/A/E/N/K/M/T/V/KH/U + GOST-таблица + пример «Доценко С.С.»→«DOTSENKO S.S.». Общий промпт для найма И самозанятого | ✅ В проде |

### Блок C — ФИЧА: автозаполнение заявки из текста менеджера (50.38, серия A1-A3 + B + D)

**Бизнес:** менеджер в Telegram шлёт полуструктурированное сообщение → вставляется в диалог «Импорт пакета» рядом со сканами → LLM парсит текст, OCR сканы → **СКАН=ИСТИНА** при конфликте (текст заполняет только пустые после OCR поля) → создаётся/заполняется заявка с привязкой справочников. Тестовый кейс — Юсуф Ерул (турок, заявка #2026-0067).

**Фундамент «город подачи» (город подачи ≠ город проживания!):**

| Pack | Что | Результат |
|---|---|---|
| **50.38-A1** | Поля `application.submission_city VARCHAR(64) NULL` + `submission_province VARCHAR(64) NULL`. Миграция применена. Модель Application + ApplicationRead + ApplicationPatch (Pydantic в applications.py, не в models!) | ✅ В проде (d5975ec) |
| **50.38-A2** | Хелпер `backend/app/pdf_forms_engine/submission_location.py`: `submission_city_province(app, addr)` → если submission_city задан (город + провинция явная/авто Barcelona→Barcelona/Madrid→Madrid); иначе fallback addr.city. 6 PDF-форм: МЕСТО ПОДПИСИ берёт город подачи (render_mi_t FIR_PROV, render_mi_tie Provincia_4+Brigada, render_ex17 Textfield-55, render_designacion Texto36, render_compromiso city, render_declaracion city). Адрес ПРОЖИВАНИЯ (DEX_LOCAL/DEX_PROV) НЕ трогали. Старые заявки целы (fallback) | ✅ В проде (85eb13e) |
| **50.38-A3** | Фронт: api.ts (submission_city/province в ApplicationResponse), SubmissionDrawer (2 поля город+провинция, автоподстановка провинции, в payload patchApplication), SubmissionCard (показ `submission_city || address?.city`). ПРОВЕРЕНО Madrid→место подписи MI-T MADRID, адрес проживания BARCELONA остался | ✅ В проде |

**Парсер + резолвер + применение:**

| Pack | Что | Результат |
|---|---|---|
| **50.38-B** | `backend/app/services/manager_text/parser.py` — MANAGER_TEXT_PROMPT (English/nullable/строгий JSON; секции applicant{name latin/native, birth, sex H/M, nationality ISO3, birth_country/place, passport_number, father_name, mother_name, email, phone}/spain_address{raw,street,city}/company{name,inn}/position{title}/representative{full_name,nie}/submission{city,province}/diploma{status}/unrecognized[]). `parse_manager_text(text)` через client.complete_text. Эндпоинт POST `/admin/applications/parse-manager-text`. + `__init__.py` | ✅ В проде (2913b87) |
| **50.38-D1** | `reference_resolver.py` — fuzzy-поиск справочников (difflib SequenceMatcher, БЕЗ LLM, список динамически из БД, порог SIM_THRESHOLD=0.72). `_normalize` убирает орг-формы (ООО/SL/etc)/кавычки/регистр. resolve_company (short/full_ru/full_es), resolve_position (title_ru/es), resolve_representative (NIE точно если есть, иначе fuzzy по имени first+last в прямом/обратном порядке), resolve_spain_address. **Устойчив к транслитерации**: «RENKONS KHEVI INDASTRIS» → «Rekkons Khevi Indastris» score 0.96, мусор <0.25 | ✅ В проде (a2bde1c) |
| **50.38-D1-fix** | resolve_spain_address по **ЯДРУ** (улица+номер). ПРИЧИНА: полный адрес «Carrer de Llull, 185, Piso 5 puerta 2, 08005 Barcelona» давал по raw только 0.66 (мусор 0.54-0.65, всё ниже порога). ФИКС: `_addr_core(s)` убирает тип улицы (Carrer de/Calle), этаж/дверь (Piso/puerta), индекс (\d{5}), город → сравнивает ядра. «llull 185» vs label = 0.82, мусор <0.43. Тест: Юсуф→id10 (0.818), Balmes→id4 (1.0), несущ→None | ✅ В проде |
| **50.38-D3-1** | `apply_parsed.py`: `apply_parsed_to_application(session, application, parsed)` — applicant-поля ТОЛЬКО пустые (скан=истина, `_is_empty`); `_APPLICANT_FIELD_MAP` (father_name→father_name_latin, mother_name→mother_name_latin, phone→phone, passport_number→passport_number простое поле!); resolve company/position/representative/spain_address → привязка id, ненайденное → notes_lines; submission_city дефолт Barcelona+провинция авто; diploma «awaiting»→«Диплом — ожидание»; unrecognized→заметка; всё в internal_notes блоком «[Из текста менеджера]». + `determine_application_type(parsed)` («НАЙМ»/NAIM/EMPLOYMENT в _raw_text/unrecognized → EMPLOYMENT, иначе None=дефолт SELF_EMPLOYED) | ✅ В проде (2a7ae2e) |
| **50.38-D3-2** | Интеграция в `import_package.py` + эндпоинт дозакидывания. finalize_import принимает `manager_text` из body → парсит → определяет тип → создаёт заявку с типом → прокидывает `parsed_text` в фоновую задачу `_run_ocr_for_docs_batch(doc_ids, app_id, parsed_text=None)` → `_auto_apply_ocr_to_applicant(app_id, parsed_text=None)` применяет текст ПОСЛЕ OCR (скан=истина). Ранний выход «нет OCR docs» тоже применяет текст. Интеграция ТОЛЬКО в основной finalize (with-company/skip-company не тронуты — примут None). Эндпоинт POST `/admin/applications/{id}/apply-manager-text-existing` (дозакидывание в существующую). **УРОК ЯКОРЯ**: body/task-якоря неуникальны (3 finalize-эндпоинта) — body привязан к хвосту «files_info + # === Этап 1: ищем EGRYL ===», task к «# === OCR в фоне (после возврата ответа клиенту) ===» (у with/skip короткий «# OCR в фоне») | ✅ В проде (c7dd49e) |
| **50.38-D4** | Фронт: api.ts (manager_text? в body-типах finalize), ImportPackageDialog (state managerText + textarea «Сообщение от менеджера» на шаге классификации рядом с полем имени клиента, для target=new; проброс props в ClassifyStep; manager_text в 3 finalize-вызова target=new). **NB: поле НЕ на первом экране загрузки (UploadStep с clientName), а на шаге классификации** (после загрузки файлов, ClassifyStep с internalNotes) — Костя путался | ✅ В проде |
| **50.38-D-fix** | Заголовок заявки `ApplicationDetail.tsx`. ПРИЧИНА: для иностранца native=«—» (placeholder, у турка нет кириллич. имени), latin=«ERUL YUSUF». Старый `isPlaceholderApplicant` считался ТОЛЬКО по native → заголовок брал internal_notes (заметки!) вместо имени, latin блокировался. ФИКС: placeholder = когда И native И latin пустые/«—» (`_nativeIsPlaceholder && !_latinValid`); fullNameLatin до fullNameRu; порядок native→latin→notes→«Без имени». Тест 4 сценария ✓. **УРОК ЯКОРЯ**: пустая строка между блоками isPlaceholderApplicant и fullNameRu — без неё якорь промахивался | ✅ В проде |

**D2 (снятие валидации дроверов) ПРОПУЩЕН** — вся блокирующая валидация на ФРОНТЕ (CompanyContractDrawer required Компания+Должность; SubmissionDrawer representative+address). Бэкенд PATCH НЕ блокирует частичное (только проверяет существование переданных FK). Автозаполнение через бэкенд обходит фронтовую валидацию → D2 не нужен.

### Блок D — Pack 50.39 — город подписания из юр.адреса компании

| Pack | Что | Результат |
|---|---|---|
| **50.39** | Автоподстановка «Города подписания» (`contract_sign_city`) из `legal_address` компании при редактировании CompanyContractDrawer, если поле пустое. Хелпер `extractCityFromLegalAddress()` (module-level): убирает индекс \d{6}, split по запятым, ищет «г. XXX»/«город XXX» → город БЕЗ «г.». useEffect на [companyId]: если selectedCompany и contractCity пустой → подставить. Тест: «121108, г. Москва, ...»→«Москва», «г.Сочи»→«Сочи», «обл. Волгоградская, г. Волгоград»→«Волгоград». Менеджер может переопределить | ✅ В проде |

### Решения Кости по раскладке текста менеджера
- Имена родителей → father_name_latin/mother_name_latin (НЕ father_name). Телефон испанский → phone. Паспорт → passport_number (простое поле, только пустое).
- Компания/должность/представитель/адрес → справочники по fuzzy (difflib, без LLM, динамически из БД — новые записи автоматом, промпт переписывать НЕ надо). **Менеджер НЕ пишет NIE** — представитель ищется по ИМЕНИ (NIE только бонус если есть). Менеджер может ошибиться в транслитерации (RENKONS vs Rekkons) — fuzzy справляется.
- Не нашли в справочнике → заметка «добавить вручную». Диплом «жду»/unrecognized → заметка.
- submission.city не указан → дефолт Barcelona (провинция Barcelona авто). НАЙМ в тексте→EMPLOYMENT, иначе дефолт SELF_EMPLOYED.

### Тестовая заявка #2026-0067 (ERUL YUSUF, applicant.id=58) — фича сработала
Турок-самозанятый. Парсер+резолвер привязали: компания РЕНКОНС ХЭВИ ИНДАСТРИС id=18 (fuzzy нашёл RENKONS→Rekkons!), должность «Аналитик производственных процессов» id=74 (spec=6 Строительство, lvl=3), представитель ANNA TELEPNEVA id=3, паспорт U259983066 TUR, ДР 20.06.2001 BATMAN, гражданство Турция, контакты, родители MEHMET ALI/CANAN, submission Barcelona, адрес Llull 185 id=10 (после D1-fix). last/first_name_latin=ERUL/YUSUF; native=«—» (placeholder — у иностранца нет кириллич. имени, ПРАВИЛЬНО). Тип SELF_EMPLOYED (в тексте не было НАЙМ).

### Капризы окружения / уроки этой сессии
- **fuzzy difflib SequenceMatcher** для справочников: нормализация (убрать орг-форму/кавычки/регистр) + порог 0.72 уверенно отделяет совпадение (0.9+) от мусора (<0.4). Список из БД динамически — добавление записей не требует правок кода/промпта.
- **Адрес — сравнивать по ЯДРУ** (улица+номер), отбросив тип улицы/этаж/индекс/город. По полной строке похожесть размывается.
- **Скан=истина**: текст менеджера применяется ПОСЛЕ OCR, заполняет только пустые поля applicant.
- **Заголовок иностранца**: native=«—» НЕ делает запись placeholder, если latin валиден. Заголовок никогда не должен показывать internal_notes при наличии имени.
- **base64 для встраивания py** в apply-скрипт (parser/resolver/apply_parsed) — избегает экранирования тройных кавычек/юникода: `base64.b64encode`→строки по 100→в скрипте `b64decode().decode()`.
- **Уникальные якоря** в файлах с повторяющимися блоками (3 finalize-эндпоинта, повторяющиеся `internal_notes` строки) — расширять уникальным хвостом/комментарием. Смотреть raw через PowerShell `"{0}|{1}|" -f ($i+1), $lines[$i]` (видит пустые строки/trailing-пробелы, которые ломают якорь).
- **Генерация опыта работы** (work_history_generator) берёт specialty из `applicant.education[-1]` — при отсутствии диплома фолбэк даёт неверную должность («Бизнес-аналитик» spec=16). С заполненным дипломом работает корректно. Возможный будущий фикс — брать specialty из должности заявки (position.primary_specialty_id) при отсутствии образования. ОТЛОЖЕНО (Костя проверил — с дипломом ок).

### Отложенные задачи
- **D4-2 — кнопка дозакидывания текста в существующую заявку через UI**: бэкенд-эндпоинт `/admin/applications/{id}/apply-manager-text-existing` готов (D3-2), нужна только кнопка/модалка во фронте. Вторичный сценарий.
- **Текстовое поле менеджера на ПЕРВОМ экране** (сейчас на шаге классификации) — перенести в UploadStep, если Косте удобнее. Не критично.
- **Очистка untracked-мусора** в КОРНЕ (десятки build_*.py, *_template_v*.docx, inspect_*.py, _check_*.py, NAIM_ANALYSIS.md). ВАЖНО: среди untracked — `apostille_sfr_renderer.py`, `context_apostille_sfr.py`, `build_apostille_sfr_template.py` (рабочие файлы апостиля СФР Pack 50.20) — проверить, закоммичены ли (апостиль в проде, но файлы в untracked).
- **work_history_generator fallback на должность заявки** (см. уроки выше).

## Сессия 03.06.2026 — Pack 50.40 (разбег номеров) + Pack 50.41 (подсветка непросмотренных)

**Pack 50.40 — разбег реестровых номеров по дате выдачи.** Раньше номера шли почти подряд: КНД 1122035 = `106_800_000 + applicant_id*7 + issued_date.toordinal()%100` (между соседними заявками ~7, от даты почти не зависит), апостили НПД и СФР = `randint(3000,4500)` от `applicant_id` (кучковались, от даты не зависели). Сделан единый детерминированный генератор `backend/app/templates_engine/_doc_numbering.py`: `compute_doc_number(ref_date, step, base, seed)` — растёт ~step за РАБОЧИЙ день от эпохи `NUM_EPOCH=2026-01-01`, СТРОГО монотонен по дате (джиттер из SHA1 < step/2 → прирост между соседними раб.днями в (step/2..3*step/2)), детерминирован по seed. КНД 1122035: step=500, base=106_800_000, ref=issued_date (`context_npd_certificate.py`). Апостиль НПД (`context_apostille.py`) и СФР (`context_apostille_sfr.py`): step=350, base=3000, ref=apostille_date, NNNNN остаётся 5-значным весь 2026 (~макс 77-90000/26). Apply: `apply_pack50_40_doc_numbering.py` (Правило 71 + Инцидент 49). Миграций НЕ требует.

**Pack 50.41 — подсветка непросмотренных документов (общее на команду).** Менеджер видит, что ещё не открывал/не скачивал. Подсвечен = не просмотрен; снятие при open(preview)/download/ZIP; ручной toggle по кликабельной точке (вернуть «новый», если открыл по ошибке). Scope: сетки сгенерированных (`DocumentsGrid.tsx`, ключ = doc.id) + сканы клиента (`AdminClientDocuments.tsx`, ключ = `scan:{id}`). Final Submission НЕ затронут.
- Хранилище: таблица `document_view_state(application_id, doc_key, seen_at, seen_by)`, UNIQUE(application_id, doc_key), ON DELETE CASCADE на application. Создаётся `migrate_pack50_41_doc_view_state.py` (свой engine из `$env:DATABASE_URL` + защита от «задвоенного» URL).
- Бэкенд: 3 эндпоинта в СУЩЕСТВУЮЩЕМ роутере `/admin/applications` (`client_documents_admin.py`, raw SQL, без новых роутеров и правок main.py): `GET …/doc-view-state`, `POST …/seen`, `POST …/unseen`.
- Фронт: `api.ts` (+`getDocViewState`/`markDocsSeen`/`markDocsUnseen`), точка-индикатор + авто-снятие на скачивании/ZIP/открытии + toggle. Apply: `apply_pack50_41_seen_state.py`.
- **Pack 50.41-fix1** — синяя (акцентная) рамка у непросмотренных в сетке (как у сканов), ширина рамки одинаковая в обоих состояниях (без сдвига layout). `apply_pack50_41_fix1_grid_border.py`.
- **Известный нюанс (ОТЛОЖЕНО по решению Кости):** в сетке точка-toggle сидит ВНУТРИ кнопки скачивания → клик по точке иногда воспринимается как скачивание. Фикс = вынести точку в обёртку-сиблинг (НЕ сделано).

---

## Сессия 09-10.06.2026 — Pack 51 (append-выписка) + Pack 52 серия (Ч/Б Альфа v2 + PDF + позиционирование печатей)

⚠️ **Коллизия нумерации:** Pack 51 в Roadmap был зарезервирован под выписки ВТБ/Открытие. По факту номер 51 ушёл на append-mode выписки, а 52 — на Ч/Б шаблон Альфы v2. ВТБ/Открытие переехали в Pack 53.x.

### Pack 51 — Append-режим банковской выписки (бэкграунд)

Менеджер мог дополнять/редактировать выписку без полной перегенерации (append rows к существующему DOCX). Развёрнуто в проде. **Pack 51-fix1** — убран UI-gate (кнопка показывалась не всегда).

### Pack 52 — Чёрно-белый шаблон Альфы v2 + DOCX→PDF + позиционирование подписи/печатей

**Бизнес-задача:** для заявки Хайдарова Зафаржона (#89, 2026-0089) требовалась Альфа-выписка в Ч/Б стилистике (как у эталона консульства) + PDF (а не DOCX) с подписью банковского сотрудника (Агеева К.В.) и двумя печатями (прямоугольная «Заместитель управляющего ДО Бульвар Дмитрия Донского» + круглая «Альфа-Банк»).

#### Архитектурные изменения

| Компонент | Что | Pack |
|---|---|---|
| `Application.bank_template_legacy_v1: bool = False` | флаг переключения v1 (старый цветной)/v2 (новый Ч/Б). Default v2 для новых заявок. Миграция применена | 52 base |
| `render_bank_statement_to_pdf()` в `docx_renderer.py` | DOCX рендер → tempfile → `soffice --headless --convert-to pdf` → байты PDF. Эндпоинты `applications.py`/`render_endpoints.py` проверяют флаг, возвращают `10_Выписка.pdf` (а не .docx) | 52 base |
| **Dockerfile** в корне репо (не nixpacks.toml) | `libreoffice` + `libreoffice-writer` + `fonts-dejavu` + `fonts-liberation` + `unrar-free` | 52-fix2 |
| **TEMPLATES_DIR** | финально `repo/templates/docx/` (НЕ `backend/templates/docx/`). v2-файлы лежат в `templates/docx/bank_statement_template_v2.docx` + `templates/docx/assets/v2/{signature,stamp_employee,stamp_bank}.png` | 52-fix3 |
| `DocumentsGrid.tsx` | fetch `/api/admin/applications/{id}` → `bankIsV2` state → swap filename `bank_statement.docx` → `.pdf` для отображения. Kind остаётся `"docx"` для группировки. Иконка PDF по расширению | 52-fix3 |
| `templates/docx/bank_statement_template_v2.docx` (НОВЫЙ) | Ч/Б шаблон Альфы. tblGrid сигнатур-таблицы: C0=2500 C1=2000 C2=4000 C3=2448 (специально широкая C2 под inline-печать ДО). R1 gridSpan=2/2 (4500/6448 dxa, лейбл «(должность, Ф.И.О....» влезает на одну строку). vAlign=BOTTOM на R0C0/R0C2/R0C3. Убрана декоративная картинка image6.png из R1C3 (артефакт v1) | 52-fix3 |
| `templates/docx/assets/v2/signature.png` | Подпись Агеевой, обрезана от прозрачных полей 79px (cropped 914×587) | 52-fix3 |
| `templates/docx/assets/v2/stamp_employee.png` | Прямоугольный штамп ДО, очищен через numpy от серых артефактов сканирования (только синий: `(B>R+15) & (B>G+5) & (A>50)`, ~563×240) | 52-fix3 |
| `templates/docx/assets/v2/stamp_bank.png` | Круглая печать «Альфа-Банк» 451×451 (без обработки) | 52-fix3 |

#### Главная драма: позиционирование 3 PNG через floating anchors

Шаблон содержит 3 текстовых маркера в строке 0 таблицы подписей: `__STAMP_SIGNATURE__` (R0C0), `__STAMP_EMPLOYEE__` (R0C2), `__STAMP_BANK__` (R0C3). Функция `_insert_v2_signature_images(doc)` в `docx_renderer.py` находит маркеры и заменяет на картинки.

**Эталон** (организация-аналог): подпись и круглая печать **пересекают линию подписей** (часть выше, часть ниже), прямоугольная сидит **полностью над линией**.

Inline-картинка садится своим нижним краем на линию (если vAlign=BOTTOM) — это идеально для **прямоугольного штампа**, но **не позволяет подписи пересекать линию** (для пересечения нужно чтобы низ картинки был НИЖЕ линии — невозможно с inline в строке без bottom-overflow).

**Решение:** floating anchor через `<wp:anchor>` с `relativeFrom="column"` для X и `relativeFrom="paragraph"` для Y, `layoutInCell="0"`, `wrapNone`. Helper `_add_floating_picture(paragraph, png_path, width_mm, x_offset_mm, y_offset_mm)` создаёт anchor XML и заменяет inline-врапинг.

**Главный косяк всей сессии (между fix4 и fix17):** в моём локальном LibreOffice превью floating-anchor **клипуется** на границе строки таблицы — y_off=-33mm и y_off=-214mm рендерятся **идентично** (упираются в потолок). Я решил что прод тоже клипует и стал увеличивать отрицательные Y. **На проде LibreOffice клипа НЕ ДЕЛАЕТ** — y_off=-33 буквально поднял подпись на 33мм выше своего маркера, y_off=-214 — на 214мм (=в верх страницы поверх шапки). Открылось только после первого реального деплоя на реальной выписке с транзакциями.

**Pack 52-fix17 — пивот архитектуры:** все 3 картинки якорятся к **одному параграфу** — параграфу маркера `__STAMP_EMPLOYEE__` в R0C2. Прямоугольная сидит inline (= ровно на линии благодаря vAlign=BOTTOM ячейки). Подпись и круглая печать floating, anchor = тот же параграф R0C2, с маленькими y_off. Маркеры `__STAMP_SIGNATURE__` (R0C0) и `__STAMP_BANK__` (R0C3) просто чистятся (пустые параграфы).

#### Финальные координаты (после fix17→fix22)

| Печать | Тип | x_off (column) | y_off (paragraph) | Размер |
|---|---|---|---|---|
| signature | floating | **−60** (column R0C2 ≈79мм → ~19мм от лев.края = слева) | **+2** (чуть ниже линии, пересекает её низом) | 38мм |
| employee | INLINE | — (paragraph alignment right в шаблоне → справа в ячейке C2) | — (vAlign=BOTTOM ячейки → низом на линию) | 55мм |
| bank | floating | **+80** (column R0C2 +80 = ~159мм = справа) | **−5** (чуть выше линии, пересекает её верхом) | 35мм |

#### Хронология fix-итераций Pack 52 (для будущих археологов)

- **52 base** → 52-fix3: путь templates/docx, libreoffice в Dockerfile, frontend swap. **Развёрнуто в прод.**
- **52-fix4..fix15** → 52-final (консолидация): R1 gridSpan фикс лейбла на одну строку + R0C2 column widths + iterative подгонка позиций. **Развёрнуто одним коммитом** как Pack 52-final.
- **52-final** на проде с реальной выпиской показал что floating-anchors улетают вверх (200мм). Прямоугольная (inline) — на месте.
- **52-fix17** — пивот: якорь всех 3 в R0C2 paragraph, маленькие y_off, чистка других маркеров.
- **52-fix18..fix22** — подгонка y_off подписи по визуальному сравнению с реальной выпиской (опускали/поднимали на 1-6мм за итерацию): −5 → +10 (мимо вниз) → −2 (мимо вверх) → +4 → +1 → +2 (✅).

#### Ключевые принципы (для будущих сессий с floating anchors в docx)

1. **Локальный LibreOffice (мой sandbox) и прод-LibreOffice (Railway/Linux) рендерят floating-anchors ПО-РАЗНОМУ.** Не доверять локальному превью для проверки финальной позиции. Прод = единственный source of truth.
2. **Якорить floating к параграфу со ВСТАВЛЕННОЙ INLINE-картинкой** (если такая есть): её параграф находится в детерминированной Y-позиции (vAlign=BOTTOM → на линии), что даёт стабильную точку отсчёта для других floating'ов.
3. **`relativeFrom="paragraph"` для Y + paragraph внутри table cell** — Y отсчитывается от **верха параграфа**. Inline-картинка с vAlign=BOTTOM делает paragraph_top ≈ row_top (paragraph short, cell tall = aligned bottom). Это работает.
4. **`relativeFrom="column"` для X внутри table cell** — `column` = колонка ячейки таблицы (не section column). x_off отсчитывается от **левой границы ячейки**. Отрицательный x_off → влево от ячейки, картинка выходит за её пределы (нужен `layoutInCell="0"`).
5. **`<wp:anchor layoutInCell="0">`** — обязательно для floating'ов в таблице, иначе картинка клипуется ячейкой.

См. также: **Правило 72** (apply-скрипты с большими функциями: sentinel-replace всей функции + helper) и **Инцидент 50** (Pack 52-fix4..fix15: local-vs-prod LibreOffice mismatch).

---

## Сессия 10.06.2026 (вечер + поздний вечер) — Pack 53 (перевод выписки RU→ES, combined PDF) + Pack 54 (Sber v2) — BOTH DEPLOYED

### Pack 53 — Перевод банковской выписки на испанский (DEPLOYED)

**Бизнес-задача:** менеджер открывает дровер клиента, жмёт «✨ Перевести выписку» → backend переводит выписку на испанский через LLM → к существующему `10_Выписка.pdf` (стр 1-2 русская с печатями) добавляются стр 3-4 испанская версия БЕЗ печатей (только лейблы «(firma del empleado AO «ALFA-BANK»)» переведены).

**Архитектурные изменения:**

| Компонент | Что |
|---|---|
| `Application.bank_statement_translation_storage_key: Optional[str]` | R2-ключ сохранённого перевода. NULL = не делался; не-NULL = combined PDF при скачивании. Миграция: `migrate_pack53_translation_storage.py` (ALTER TABLE ADD COLUMN VARCHAR(255)) |
| `_insert_v2_signature_images(doc, *, mode="full"\|"markers_only")` | kwarg mode: full = вставить 3 PNG (текущее поведение), markers_only = только чистим маркеры __STAMP_*__ (для перевода — лейблы R1 переводятся в испанский, PNG не вставляются) |
| `render_bank_statement(app, sess, *, for_translation=False)` | kwarg для пропуска вставки PNG-печатей при подготовке к переводу |
| `render_bank_statement_for_translation(app, sess)` | wrapper над render_bank_statement(for_translation=True) |
| `render_bank_statement_combined_to_pdf(app, sess, es_docx_bytes)` | RU PDF (через soffice) + ES DOCX → PDF (через soffice) → pypdf merge → combined PDF bytes |
| POST `/admin/applications/{id}/bank-statement/translate` (async) | render_for_translation → translate_docx → R2 save → Application.translation_storage_key = key (~30-60 сек, ~$0.05) |
| GET `/admin/applications/{id}/download-file/bank_statement` (modified) | если translation_storage_key есть → combined PDF (RU+ES); иначе → RU PDF (текущее поведение Pack 52) |
| Frontend `translateBankStatement(appId)` в `frontend/lib/api.ts` | POST + ждёт ~60 сек на одном fetch (без polling) |
| Frontend кнопка «✨ Перевести» / «⏳ Переводится...» / «✅ Готово» в `ApplicantDrawer.tsx` | секция «Банковская выписка», под блоком «Дополнить период»; видна только для v2-выписок (`isV2Bank = !bank_template_legacy_v1`); состояние «Готово» сбрасывается через 5 сек; confirm-dialog при повторе |

**Файлы развёртывания (в `/mnt/user-data/outputs/`):**
- `migrate_pack53_translation_storage.py` — миграция БД (запускается один раз, идемпотентна)
- `apply_pack53_0_backend.py` — изменения в model + docx_renderer + applications.py
- `apply_pack53_1_frontend.py` — изменения в api.ts + ApplicantDrawer.tsx

**Деплой**: миграция → apply backend → push → Railway deploy → apply frontend → push → Vercel deploy. Без инцидентов.

### Pack 54 — Sber v2 (Ч/Б Сбер шаблон + Кирьянов + круглая печать + перевод RU→ES) [FULLY DEPLOYED]

**Бизнес-задача:** аналог Pack 52 (Альфа v2) для Сбербанка. Тестовая заявка #83. PNG ассеты от пользователя: подпись Кирьянова Е.В. (988×555 после обрезки прозрачных полей) + круглая печать «ПАО Сбербанк г. Москва» (400×400).

**Финальная архитектура** (после серии fix1..fix10):

| Компонент | Что |
|---|---|
| `bank_statement_template_044525225_v2.docx` | Скопирован из v1, изменено: image1.png (СБЕР logo) → grayscale (через fix4 текстовая замена `#21A038 → #1A1A1A` в document.xml для зелёного «ИТОГО ПО ОПЕРАЦИЯМ»), Table[3] полностью пересобрана — 4 колонки × 5 строк. **Размеры колонок: 2400/2700/2900/2204 dxa** (= 42/48/51/39 мм при content width 180мм). Геометрия: C0 = 0-42мм, C1 = 42-90мм, C2 = 90-141мм, C3 = 141-180мм от левого поля. C2 имеет `margin_left=400 dxa`. Левая колонка: «Дата формирования» / `{{ bank.statement_date_formatted }}` / «Сотрудник, сформировавший выписку» (gridSpan=2) / «ФИО сотрудника» / Кирьянов Е. В. / «Должность сотрудника» / Старший менеджер по обслуживанию. Правая: «Подпись» / `__STAMP_SIGNATURE__` (R0C3 с bottom-border = линия подписи в template, но в runtime убирается через fix8 `val=nil`) / «Структурное подразделение ПАО Сбербанк» (gridSpan=2) / «Территориальный банк» / Доп.офис №9038/01655 / «Номер подразделения» / №9038/01655 / «Адрес подразделения» / г Москва, ул Алтайская, д 4. Все статика — в шаблоне. |
| `templates/docx/assets/v2_sber/signature.png` | Подпись Кирьянова, 988×555, RGBA (прозрачный фон) |
| `templates/docx/assets/v2_sber/stamp_bank.png` | Круглая печать Сбера, 400×400 |
| `_resolve_bank_statement_template_path` | Для любого банка проверяет `_v2.docx` суффикс перед `_v1`. |
| `render_bank_statement` dispatcher | `name == "bank_statement_template_v2.docx"` → `_insert_v2_signature_images` (Альфа). `name.endswith("_v2.docx") and "044525225" in name` → `_insert_v2_sber_signatures` (Sber). Передаёт `mode = "markers_only" if for_translation else "full"`. |
| `_insert_v2_sber_signatures(doc, *, mode)` | **Финальный порядок (fix10):** 1) найти target_p (параграф `__STAMP_SIGNATURE__` в R0C3); 2) **Этап 1.5 layout-правки** — убирается bottom-border со всех ячеек Row 0 (включая C3 из template) через `val=nil`; перед footer table вставляется spacer-параграф `line=1700 twips` (~30мм) с `lineRule=exact`; 3) **чистка маркера** `__STAMP_SIGNATURE__` (всегда, в обоих режимах); 4) `if mode == "markers_only": return` (для перевода — без PNG); 5) подпись Кирьянова FLOATING (x=112, y=-3, width=25мм, z_order=10); 6) круглая печать FLOATING (x=150, y=-10, width=35мм, z_order=20, **rotation_deg=25** — поворот по часовой). |
| `_add_floating_picture` расширен | Новые kwargs **`z_order=None`** (детерминированный relativeHeight, иначе random — для z-порядка между floating'ами; signature z=10, stamp z=20 → печать ПОВЕРХ подписи) и **`rotation_deg=0`** (поворот через атрибут `rot` на `<a:xfrm>` в единицах 1/60000 градуса, положительное = по часовой). Обратно совместимо (Альфа Pack 52 работает без новых kwargs). |

### Серия fix1..fix10 — что и зачем

| Fix | Что сделано | Зачем |
|---|---|---|
| fix1 | Перенос ассетов из `pack54_assets/templates/docx/...` в `templates/docx/...` (PowerShell `Move-Item`) | После Pack 54.0 ассеты ушли в неверную папку → renderer не находил v2-шаблон, делал fallback на v1 с зелёной плашкой ЭП |
| fix2 | Координаты круглой печати: `x_off -15→+140`, `width 50→35`, `y_off -15→-5` | **Ключевое открытие**: в `_add_floating_picture` `<wp:positionH relativeFrom="column">` → X отсчитывается **от левого поля страницы**, не от ячейки якорного параграфа. С `x=-15` печать улетала на 0..50мм от поля (поверх C0-C1 «Дата/ФИО»), а не в C3. После +140 центр печати в C3. |
| fix3 | Попытка: убрать зелёный + vAlign=BOTTOM в C3 + grayscale logo через PIL | **СЛОМАЛ РЕНДЕР** — `ValueError: Invalid input tag of type cython_function_or_method`. Виновник: PIL-конверсия PNG в word/media/ или vAlign в неканоническом порядке schema tcPr. Откатил fix4. |
| fix4 | Откат template из автобэкапа `.bak_pre_pack54_fix3` + только безопасная замена `#21A038 → #1A1A1A` в document.xml (без PIL, без vAlign) | Recovery от fix3. Убран зелёный «ИТОГО ПО ОПЕРАЦИЯМ ЗА ПЕРИОД» текст и его подчёркивание-полоса. |
| fix5 | Подпись Кирьянова: INLINE → FLOATING. Добавлен kwarg `z_order` в `_add_floating_picture`. Signature z_order=10, stamp z_order=20. | INLINE 35мм подпись раздувала Row 0 до ~20мм высотой → большой провал между «Подпись» и «Сотрудник, ...». FLOATING не влияет на высоту ячейки. Random `relativeHeight` мог прятать стамп под подпись — детерминируем. |
| fix6 | Right-align «Подпись» в C2 + spacer ~30мм перед footer table + signature `x=141, y=-3`, stamp `x=150, y=-10` | Опустить таблицу ниже, подпись/линия ближе к слову «Подпись» (right-align), поднять подпись на линию. |
| fix7 | Подпись и линия влево: revert right-align, добавить bottom-border на C2 → линия от 90 до 180мм, signature `x=90, y=+5` | Юзер: «выравнивание по левому краю с нижними строчками». Линия продлевалась через C2 + C3. |
| fix8 | Убрать линию **полностью**: bottom-border всех ячеек Row 0 → `val=nil` + clean атрибуты sz/space/color. Signature `x=112, y=-3`. | Юзер: «линию вообще убери, подпись справа от слова Подпись». Слово остаётся в C2 (97-109мм), подпись справа от слова (112-137мм). |
| fix9 | Параметр `rotation_deg` в `_add_floating_picture` + `rotation_deg=25` для круглой печати | Юзер: «поверни печать по часовой на 20-30°». OOXML: `<a:xfrm rot="1500000">` (25° × 60000). |
| fix10 | Layout-правки (Этап 1.5) и чистка маркера перенесены **ДО** проверки `mode=markers_only` | **Критично для перевода RU→ES**: иначе ES-версия в combined PDF получала линию подписи и без spacer'а — несимметрично с RU. Теперь обе версии идентичны по layout. |

**Pack 53 инфраструктура переиспользуется как есть** — Sber v2 заявка автоматически получает кнопку «✨ Перевести выписку» в дровере (видна для `bank_template_legacy_v1=FALSE`), endpoint POST `/admin/applications/{id}/bank-statement/translate` работает, combined PDF (RU стр 1-N + ES стр N+1..) скачивается через GET `/download-file/bank_statement`.

### Ключевые уроки Pack 54 (для следующих банков)

1. **`relativeFrom` в `_add_floating_picture`**: `column` для X = **левое поле страницы**, не ячейка. `paragraph` для Y = относительно якорного параграфа (точная семантика зависит от наличия inline-картинки в нём — см. Правило 72).
2. **НИКОГДА не трогать template DOCX «на горячую» через PIL/zip-rewrite** — fix3 disaster. Всё что можно — делать в runtime через `OxmlElement` / `lxml` в самом renderer'е (см. Этап 1.5 в `_insert_v2_sber_signatures`).
3. **Runtime XML модификации (vAlign, tcBorders, jc) безопаснее** чем редактирование template'а — они применяются на свежем DOCX после docxtpl-рендеринга, не накапливаются.
4. **Z-order между floating'ами в одном параграфе** = `relativeHeight` (не `behindDoc`). Default random — может прятать одну картинку под другую. Использовать явный `z_order` kwarg.
5. **Rotation для floating PNG** = `<a:xfrm rot="N">` где N = degrees × 60000. Положительное = по часовой.
6. **Markers_only режим** (для перевода) ДОЛЖЕН применять те же layout-правки что и `full` — иначе combined PDF будет несимметричным.

### Что в `/mnt/user-data/outputs/` для следующего чата

- `apply_pack53_0_backend.py` + `apply_pack53_1_frontend.py` + `migrate_pack53_translation_storage.py` — Pack 53 (DEPLOYED)
- `apply_pack54_sber_v2.py` — Pack 54.0 (DEPLOYED)
- `apply_pack54_fix2.py` ... `apply_pack54_fix10.py` — серия fix-итераций (DEPLOYED)
- `pack54_assets/` — папка ассетов (после fix1 уже в правильных путях)

---


<a id="архитектура"></a>

## Сессия 16.06.2026 — Pack 56.x — ФИЧА «Ситы» (запись на приём) + заглушка отлова сит — DEPLOYED

Новое окно «Ситы» в карточке клиента: контакты для портала записи (отдельные от
контактов клиента), локация, N.I.E (общий с «Карта TIE») и кнопки отлова сит.
Сделано в 5 паков (8 apply-скриптов), все идут точечными правками по образцу Pack 50.15.

### Данные (всё на applicant, кроме NIE)
- `applicant.cita_fill_type` VARCHAR(16) — `'no_cert'` (без сертификата) / `'with_cert'` (с сертификатом)
- `applicant.cita_cert_owner` VARCHAR(128) — чей сертификат (ЗАГЛУШКА, выпадающий список пустой — сертификаты загрузим позже)
- `applicant.cita_email` VARCHAR(128) — почта для подтверждения ситы (≠ email клиента)
- `applicant.cita_phone` VARCHAR(32) — телефон для кода при оформлении (≠ phone клиента)
- `applicant.cita_location` VARCHAR(16) — `'Madrid'` / `'Barcelona'`
- `applicant.cita_catching` BOOLEAN DEFAULT FALSE — флаг «отлов запущен» (читает будущий алгоритм)
- **N.I.E НЕ дублируется** — используется `application.nie` (то же поле, что «Карта TIE»). CitaDrawer пишет nie через `patchApplication(...,{nie} as any)` — ровно как TieDrawer. Значение синхронно в обе стороны (один источник = `application.nie`).

### Бэкенд
- Миграции: `apply_pack56_0_migration` (fill_type/cert_owner/email/phone), `apply_pack56_2_migration` (location), `apply_pack56_3_migration` (catching) в `db/migrations.py`, зарегистрированы в `main.py` lifespan. (Функции `56_1`/`56_4` — НЕ миграции, это фронт-паки; нумерация функций не сплошная — это ок.)
- `api/applicants.py` `_PATCHABLE_FIELDS` += `cita_fill_type, cita_cert_owner, cita_email, cita_phone, cita_location, cita_catching`. PATCH-петля корректно проводит boolean (`False == ""` → ложь → `setattr`).
- `models/applicant.py` — поля в `Applicant(table)` + `ApplicantCreate` + `ApplicantUpdate`.

### Фронт
- **NEW `components/admin/cards/CitaCard.tsx`** — плашка «Ситы» на странице заявки, ПЕРЕД чек-листом (`<BusinessChecksBlock>`). Read-only сводка (тип/локация/контакты) + «Изменить» (открывает CitaDrawer) + кнопки отлова. Props: `applicant, application, onEdit, onChanged`.
- **NEW `components/admin/CitaDrawer.tsx`** — ОТДЕЛЬНЫЙ дровер редактирования (не дровер клиента!). Поля: тип, [чей сертификат], локация, N.I.E (после локации, валидация `/^[XYZ]?\d{6,8}[A-Z]$/`), email, телефон. Самодостаточный (свой локальный `DField`). Сохранение: `updateApplicant` (cita_*) + `patchApplication` (nie). Props: `applicant, application, onClose, onSaved`.
- `ApplicationDetail.tsx` — импорт/стейт/рендер CitaCard + CitaDrawer (`showCitaDrawer`); плашка открывает CitaDrawer; `application` non-null прокинут (как в TieDrawer). `onChanged={loadAll}`.
- `ApplicantDrawer.tsx` — секция «Ситы» была добавлена в 56.0/56.1, затем **ПОЛНОСТЬЮ УДАЛЕНА в 56.2** (JSX + стейт + payload). Сейчас в дровере кандидата сит НЕТ.
- `lib/api.ts` — `cita_*` + `cita_catching` в типе payload `updateApplicant`. NIE через `patchApplication` с `as any` (тип patchApplication не содержит nie — как у TieDrawer).

### Кнопки отлова (ЗАГЛУШКА — алгоритма ещё нет)
- **«Начать ловить ситу»** — активна ТОЛЬКО при `application.status === "approved"` И заполнены `location + email + phone + nie` И `!cita_catching`. По клику → `cita_catching = true`.
- **«Остановить»** — активна ТОЛЬКО при `cita_catching === true`. По клику → `cita_catching = false`.
- Кнопки на плашке (общая карточка клиента), индикатор «Ловля запущена/остановлена». Реальный алгоритм подключится к флагу `cita_catching` (см. Roadmap).

### Паки и apply-скрипты (в корне репо, в .gitignore)
| Pack | Скрипт | Что |
|---|---|---|
| 56.0 | `apply_pack56_0_backend.py` / `apply_pack56_1_frontend.py` | поля cita_* + секция в ApplicantDrawer (позже убрана) |
| 56.1 | `apply_pack56_2_backend.py` / `apply_pack56_3_frontend.py` | `cita_location` + плашка `CitaCard` перед чек-листом |
| 56.2 | `apply_pack56_4_cita_drawer.py` | отдельный `CitaDrawer`, удаление секции из ApplicantDrawer |
| 56.3 | `apply_pack56_5_nie.py` | поле N.I.E в CitaDrawer (синхрон с «Карта TIE» через patchApplication) |
| 56.4 | `apply_pack56_6_catching_backend.py` / `apply_pack56_7_catching_frontend.py` | флаг `cita_catching` + кнопки Start/Stop (заглушка) |

### Тест после деплоя
Лог Railway: `[migration] Pack 56.0/56.1/56.4: applicant.cita_* / cita_location / cita_catching ready`.
Заявка статус «Одобрена» + заполнены все поля ситы → кнопка «Начать ловить ситу» активна.

# 3. Архитектура и ключевые подсистемы

## 3.1 Position — переиспользуемый шаблон должностей (Pack 20.x)

**Архитектура:**
- `Position` НЕ привязан к Company (Pack 20.0 удалил `position.company_id`)
- Position определяется по `(specialty_id, level)`:
  - **Specialty** — ОКСО (08.03.01 Строительство, 09.03.04 Программная инженерия, ...)
  - **Level** — L1 Junior / L2 Middle / L3 Senior / L4 Lead
- Связь Company↔Position идёт **только через Application**

**Содержимое Position:**
- `title_ru`, `title_ru_genitive`, `title_es`, `primary_specialty_id`, `level` (1-4)
- `salary_rub_default`, `tags`, `duties` (9-11 обязанностей)
- `profile_description` — краткое описание профессии для блока «ПРОФЕССИЯ» в CV
- **12 полей tech_opinion** (6 пар RU/ES) — см. §3.16
- `international_analog_ru/_es`

**Зарплатные сетки:** IT 200/320/450/600к, Строители 180/240/320/450к, Юристы 100/180/280/400к, Менеджмент/БА 150/240/340/480к, Экономика 110/200/320/600к, Продажи 130/220/320/500к, Лингвистика 90/180/280/400к.

## 3.2 work_history_generator (Pack 20.3, обновлён в Pack 37.8)

**Файл:** `backend/app/services/work_history_generator.py` → `suggest_work_history(applicant, session) -> WorkHistorySuggestion`.

**Алгоритм:**
1. Specialty: `applicant.education[-1].specialty` → match по коду в Specialty
2. Region: `applicant.inn_kladr_code[:2]`
3. Count = 1/2/3 (веса 0.2/0.5/0.3)
4. Уровни: для count=2 → [3, 2] (Senior + Middle)
5. Position по `(specialty_id, level)`, `duties` снапшотом
6. Companies из `LegendCompany` по region+specialty (fallback Москва)
7. Периоды: 3.5+ года последняя работа, 1.5-3 года предыдущие

**Endpoint:** `POST /admin/applicants/{id}/regen-work-history` (Pack 30.0).

**Pack 37.8 (важно):** после `suggest_work_history` endpoint сохраняет `result.records` в `applicant.work_history` (через `model_dump()`), затем вызывает `sync_dn_work_record_safe` → возвращает фронту список с DN-employer первой записью.

## 3.3 DN-employer sync в work_history (Pack 37.2/37.6/37.7/37.8)

**Архитектура источника истины:**
- Единственный источник истины — `applicant.work_history[0]` в БД
- При наличии Application с `company_id + position_id + contract_sign_date` — `work_history[0]` всегда = DN-employer

**Сервис `services/work_history_sync.py`:**
- `sync_dn_work_record(applicant, application, session, *, company=None, position=None) -> bool`
- `sync_dn_work_record_safe(application, session) -> bool` — обёртка с try/except
- Логика идемпотентна: no-op если БД уже синхронизирована

**3 точки sync:**
1. **PATCH `/admin/applications/{id}`** — если затронуты `company_id`/`position_id`/`contract_sign_date`
2. **POST `/admin/applications/{id}/assign`** — всегда
3. **PATCH `/admin/applicants/{id}`** — если в patch есть `work_history`

**CV-рендерер `_build_cv_work_history` (Pack 25.7 + Pack 37.6):** идемпотентен, оставлен как защитный слой.

## 3.4 AI Document Audit (Pack 37.x)

**Концепция:** симуляция приёма документов в консульстве через LLM. Менеджер на полностью укомплектованной заявке нажимает «🛂 Симуляция приёма документов» → backend рендерит полный пакет в памяти → извлекает текст из ZIP → LLM (Sonnet 4.6) проверяет по 80 правилам в 6 категориях → возвращает findings с verdict (PASS/WARN/FAIL).

**Backend файлы:**
- `app/models/audit.py` — `ApplicationAuditReport`, `AuditFinding`, enum'ы
- `app/services/audit/context_builder.py` — собирает «досье кейса», `_gost_transliterate`, `_looks_like_gibberish`
- `app/services/audit/document_extractor.py` — `docx2txt + pypdf`
- `app/services/audit/prompts.py` — системный промпт ~14579 chars, 80 правил
- `app/services/audit/auditor.py` — `run_audit` через `BackgroundTasks`
- `app/services/audit/fix_handlers.py` — 8 whitelist fix-actions с Pydantic-валидацией
- `app/services/audit/audit_export.py` — DOCX-генератор
- `app/api/audit.py` — 7 endpoints

**Frontend файлы:**
- `frontend/app/admin/applications/[id]/audit/page.tsx` — страница со светофором
- `frontend/components/admin/AuditFindingCard.tsx`, `AuditManualFixDialog.tsx`
- Кнопка «🛂 Симуляция приёма документов» в `ApplicationDetail.tsx`

**Стоимость:** ~$0.17 за прогон, 30-200 сек.

## 3.5 ИНН-генератор (Pack 17 → 28)

Параллельно живут **ДВА** источника ИНН:

**Источник 1 — `self_employed_registry`** (legacy SNRIP, ежемесячный импорт, 546k+ ИП, ⚠️ гуглятся). **Сейчас используется** через `pipeline.suggest_inn_for_applicant`.

**Источник 2 — `npd_candidate`** (Pack 28, новый, через `rmsp-pp.nalog.ru?sk=SZ` → EGRUL → NPD). **Не используется в выдаче** до Pack 28 Часть 2.

**Дата НПД — синтетическая** (Pack 18.3.4). ФНС API урезали (Инцидент 19). TODO Pack 28.5.

## 3.6 LLM-перевод на испанский (Pack 15 + 35.9-35.10)

LLM-pipeline берёт русские документы и переводит на испанский. Для CV: «Modalidad: Remoto» в каждой работе + блок Declaración в конце.

**Pack 35.9-35.9.2** — разбиение шапки «город + дата» в `_split_city_date_paragraphs(doc)` в `docx_translator.py`.
**Pack 35.10** — латинские инициалы в подписи через `_build_applicant_subs` в `name_substitution.py`.

⚠️ **ВАЖНО:** русские шаблоны НЕ должны содержать испанских блоков (Modalidad/Declaración).

## 3.7 Банковская выписка (Pack 25 + 35.7 + 47 + 48 + 50.30/50.31 найм)

**Multi-bank resolution** (Pack 47.0):
- `_resolve_bank_statement_template_path(bik)` в `docx_renderer.py` — switch по BIK
- Шаблон `bank_statement_template_<bik>.docx` ищется автоматически. Fallback на default `bank_statement_template.docx` (Альфа) если нет специфичного.

**Активные шаблоны на 25.05.2026:**
| BIK | Bank | Шаблон | Pack |
|---|---|---|---|
| 044525593 | АО «АЛЬФА-БАНК» | `bank_statement_template.docx` (default) | 25.x |
| 044525225 | ПАО Сбербанк | `bank_statement_template_044525225.docx` | 47.0–47.23 + 49.0 + 49.1 |
| 044525974 | АО «ТБанк» | `bank_statement_template_044525974.docx` | 48.0–48.4 |

**Bank-specific postprocessors** в `context.py`:
- `_apply_sber_postprocess(bank_data, applicant, session)` — Сбер (Pack 47.2): категории, running_balance, сберовский формат сумм, форматирование номера счёта `XXXXX XXX X XXXX XXXXXXX`. No-op для не-Сбер.
- `_apply_tbank_postprocess(bank_data, applicant, session)` — ТБанк (Pack 48.0 + 48.3.1): формат сумм tx (`+574.00 ₽`), формат итогов (`799 033,00 ₽`), `card_number` (4 цифры по hash bank_account), сортировка tx desc, договор (`bank.contract_date_formatted`, `bank.contract_number` — детерминированно по `applicant.id`), времена tx (`tx.date_formatted` = multiline `"DD.MM.YYYY\nHH:MM"`, `tx.settle_date_formatted`). No-op для не-ТБанк.

Оба вызываются в `build_context` после построения базовых tx данных. Резолв по `applicant.bank.bik` через `session.get(Bank, applicant.bank_id)`.

**Шаблон по умолчанию (Альфа):** `templates/docx/bank_statement_template.docx`

**Двухфазный → четырёхфазный рендер** (`docx_renderer.py:render_bank_statement`):
1. **Фаза 1** — docxtpl подставляет шапку через Jinja
2. **Фаза 2** — python-docx клонирует строку-маркер `__TX_*__` для каждой транзакции
3. **Фаза 3** (Pack 47.15+) — `_replace_ep_badge_marker` ищет маркер `__EP_BADGE__` и заменяет на inline-картинку (только для Сбера)
4. **Фаза 4** (Pack 47.19) — `_ensure_paragraphs_at_tc_end` + `_normalize_picture_ids` для OOXML compliance (см. §3.18)

**Tx-маркеры в шаблонах:**
- Альфа/Сбер: `__TX_DATE__`, `__TX_CODE__`, `__TX_DESCRIPTION__`, `__TX_AMOUNT__`, `__TX_CATEGORY__` (Pack 47.2, только Сбер), `__TX_BALANCE__` (Pack 47.2, только Сбер)
- ТБанк дополнительно (Pack 48.0): `__TX_DATE_SETTLE__`, `__TX_AMOUNT_CARD__`, `__TX_CARD__`

Шаблоны без специфичных маркеров их просто игнорируют (если маркера нет в тексте параграфа — нет и замены).

**Логика периода:**
```python
if statement_date_override is not None:
    statement_date = statement_date_override
else:
    statement_date = today - timedelta(days=random.randint(7, 10))
period_end = statement_date - timedelta(days=1)
period_start = statement_date - relativedelta(months=3)
```

**UI Pack 25.10:** в `ApplicantDrawer.tsx` секция «Банковская выписка» с date-picker, кнопкой ✨ Auto, кнопкой «Сгенерировать/Перегенерировать».

**Ветка НАЙМА (Pack 50.30 + 50.31):** для `application_type == EMPLOYMENT` выписка генерится по другой логике — переводы от работодателя 2 раза/мес вместо «услуг по договору»:
- хелпер `_split_salary_employment(gross)` → (аванс, зарплата): на_руки = оклад×0.87 (минус 13% НДФЛ); аванс ≈40% округл. вниз до 10тыс; зарплата = остаток
- `generate_default_transactions(..., is_employment: bool)` — в цикле по месяцам если найм: **аванс** (20-25 число текущего месяца) + **зарплата** (5-9 число следующего) с формулировками «Аванс/Заработная плата за {месяц} {год}г. по Трудовому договору №{N} от {дата}», затем `continue` (минуя KWIKPAY/НПД/комиссию). Бытовые траты (СБП, подписки) — общие
- `is_employment` пробрасывается из ДВУХ мест: `context.py` (автогенерация при рендере, Pack 50.30) И `api/bank_transactions.py` `_generate_for_app` (кнопка «Перегенерировать», Pack 50.31) — оба через `application_type == EMPLOYMENT`
- эталон `Выписка_по_счету_Орлов.docx` (оклад 310000 → аванс 100000 + зарплата 169700). Самозанятый (`is_employment=False` дефолт) — не изменён

## 3.18 Sber EP badge — runtime PNG плашка ЭП (Pack 47.15–47.20)

**Что это:** документ "подписан электронной подписью" — внизу выписки Сбера прямоугольная плашка с логотипом СБЕР, текстом "Документ подписан электронной подписью*", синей полосой "СВЕДЕНИЯ О СЕРТИФИКАТЕ ЭП", и 4 строками реквизитов сертификата (Сертификат / Владелец / Действителен / Дата подписи). До Pack 47.15 пытались нарисовать вложенными таблицами в DOCX — выглядело криво на разных версиях Word. С Pack 47.15+ — static PNG asset + PIL overlay реквизитов в runtime.

**Файлы:**
- `templates/docx/sber_ep_card.png` (1134×537, 50kb) — static asset, вырезан из эталонной выписки Сбера. Белый фон, лого + заголовки + синяя полоса + ПУСТАЯ нижняя зона для реквизитов.
- `backend/app/templates_engine/ep_badge_renderer.py` — функция `render_ep_badge_png(statement_date_str, cert_no, owner, valid_from, valid_to)`. Открывает sber_ep_card.png, ImageDraw накладывает 4 строки реквизитов в координатах `LABEL_X=76, VALUE_X=347, START_Y=310, ROW_GAP=45`, шрифт DejaVu Sans 24pt.
- В `docx_renderer.py` ФАЗА 3 `_replace_ep_badge_marker` — ищет маркер `__EP_BADGE__`, заменяет через `add_picture`.

**Реквизиты сертификата:**
- Cert №, владелец, validity — hardcoded по эталону Сбера в `ep_badge_renderer.py`
- Дата подписи — динамическая из `bank.statement_date_formatted`

**OOXML compliance** (Pack 47.18 + 47.19):
- После `add_picture` python-docx ставит `pic:cNvPr id="0"` → дубликат с sber_logo в шапке → Word ругается. `_normalize_picture_ids` проходит по `doc.element.iter()` и заменяет ВСЕ id="0" на уникальные 1002, 1003, ...
- Если ячейка с picture'ом заканчивается на `<w:tbl>` или удалили последний `<w:p>` — Word ругается "Обнаружено неоднозначное сопоставление ячеек". `_ensure_paragraphs_at_tc_end` для каждой `<w:tc>` проверяет последний child и добавляет `<w:p>` если нет.

**Pillow** уже на проде как транзитивная зависимость python-docx — новых deps не добавилось.

## 3.8 Нумерация актов/счетов (Pack 25.6 v2)

Два разных поля:
- **`sequence_number`** = `int idx` (1, 2, 3) — для lookup в `docx_renderer.py`
- **`display_number`** = `"04/26"` — в шаблонах

## 3.9 OCR auto-apply (Pack 13 + 25.12 + 37.3 + 41.0-C)

**Файл:** `backend/app/api/client_documents_admin.py:_auto_apply_ocr_to_applicant` + `import_package.py`.

**Правила применения:**
| Поле | Правило |
|---|---|
| `last_name_native`, `first_name_native`, `passport_*`, `passport_expiry_date` (Pack 37.3), `birth_*`, `email`, `phone` | Только если в applicant поле пусто |
| **`education`** (DIPLOMA_MAIN) | **ВСЕГДА замещает** (Pack 25.12) |
| **`passports[]`** (Pack 41.0-C) | **upsert по `number`** через `upsert_by_number()` |

## 3.21 Автозаполнение заявки из текста менеджера (Pack 50.38)

**Бизнес:** менеджер вставляет полуструктурированное Telegram-сообщение в диалог «Импорт пакета» → заявка заполняется автоматически. **Скан = истина** (текст заполняет только пустые после OCR поля).

**Пакет `backend/app/services/manager_text/`:**
- `parser.py` — `parse_manager_text(text)`: LLM (MANAGER_TEXT_PROMPT, строгий JSON) → секции applicant/spain_address/company/position/representative/submission/diploma/unrecognized[].
- `reference_resolver.py` — fuzzy-поиск справочников **без LLM** (difflib SequenceMatcher, список динамически из БД, порог 0.72). `resolve_company/position/representative/spain_address`. Устойчив к транслитерации (RENKONS→Rekkons 0.96). Представитель по ИМЕНИ (NIE бонус). Адрес — по ЯДРУ (улица+номер, `_addr_core` убирает тип улицы/этаж/индекс/город — Pack 50.38-D1-fix).
- `apply_parsed.py` — `apply_parsed_to_application(session, app, parsed)`: applicant-поля только пустые (`_APPLICANT_FIELD_MAP`: father_name→father_name_latin, phone→phone, passport_number простое поле), resolve справочников→привязка id, submission_city дефолт Barcelona, ненайденное+диплом+unrecognized→internal_notes блок «[Из текста менеджера]». + `determine_application_type` (НАЙМ→EMPLOYMENT).

**Интеграция (Pack 50.38-D3-2):** `import_package.py` finalize_import принимает `manager_text` из body → парсит → определяет тип → создаёт заявку → прокидывает `parsed_text` в фоновую задачу `_run_ocr_for_docs_batch(.., parsed_text)` → `_auto_apply_ocr_to_applicant(.., parsed_text)` применяет ПОСЛЕ OCR (скан=истина). Только основной finalize (не with/skip-company). Эндпоинты: POST `/admin/applications/parse-manager-text` (только парсинг), POST `/admin/applications/{id}/apply-manager-text-existing` (дозакидывание в существующую).

**Фронт (D4):** ImportPackageDialog — textarea «Сообщение от менеджера» на шаге классификации (для новой заявки), manager_text в 3 finalize-вызова.

**Заголовок заявки (D-fix):** `ApplicationDetail.tsx` — для иностранца (native=«—», latin валиден) заголовок берёт latin ФИО, не заметки. placeholder = когда И native И latin пустые.

## 3.10 DOCX-импорт компании (Pack 26.0)

**Бэкенд:** `services/company_extractor.py` + endpoint `POST /admin/companies/extract-from-document`. LLM генерирует все поля компании включая **склонения директора**.

**Frontend:** `CompanyImportDialog.tsx`, `CompanyDrawer.tsx` с prop `initialFields?`.

## 3.11 Корзина с автоудалением (Pack 27.0)

**Архитектура:** soft-delete через `application.deleted_at`, lazy cleanup записей старше 7 дней при открытии `/admin/trash`.

**3 endpoint'а:** `DELETE`, `POST .../restore`, `DELETE .../permanent`.

## 3.12 PDF AcroForm flatten (Pack 36.0 + 36.1)

**Файл:** `backend/app/pdf_forms_engine/flatten_form.py` → `flatten_pdf_form(bytes) -> bytes`.

После `pypdf.update_page_form_field_values()`: переписывает `/AP /N` своим content stream (9pt Helvetica), `generate_appearance_streams()` для radio/checkbox, `flatten_annotations()`. Идемпотентно.

⚠️ **Шаблоны** обязательно с inclusion.gob.es (см. §8).

## 3.13 Final Submission Audit (Pack 39.0)

**Архитектурное отличие от Pack 37.0:** проверяет реальные сканы документов клиента, а не сгенерированные DOCX из БД.

**3 таблицы БД** (привязка к **`applicant_id`**):
- `final_submission_document` — физические документы с дедупом по SHA256, история версий через `is_active + previous_version_id`, `extraction_method` (pypdf/vision/docx2txt/mixed)
- `final_submission_audit_report` — прогоны проверки с `inspector_summary`
- `final_submission_finding` — findings с `affected_documents JSONB` и `values_found JSONB`, status (open/acknowledged/dismissed — БЕЗ fix_action)

**8 категорий проверок A-H:** A_identity, B_numeric, C_dates, D_company, E_translation, F_completeness, G_quality, H_stale (хвосты прошлых клиентов).

**Гибрид extraction:** pypdf бесплатно для текстовых PDF, Claude Vision (`claude-sonnet-4-5`) для сканов до 30 страниц, docx2txt для DOCX.

**AI-классификатор:** Haiku-4-5, 21 категория, confidence 0-1, source 'ai'/'manual'.

**LLM-аудитор:** Sonnet-4-5, `max_tokens=32768`, temperature=0.0. Промпт — «опытный визовый офицер испанского консульства, 15 лет стажа».

**Frontend** (`app/admin/applications/[id]/final-check/page.tsx`): drag&drop, polling каждые 5 сек на extraction + 2 сек на is_running, FindingsByCategory, кнопки «Иду исправлять»/«False positive», DOCX-экспорт через RFC 5987.

**Стоимость:** ~$0.10 за прогон.

## 3.14 Multi-passport на applicant (Pack 41.0)

**Архитектура источника истины:**
- `applicant.passports` (JSONB) — массив `PassportRecord`
- `applicant.passport_id_for_ru_docs` (VARCHAR(36)) — выбор менеджера для договора
- Скаляры `applicant.passport_*` — **зеркало primary** через `reconcile_applicant_passports()`

**PassportRecord:**
```python
{
  "id": "p_xxxxxxxx",          # уникальный 10-символьный hex
  "number": "C05803188",        # нормализованный номер
  "issue_date": "2026-04-10",   # ISO string в JSONB
  "expiry_date": "2036-04-10",  # ISO string
  "issuer": "AZE",              # оригинал из паспорта
  "issuer_ru": "Министерство...",  # русский (для договора)
  "passport_type": "FOREIGN",   # RU_INTERNAL | RU_FOREIGN | FOREIGN
  "is_primary": true,           # ровно один primary (или ни одного)
  "notes": "...",
  "source": "ocr|manual|legacy_backfill"
}
```

**Сервис `services/applicant_passports.py`:**
- `normalize_number(num) -> str` — uppercase, strip, no spaces
- `make_passport_record(...)` — создание с id вида `p_<8hex>`
- `upsert_by_number(applicant, record)` — поиск по номеру + merge
- `recompute_primary(applicant)` — выбор primary (preferring not RU_INTERNAL, then latest issue_date)
- `get_primary(applicant)` — текущий primary
- `get_passport_dict_for_ru_docs(applicant)` — 3-уровневый приоритет: passport_id_for_ru_docs → primary → legacy скаляры
- `sync_primary_to_legacy_fields(applicant)` — пишет primary в скаляры
- `reconcile_applicant_passports(applicant)` — full pipeline (после любого изменения passports[])

**Бизнес-логика после Pack 41.0-K (финал серии 41.0):**
- **Русские клиенты (nationality=RUS) с выбранным внутренним паспортом** (`passport_id_for_ru_docs` → `passport_type=RU_INTERNAL`) → **ВНУТРЕННИЙ паспорт во ВСЕ русские документы** (договор + акты + счета + employer_letter + CV + tech_opinion + business_trip + employment_contract + bank_statement + НПД-справка). Override централизован в `build_context` (5 точечных замен) + отдельный override в `build_npd_certificate_context`.
- **Русские клиенты без выбора внутреннего** → primary паспорт через `applicant.passport_*` скаляры
- **01_Договор.docx (Pack 41.0-G)** — дополнительный override поверх Pack 41.0-K: для договора может быть ЛЮБОЙ выбранный паспорт (включая исторический загран), не только RU_INTERNAL
- **Иностранцы (nationality≠RUS)** → выбор `passport_id_for_ru_docs` работает ТОЛЬКО для договора, остальные русские документы → primary
- **Испанские PDF формы** (MI-T, EX-17, designacion, compromiso, declaracion, mi_tie) → ВСЕГДА primary
- **Апостиль** → шаблон не использует passport_* поля → не затрагивается

**Override механизм** в `context.py build_context` (Pack 41.0-K):
```python
# Перед _parse_passport
_pass_number_pack41k = applicant.passport_number
_pass_issue_date_pack41k = applicant.passport_issue_date
_pass_issuer_pack41k = _resolve_passport_issuer_for_template(applicant)
if (applicant.nationality or "").upper() == "RUS":
    _ru_dict = get_passport_dict_for_ru_docs(applicant)
    if _ru_dict.get("passport_type") == "RU_INTERNAL" and _ru_dict.get("number"):
        _pass_number_pack41k = _ru_dict["number"]
        # ... issue_date conversion + issuer override
passport_data = _parse_passport(_pass_number_pack41k, applicant.nationality)
# В return dict все applicant.passport_* заменены на _pass_*_pack41k
```

**Override механизм в `docx_renderer.py render_contract()`** (Pack 41.0-G — ПОВЕРХ Pack 41.0-K):
```python
context = build_context(application, session)
# Pack 41.0-G — override для договора
_ru_passport = get_passport_dict_for_ru_docs(application.applicant)
if _ru_passport.get("number"):
    # Pack 41.0-G fix2 — конвертим ISO-string в date
    _raw = _ru_passport.get("issue_date")
    _issue_date = date.fromisoformat(_raw) if isinstance(_raw, str) else _raw
    context["applicant"]["passport_number"] = _ru_passport["number"]
    context["applicant"]["passport_issue_date"] = _issue_date
    context["applicant"]["passport_issue_date_str"] = fmt_date_ru(_issue_date)
    # ... остальные паспортные поля
```

**UI:**
- `frontend/components/admin/PassportsSection.tsx` — карточки паспортов с inline-редактированием
- Dropdown «🇷🇺 Паспорт для договора» (применяется только к 01_Договор.docx)
- Кнопка «Использовать внутренний РФ» для россиян
- Кнопка «Резолв issuer_ru» через словарь стран

**Множественные паспорта в `applicant_document` (Pack 42.2):**
- `_upsert_document_for_application` в `import_package.py` НЕ перезаписывает паспорта (4 типа: PASSPORT_NATIONAL, PASSPORT_FOREIGN, PASSPORT_INTERNAL_MAIN, PASSPORT_INTERNAL_ADDRESS)
- Для всех остальных типов (диплом, справка, апостиль) — старая логика upsert (один документ на тип)

## 3.20 НПД-справка ИФНС резолв (Pack 18.3 + 33.8 + 41.0-L + 41.0-M)

**Контекст:** для каждой НПД-справки (КНД 1122035) нужно подставить **наименование ИФНС** места постановки на учёт самозанятым. Раньше — auto-resolve по `inn_kladr_code[:2]` (где выдан ИНН). Проблема: ИНН и место жительства могут быть в разных субъектах РФ (Инна Лясковец, ИНН в Калининграде 3905, проживает в Москве Раменки).

**Слой 1 — Ручной override (Pack 41.0-M, приоритет):**

Поле `applicant.npd_ifns_name VARCHAR(500) NULL`. Менеджер копирует точное наименование ИФНС из официального сервиса ФНС **[service.nalog.ru/addrno.do](https://service.nalog.ru/addrno.do)** (там по адресу выдаётся актуальный код+наименование+ОКТМО). Workflow в UI (Pack 41.0-N):
1. 📋 Кнопка под home_address → `navigator.clipboard.writeText(...)` (inline-фидбек ✓ Скопировано на 2 сек, без alert — Pack 41.0-P)
2. 🔗 Ссылка target="_blank" на сервис ФНС
3. Менеджер вставляет адрес, копирует наименование
4. Поле «Название ИФНС для НПД-справки» (textarea) сразу под NpdCheckBadge (Pack 41.0-O)
5. Сохраняет

В `build_npd_certificate_context` (`context_npd_certificate.py`):
```python
_manual_ifns_name = (applicant.npd_ifns_name or "").strip()
_ifns_full_name = _manual_ifns_name if _manual_ifns_name else ifns.full_name
_ifns_short_name = _manual_ifns_name if _manual_ifns_name else ifns.short_name
# В return "ifns": {"full_name": _ifns_full_name, "short_name": _ifns_short_name, ...}
```

**Слой 2 — Auto-resolve (fallback, если ручное поле пустое):**

`_resolve_region_code(applicant)` с 3 Tier (Pack 41.0-L):
- **Tier 0** — keyword-таблица по `home_address` (по падежам/регионам):
  - «московская область» → 50, «ленинградская область» → 47, «ростовская область» → 61
  - «санкт-петербург» → 78, «краснодарский край» → 23, «ростов-на-дону» → 61
  - «москва» → 77, «спб» → 78, «сочи»/«анапа»/«краснодар»/«новороссийск» → 23
  - **Важно:** длинные ключи раньше коротких чтобы «Московская область» не схватилась как «Москва»
- **Tier 1**: `inn_kladr_code[:2]`
- **Tier 2**: `inn[:2]`

Дальше `_pick_ifns(session, region_code, applicant)` через Pack 33.8 Tier A/B/C-prime/C по `ifns_office.coverage_keywords`.

**Seed-данные `ifns_office` для региона 77 (Москва):**
- УФНС по г. Москве (default, code=7700, coverage_keywords=[])
- ИФНС № 13 (САО) — coverage_keywords: костякова, тимирязевск, савёловск, аэропорт, бескудниковский, войковский, дмитровский, дегунино, коптево
- ИФНС № 15 (СВАО) — снежная, свиблово, алексеевский, ростокино, марфино, бутырский, отрадное, медведково, ярославский
- ИФНС № 24 (ЮАО) — симоновский, даниловский, бирюлёво, нагатино, донской, чертаново, зябликово, орехово-борисово
- ИФНС № 27 (ЮЗАО) — лазарева, бутово, зюзино, котловка, черёмушки
- ИФНС № 28 (ЮЗАО) — академический, каховка, тёплый стан, ясенево, коньково, тропарёво
- ИФНС № 31 (ЗАО) — молодёжная, кунцево, можайский, фили, давыдково, крылатское, вернадского
- **ИФНС № 29 (ЗАО, Pack 41.0-L)** — раменки, очаково, очаково-матвеевское, ново-переделкино, тропарёво-никулино, проспект вернадского, солнцево, внуково

**Известный пробел:** в seed нет ИФНС из ЦАО, ВАО, ЮВАО, СЗАО, ЗелАО, ТиНАО (~22 инспекции). Для клиентов оттуда auto-resolve упадёт на default УФНС (Pack 41.0-L Tier C). **Решение** — ручное заполнение `npd_ifns_name` через сервис ФНС (Pack 41.0-M/N). Massive seed отложен (был частью Pack 41.0-M v1 черновика, отброшен в пользу ручного override).

## 3.15 Drag-and-drop в "Документы клиента" (Pack 42.3)

**Архитектура quick-mode** в `ImportPackageDialog`:
- Новые props `initialFiles?: File[]` + `initialApplicationId?: number`
- При наличии обоих → `useEffect` авто-стартует: `setTarget("existing")`, `setExistingApplicationId(initialApplicationId)`, `requestAnimationFrame(() => handleFilesSelected(initialFiles, ""))`
- Пропускаются шаги «выбор файлов» (UploadStep) и «выбор заявки»

**В `AdminClientDocuments`:**
- Вся секция = drop-zone (`onDragEnter/Over/Leave/Drop` на корневом div)
- При drag-over: рамка синяя + overlay «Отпустите файлы для импорта»
- При drop: `setDroppedFiles(files)` → рендерится `<ImportPackageDialog initialFiles={droppedFiles} initialApplicationId={applicationId}>`
- После `onImported`: автоматический refresh через `load()`

## 3.16 Tech Opinion подсистема (Pack 40.0-G + Pack 43.0 + Pack 44.0 + Pack 45.0)

**Что это:** генерация документа `17_Техническое_заключение.docx` (DICTAMEN TÉCNICO sobre el carácter de trabajo a distancia) — заключение работодателя для испанского консульства о том, что деятельность работника осуществляется дистанционно.

**Шаблон:** `templates/docx/tech_opinion_template.docx`
**Рендерер:** `templates_engine/docx_renderer.py:render_tech_opinion(application, session)` — общий `build_context()` без переопределений.
**Контекст-сборка:** `templates_engine/context.py` строки 1602-1693 — собирает company.director_*, position.tech_opinion_*, application.tech_opinion_override_text. Helper-функции: `_to_director_position_nominative_ru`, `_to_director_position_es`, `_short_latin_from_full` (после Pack 44.0).

**12 полей tech_opinion в Position (6 пар RU/ES):**

| Поле | Тип | Назначение |
|---|---|---|
| `tech_opinion_description_ru/_es` | text | §1 — длинное описание деятельности |
| `tech_opinion_tools_ru/_es` | jsonb `[{name, purpose}, ...]` | §2 — список инструментов и софта |
| `tech_opinion_steps_ru/_es` | jsonb `[{title, body}, ...]` | §3 — шаги рабочего процесса |
| `tech_opinion_grounds_ru/_es` | jsonb `[str, ...]` | §4 — основания дистанционности |
| `tech_opinion_contract_clause_ru/_es` | text | §4 — цитата из договора |
| `international_analog_ru/_es` | varchar | §1 — «должность аналогична Production Process Analyst в международной практике» |

Также участвует `title_es` (varchar NOT NULL) — короткое название должности на испанском, повторяется ~8 раз в документе.

**Per-application override:** `application.tech_opinion_override_text` — заменяет §1-§4 для конкретной заявки (Pack 40.0-G, не для seed-должностей).

### Workflow создания новой должности (после Pack 45.0)

1. Менеджер открывает `PositionDrawer` → вводит 4 обязательных поля: title_ru, title_es, primary_specialty_id, level
2. Жмёт **«✨ Сгенерировать всё»** в шапке Drawer (Pack 45.0) → 30-50 сек → 9 русских полей заполнены (duties, tags, profile_description + 5 tech_opinion_*_ru + international_analog_ru)
3. Менеджер проверяет/правит русские поля, дополнительно заполняет title_ru_genitive и salary_rub_default
4. Жмёт **«✨ Сгенерировать испанский»** в `TechOpinionSection` (Pack 43.0) → 30-60 сек → 5 ES-полей заполнены
5. Менеджер проверяет/правит → «Сохранить»

### Endpoints

- `POST /admin/positions/generate-russian` (Pack 45.0) — принимает `{title_ru, title_es, primary_specialty_id, level, ...}`, возвращает 9 русских полей. В БД НЕ пишет.
- `POST /admin/positions/{position_id}/translate-spanish` (Pack 43.0) — переводит RU → ES, возвращает 5 ES-полей. В БД НЕ пишет.

### Подпись директора в испанской части

Использует helper `_short_latin_from_full(company.director_full_name_latin)` в context.py (Pack 44.0 — фикс).

Логика: русский порядок ФИО («Фамилия Имя Отчество» = `KAYTUKTI KONSTANTIN PETROVICH`) → испанский стиль подписи: инициалы имени+отчества + ФАМИЛИЯ в верхнем регистре = `K.P. KAYTUKTI`. До Pack 44.0 функция была написана для западного порядка имён и выдавала `K. PETROVICH` (теряя фамилию).

**Старый endpoint** `api/tech_opinion.py` (Pack 40.0) deprecated, оставлен пустым роутером для совместимости с `main.py`.

## 3.17 Диплом для хурадо (Pack 46.0)

**Что это:** PDF-документ, визуально воспроизводящий титульный лист диплома без гербовых элементов и печатей. Передаётся присяжному переводчику (хурадо) в Испании как структурированный source для перевода и заверения апостилем реального диплома клиента.

**Архитектурное отличие** от других документов в проекте: НЕТ DOCX/PDF-шаблонного файла. PDF собирается **с нуля через ReportLab** в `backend/app/services/diploma_pdf_renderer.py` — координаты каждого элемента прописаны как явные числа `x, y, font, size`. Раскладка подбиралась 10 итераций по эталону Кости.

**Файлы:**
- `backend/app/services/diploma_pdf_renderer.py` — ReportLab-рендерер. Размер страницы 708.96 × 497.76 pt (landscape). Оси: `LEFT_CX=170` (левая колонка — ВУЗ, реквизиты), `RIGHT_CX=536` (правая — ФИО, специальность, БАКАЛАВР), `RIGHT_EDGE=668.2` (правый край подписей).
- `backend/app/services/diploma_field_generator.py` — Sonnet 4.6 генерирует 6 полей в правильном формате для конкретного ВУЗа (не реальные идентификаторы).
- `backend/app/fonts/` — TTF Liberation Serif (Regular/Bold/Italic, ~1.5 МБ закоммичены). Fallback на системные `/usr/share/fonts/truetype/liberation/` если bundled нет. Crash-fallback на встроенный `Times-Roman` (без кириллицы — крякозябры, но не падает).

**Раскладка элементов** (координаты Y измерены сверху страницы):
| Элемент | x | y | font | size |
|---|---|---|---|---|
| ФИО строка 1 (фамилия) | RIGHT_CX | 59 | Regular | 18 |
| ФИО строка 2 (имя+отчество) | RIGHT_CX | 78 | Regular | 18 |
| Специальность (38.03.05 Бизнес-информатика) | RIGHT_CX | 162 | Regular | 11 |
| Степень БАКАЛАВР/МАГИСТР | RIGHT_CX | 275.8 | Regular | 12 |
| Протокол строка | RIGHT_CX | 311.8 | Regular | 11 |
| ВУЗ (до 4 строк заглавными) | LEFT_CX | 151.2+ | Regular | 10 |
| г. Москва | LEFT_CX | 203.8 | Regular | 10 |
| Номер бланка КРАСНЫЙ #B71C1C | LEFT_CX | 355 | Bold | 14 |
| registration_number | LEFT_CX | 421.9 | Regular | 11 |
| issue_date | LEFT_CX | 467.3 | Regular | 11 |
| Подписант 1 (по правому краю) | RIGHT_EDGE | 402.5 | Regular | 11 |
| Подписант 2 (по правому краю) | RIGHT_EDGE | 439.2 | Regular | 11 |

**Endpoints (Pack 46.0/B):**
- `POST /admin/applicants/{id}/education/{idx}/generate-fields` — LLM генерирует 6 полей по `institution + specialty + graduation_year + degree`. Возвращает dict с 6 полями. В БД НЕ пишет (фронт сам через PATCH).
- `GET /admin/applicants/{id}/education/{idx}/diploma.pdf` — рендерит PDF, отдаёт `Content-Disposition: inline` с ASCII fallback + RFC 5987 для кириллического имени (Правило 61).

**UI (Pack 46.0/C):**
- В `ApplicantDrawer.tsx` внутри `education.map((edu, i) => ...)` добавлена подсекция «📄 Диплом для хурадо» после поля specialty
- 6 inputs (последний — signers как textarea «по одному на строку»)
- Кнопка ✨ **Сгенерировать** — disabled пока пусто `institution`/`specialty`/`graduation_year`. После клика **автосохраняет** через `updateApplicant + onSaved()` (Pack 46.0 fix1)
- Кнопка 📄 **Скачать диплом** — disabled пока пусто `diploma_number`/`registration_number`/`issue_date`. Открывает PDF в новой вкладке через `blob + URL.createObjectURL + window.open` (нужен Authorization header — прямой `<a href>` не сработает)

**Workflow:**
1. Менеджер вводит ВУЗ + специальность + год выпуска (например через ✨ Подобрать вуз из Pack 19.0)
2. Жмёт ✨ Сгенерировать (~10-20 сек) → 6 LLM-полей заполнены и **сразу в БД**
3. Менеджер при желании редактирует значения вручную
4. Жмёт 📄 Скачать диплом → PDF в новой вкладке

**Промпт для protocol_number** (fix2): сужен с «1-30, чаще всего 1-10» до «1-3, чаще всего 1». На реальных дипломах указывается номер **итогового** заседания ГЭК (о присвоении квалификации всем выпускникам потока), а не номер защиты ВКР конкретного студента — это всегда 1-3.

**Стоимость LLM:** ~$0.01-0.02 за прогон (короткий промпт, выход ~500 токенов).

---

<a id="бд"></a>

# 4. Активные данные в БД

## Position table — 53+ строки (Pack 33.4 +21, + новые через Pack 45.0)

Основные специальности: 08.03.01 Строительство, 09.03.04 Прог. инжен., 38.03.01 Экономика, 38.03.02 Менеджмент, 38.03.06 Торговое дело, 40.03.01 Юриспруденция, 42.03.01 Реклама (PR), 45.03.02 Лингвистика + 21 specialty × Middle от Pack 33.4.

⚠️ **Position id=2 геодезист** дублирует уровень с id=13 на 08.03.01 L2. `SPECIFIC_KEYWORDS` tie-breaker корректно работает.

## representative — 5 активных
TELEPNEVA, BUGARIN, DMITREV, ORLOVA, KORENEVA — все в Барселоне.

## spain_address — 13 активных
11 новых из списка Кости + Balmes 128 (Барселона) + Castelló 5 (Мадрид).

## company table — 18+ записей

Ключевые:
- **id=16** ООО АГАЛАРОВ-ДЕВЕЛОПМЕНТ — Pack 25 сессия, директор Василевская А.В.
- **id=18** ООО РЕНКОНС ХЭВИ ИНДАСТРИС — Pack 34.x каскад багов, директор Кайтукти К.П.

⚠️ **Мусор для cleanup:** id=1 (`xzcxzc`), id=10 (`gfgdfgdfgfd`), id=15 (ИНЖГЕОСЕРВИС с тестовыми реквизитами).

### Структура полей company

```
tax_id_primary       — ИНН (обязательно)
tax_id_secondary     — КПП (для ОПФ "ООО" — обязательно). ⚠️ Имя обманчивое.
country              — ISO-3 ('RUS', 'KAZ').
short_name           — 'ООО "НАЗВАНИЕ"' кириллицей
full_name_ru/es      — 'Общество с ограниченной...' / 'Sociedad de Responsabilidad Limitada...'
legal_address        — юр. адрес одной строкой (после Pack 16.7 — основной)
legal_address_line1/line2  — legacy, в per-company шаблонах после Pack 33.6 не используется
postal_address       — почт. адрес. Если NULL — берётся legal_address.
director_full_name_ru          — именительный
director_full_name_genitive_ru — родительный
director_short_ru              — 'Беляев Р.К.'
director_full_name_latin       — GOST 7.79 (порядок: ФАМИЛИЯ ИМЯ ОТЧЕСТВО)
director_position_ru           — РОДИТЕЛЬНЫЙ ПАДЕЖ ('Генерального директора')
bank_name, bank_account, bank_bic, bank_correspondent_account
notes                — ОГРН, КПП-историческое
```

⚠️ **ОГРН не имеет отдельного поля** — кладём в `notes`.

## bank table — 5 банков (Pack 47/48 серия)

| id | BIK | Name | Шаблон выписки |
|---|---|---|---|
| 1 | 044525593 | АО «АЛЬФА-БАНК» | default `bank_statement_template.docx` |
| 2 | 044525225 | ПАО Сбербанк | **v2 (Pack 54 DEPLOYED): `bank_statement_template_044525225_v2.docx`** — Ч/Б, Кирьянов Е.В., круглая печать повёрнута на 25°, перевод RU→ES доступен. v1 (legacy): `bank_statement_template_044525225.docx` (Pack 47, плашка ЭП) — выбирается через `bank_template_legacy_v1=TRUE`. |
| 3 | 044525187 | Банк ВТБ (ПАО) | пока default Альфа (TODO: свой шаблон) |
| 4 | 044525974 | АО «ТБанк» | `bank_statement_template_044525974.docx` (Pack 48) |
| 5 | 044525985 | ПАО Банк «ФК Открытие» | пока default Альфа (TODO: свой шаблон) |

## applicant table

⚠️ **Полей `full_name_ru` или `full_name_es` НЕТ.** Реальные поля:
- `last_name_native`, `first_name_native`, `middle_name_native`
- `last_name_latin`, `first_name_latin`
- `passport_number`, `passport_issue_date`, `passport_expiry_date` (Pack 37.3), `passport_issuer`, `passport_issuer_ru` (Pack 35.2-35.3)
- **`passports JSONB`** (Pack 41.0-A) — массив PassportRecord
- **`passport_id_for_ru_docs VARCHAR(36)`** (Pack 41.0-A) — выбор для договора
- `birth_date`, `birth_place_latin`, `birth_country` (Pack 18.10)
- `nationality`, `sex`, `marital_status`
- `inn`, `inn_registration_date`, `inn_source`, `inn_kladr_code`
- `home_country`, `home_address`
- `education: List[EducationRecord]`, `work_history: List[WorkRecord]`, `languages: List[LanguageRecord]`
   - **`education[*]`** (JSONB, Pack 19.0 + 46.0): базовые поля — `institution`, `degree`, `graduation_year`, `specialty`. Поля диплома для хурадо (Pack 46.0, без миграции — JSONB новые ключи): `diploma_number`, `registration_number`, `protocol_number`, `protocol_date` (ISO), `issue_date` (ISO), `signers[{name, position}]`
- `apostille_signer_*` (Pack 18.9)

Когда нужно «полное имя на русском» — `f"{first_name_native} {last_name_native}".strip()`.

## application table

Ключевые поля: `applicant_id`, `company_id`, `position_id`, `representative_id`, `spain_address_id`, `contract_number`, `contract_sign_date`, `contract_sign_city`, `salary_rub`, `bank_statement_date` (Pack 25.9), `bank_transactions_override` (JSON), `submission_date`, `fingerprint_date` (Pack 36.1), `nie`, `deleted_at` (Pack 27.0), `is_filed`, `is_archived`, `is_urgent`, `is_paid`, `is_ready_for_pickup` (Pack 34.2), `outgoing_number`, `outgoing_date` (Pack 40.0-G), `tech_opinion_override_text` (Pack 40.0-G).

## ИНН-реестр

- `self_employed_registry`: total ~546k, used минимально, последний импорт от 25.04.2026
- `npd_candidate` (Pack 28): 10 записей, 3 verified (region 23)

## Pack 37 — audit таблицы

- `application_audit_report`: verdict (PASS/WARN/FAIL), model_used, tokens, cost_usd, is_running, summary_counts (JSON), triggered_by
- `audit_finding`: category, severity, title, description, evidence, field_path, current_value, suggested_value, fix_action, fix_payload (JSON), status (open/accepted/dismissed/manually_fixed)

## Pack 39 — final submission таблицы

- `final_submission_document`, `final_submission_audit_report`, `final_submission_finding` — см. §3.13

---

<a id="pipeline"></a>

# 5. Pipeline генерации документов

```
Менеджер → Drawer applicant'а → ✨ «Подобрать опыт работы»
   ↓
POST /admin/applicants/{id}/regen-work-history (Pack 30.0 + Pack 37.8)
   ↓
suggest_work_history() → sync_dn_work_record_safe → DN-employer первой записью
   ↓
WorkHistorySuggestion → менеджер сохраняет
   ↓
Менеджер заполняет компанию+договор+position → PATCH /applications/{id}
   ↓
Pack 37.2 хук: sync_dn_work_record_safe (если изменились триггерные поля)
   ↓
Менеджер «Сгенерировать пакет» → POST /applications/{id}/render-package
   ↓
templates_engine/docx_renderer.py:
   - render_contract → 01_Договор.docx
     [Pack 41.0-G override на passport_id_for_ru_docs если задан]
   - render_act × N → 02-04_Акт.docx (primary паспорт)
   - render_invoice × N → 05-07_Счёт.docx
   - render_employer_letter → 08_Письмо.docx (Pack 40.0-G outgoing)
   - render_cv → 09_Резюме.docx
   - render_bank_statement → 10_Выписка.docx
   - render_npd_certificate → 15_Справка_НПД.docx
   - render_npd_certificate_lkn → 15b_Справка_НПД_ЛКН.docx
   - render_apostille → 16_Апостиль.docx
   - render_tech_opinion → 17_Техническое_заключение.docx (Pack 40.0-G + 44.0 подпись)
   ↓
pdf_forms_engine (Pack 36.0):
   - render_mi_t → 11_MI-T.pdf (flatten_pdf_form)
   - render_designacion → 12_Designacion_representante.pdf
   - render_compromiso → 13_Compromiso_RETA.pdf
   - render_declaracion → 14_Declaracion_antecedentes.pdf
   - render_ex17 → 17_EX-17_TIE.pdf (Pack 36.1)
   ↓
ZIP пакет → R2 storage → доступен через UI
[Pack 42.0: статус НЕ меняется автоматически на DRAFTS_GENERATED — менеджер вручную через dropdown]

[ОПЦИОНАЛЬНО] Менеджер → 🛂 «Симуляция приёма документов» (Pack 37.0-D)
   ↓
POST /applications/{id}/audit/run → BackgroundTasks → Findings → UI /audit
   ↓
DOCX export через /audit/reports/{id}/export.docx

[ОПЦИОНАЛЬНО] Менеджер → 📋 «Финальная проверка» (Pack 39.0)
   ↓
/admin/applications/{id}/final-check → drag&drop сканы → extraction Background
   ↓
POST /final-submission/audit/run → Sonnet-4-5 → 8 категорий A-H
   ↓
Findings UI с Acknowledge/Dismiss → DOCX export
```

---

<a id="правила"></a>

# 6. Правила проекта (МАСТЕР-СПИСОК)

## Workflow и деплой

### 🔥 Правило 34 — Apply-скрипты `apply_pack*.py` в стиле точечных правок

Стандарт проекта: каждый Pack оформляется отдельным `apply_pack*.py` скриптом который:
1. Делает backup затрагиваемых файлов в `*.bak_pre_pack*`
2. Применяет точечные `str.replace(OLD, NEW, 1)` правки с проверкой `if old not in text → FAIL`
3. Идемпотентен
4. Поддерживает `--backfill-only` где нужно

Скрипты в корне репо `D:\VISA\visa_kit\`, запуск `python apply_pack37_X.py`. После применения — `git status`, точечный `git add <file>`, коммит, push на main → автодеплой.

### 🔥 Правило 40 — `git add -A` категорически ЗАПРЕЩЁН

Если в `git status` есть untracked мусор — `git add -A` потащит всё. Точечный `git add <file1> <file2>` (Инцидент 22).

### 🔥 Правило 56 — Patcher должен `sys.exit(1)` при FAIL якоре

Если anchor не нашёлся в `str.replace` — `return 1` или `sys.exit(1)`, **не** `print + pass` (Инцидент 33).

### Правило 38 — Smoke-test нового endpoint'а: всегда `/docs` + клик в UI

Импорт сервиса в файле endpoint'а ≠ endpoint зарегистрирован. После деплоя: открыть `/docs` → Ctrl+F новый роут → клик в UI → DevTools Network проверить 200 (Инциденты 12, 20).

### Правило 54 — При signature change функции — grep ВСЕХ вызовов

Pack 35.4 правил `_build_bank_context`, но забыл что внутри есть делегирующий вызов без `applicant` → NameError у Шахина. Перед deployment signature change — `grep -rn "имя_функции(" .` (Инцидент 31).

### 🔥 Правило 66 — Идемпотентный маркер apply-скрипта = уникальная подстрока из тела ИМЕННО ЭТОЙ правки

Использовать `"Pack 43.0"` или `"translatePositionToSpanish"` как маркер идемпотентности — **ошибка**. После того как первая правка в файле добавила эти строки, последующие правки в том же файле silent-skip'нутся, потому что маркер уже «найден». Маркер должен быть **уникальной подстрокой из тела конкретной правки**, не повторяющейся в других правках того же файла.

Примеры хороших маркеров:
- `'@router.post("/{position_id}/translate-spanish")'` — для endpoint Pack 43.0
- `'async function handleTranslate()'` — для функции в TSX
- `'render_tech_opinion → 17_Техническое_заключение.docx | 40.0-G'` — для строки таблицы в MD

Плохие: `"Pack 43.0"`, `"translate"`, `"def "`, `"function"`. Инцидент 44.

## PowerShell специфика

### Правило 35 — PowerShell ps1 файлы ВСЕГДА в UTF-8 with BOM
Без BOM PS читает как cp1251 → ломается кириллица.

### Правило 39 — Команды для пользователя: реальные пути, без `<placeholder>`
`cd $env:USERPROFILE\Downloads` ✅, `cd C:\Users\<you>\Downloads` ❌.

### Правило 41 — PowerShell 5.1 + UTF-8: `[Console]::OutputEncoding` обязательно
`>` редирект mangles UTF-8 на ru-Windows. `::new()` это PS 7+, в PS 5.1 — `New-Object` (Инцидент 23).

### Правило 45 — PowerShell `>>` запускает команды параллельно
Провал первой не блокирует остальные. Patcher всегда отдельной командой (Инцидент 24).

### Правило 48 — Один `git add` на строку
В PowerShell `\` continuation не работает как в bash. Писать `git add file1` на отдельной строке.

### 🔥 Правило 67 — При подозрительно пустом грeps по `backend/` использовать `Select-String -LiteralPath`

`Get-ChildItem -Path backend -Recurse -Include *.py | Select-String -Pattern "..."` иногда **молча возвращает ноль** на присутствующий паттерн (минимум 3 раза за сессию 24.05.2026: `tech_opinion`, `director_full_name_latin_initials`, `_to_director_position_*`, `_short_latin_from_full`). Причина не выяснена окончательно — возможно связано с подчёркиваниями в паттерне, кодировкой файла или buffering pipeline. Workaround: `Select-String -LiteralPath <конкретный_файл> -Pattern "..."` по конкретному файлу — **работает стабильно**. При неожиданно пустом грeps — переключаться на эту форму.

## БД и миграции

### Правило 18 — Перед DROP COLUMN или breaking changes — глобальный grep
`Get-ChildItem ... | Select-String -Pattern "имя_поля"` по всему проекту перед удалением. ⚠️ Если грeps пустой подозрительно — Правило 67.

### Правило 20 — Перед SQL — dump схемы таблицы
`SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name = '...'`.

### Правило 43 — Raw SQL INSERT обязан перечислять NOT NULL колонки без DB DEFAULT
SQLModel `default_factory=datetime.utcnow` работает только через ORM. Для raw SQL `NOW()` явно (Инцидент 21).

### Правило 53 — SQL enum в UPPERCASE
В JSON API возвращается lowercase, но в Postgres хранится UPPERCASE (`PENDING`, `IN_PROGRESS`). Для SQL — uppercase.

### Правило 55 — Railway Query UI multi-statement silent drop
`SELECT count(*); SELECT min(id);` показывает результат только последнего. По одному запросу за раз (Инцидент 32).

## SQLModel и FastAPI

### Правило 36 — В скриптах вне FastAPI request-цикла использовать `Session(engine)`, НЕ `get_session()`
`get_session()` это FastAPI generator dependency, в CLI скриптах — `with Session(engine) as session: ...`.

### Правило 52 — `getattr(application, "applicant", None)` — лотерея
SQLModel relationship может быть None или AttachedObject. Надёжно: `session.get(Applicant, application.applicant_id)`.

## DOCX/PDF шаблоны

### Правило 25 — Финальная проверка DOCX — ВСЕГДА в Word, не в LibreOffice
LibreOffice даёт фантомные регрессии (Pack 25.0 история).

### Правило 28 — Сначала проверить шаблон, потом код
В Pack 25.x ушло 30 минут на дебаг кода, оказалось что в шаблоне `bank_statement_template.docx` были hardcoded даты периода. Симметрично: Pack 44.0 — потратил время предполагая что переменные шаблона выдуманы, оказалось они вычисляются в `context.py`. Сначала проверить **обе стороны**: и шаблон, и контекст.

### Правило 42 — DOCX шаблоны: первый клиент оставляет следы
Hardcoded имена/должности/специальности первого клиента. Параметризовать всё.

### Правило 57 — `<w:r>` без `<w:rPr>` = Word применяет default стиль
При создании нового run из старого ВСЕГДА копировать `<w:rPr>` через `deepcopy` (Pack 35.10).

### 🔥 Правило 58 — PDF AcroForm-шаблоны только официальные с государственного ведомства
Никогда не сохранять заполненный AcroForm PDF поверх шаблона. SHA256 шаблонов в §8 — обязательный артефакт (Инцидент 35).

### 🔥 Правило 59 — После любого LLM-перевода прогонять `substitutions.apply()` на результате
LLM может откатывать substitution. Прогон `substitutions.apply()` после ответа LLM защищает от реверсии латинских инициалов (Инцидент 36).

### 🔥 Правило 60 — Apply-скрипт с большими `str.replace` блоками: ВСЕГДА верификация after-apply
Точечный `str.replace(OLD, NEW, 1)` может «применился» (no FAIL) но по факту не изменил файл — fuzzy whitespace/EOL mismatch. После апплая ОБЯЗАТЕЛЬНО: `Select-String -Pattern "уникальная_строка_из_NEW"` для каждого блока, чтобы убедиться. Если правок много (5+) — собирать как отдельный verification step в скрипте + has_* проверки каждого блока перед записью (Инцидент 38).

### 🔥 Правило 61 — HTTP-заголовки только ASCII, кириллические значения через RFC 5987
`Content-Disposition: filename="Селимай..."` → `UnicodeEncodeError: 'latin-1' codec`. Правильно: `filename="ascii_fallback.docx"; filename*=UTF-8''{urllib.parse.quote(unicode_name)}` (Инцидент 39).

### 🔥 Правило 62 — Многоуровневое экранирование Python-строк: `ast.parse` сразу
После создания файла apply-скриптом — `python -c "import ast; ast.parse(open('новый_файл.py').read())"`. Если SyntaxError — точный line+column. Часовой fix-цикл превращается в 5-минутный (Инцидент 40).

### 🔥 Правило 63 — PowerShell + квадратные скобки в путях: `-LiteralPath`
`Get-Content frontend\app\admin\applications\[id]\page.tsx` падает с `ObjectNotFound` — PS интерпретирует `[id]` как wildcard. Решение: `Get-Content -LiteralPath "..."`. То же для `Set-Content`, `Test-Path` (Инцидент 41).

### 🔥 Правило 64 — Patcher с многострочными якорями: ВСЕГДА проверять через len-delta после `str.replace`

Большие многострочные якоря с пустыми строками/комментариями часто содержат структурные различия между моим прогнозом и реальным файлом (CRLF vs LF, лишние пробелы, отсутствующие комментарии). `str.replace` при несовпадении возвращает текст БЕЗ изменений — patcher без проверки длины думает что применил. Каждый `str.replace` обязан быть обёрнут в:
```python
before_len = len(text)
new_text = text.replace(OLD, NEW, 1)
if len(new_text) == before_len:
    raise PatcherError(f"якорь не сматчился: {label}")
```
Альтернатива для импортов: AST-based вставка через `ast.parse() + end_lineno` многострочного импорта (Инцидент 42).

### 🔥 Правило 65 — JSONB ISO-string поля конвертить в date/datetime ПЕРЕД передачей в форматтеры

`passports[].issue_date` хранится как ISO-string `"2026-04-10"` (PostgreSQL JSONB). Прямая передача в `fmt_date_ru()` падает `AttributeError: 'str' object has no attribute 'strftime'`. Конверсия обязательна:
```python
_raw = passport_dict.get("issue_date")
if isinstance(_raw, str) and _raw:
    _issue_date = date.fromisoformat(_raw)
else:
    _issue_date = _raw  # уже date или None
```
То же касается любых JSONB полей с датами (Инцидент 43).

### 🔥 Правило 68 — Helper-функция работает с конкретным форматом данных — задокументировать

Функция `_short_latin_from_full()` была написана с docstring `"John Robert Smith → J. Smith"` (западный порядок), но на проекте используется на данных в **русском порядке** `KAYTUKTI KONSTANTIN PETROVICH`. Docstring обманчиво указывал что функция работает, на самом деле она для другого формата. Перед использованием helper'а — прочитать docstring И проверить на реальных данных:
```python
print(_short_latin_from_full("KAYTUKTI KONSTANTIN PETROVICH"))  # → "K. PETROVICH" — WRONG
```
Если в проекте формат данных **другой** чем в docstring helper'а — переписывать helper, а не данные (Pack 44.0, Инцидент 45).

### 🔥 Правило 69 — Перед `git commit` ВСЕГДА `git status` для проверки staged-файлов

`git add несуществующий_файл.py` в PowerShell **не падает** — просто ничего не добавляет в staged. Если apply-скрипт упал до создания .py файла (например на скачивании зависимости), но Костя продолжает по чек-листу `git add → git commit → git push` — коммит уходит **без** этого файла. На проде Railway/Vercel импорт упадёт с `ModuleNotFoundError` через 2 минуты после деплоя.

Защита:
```powershell
git add <конкретные файлы>
git status          # ← ОБЯЗАТЕЛЬНО! проверь что все нужные файлы в "Changes to be committed"
git commit -m "..."
git push origin main
```

Если в `git status` после `git add` каких-то файлов нет в staged — НЕ коммитить. Проверить:
1. Файл действительно существует на диске? (`Get-ChildItem <путь>`)
2. Файл не в `.gitignore`?
3. apply-скрипт прошёл до конца без ошибок?

(Pack 46.0, Инцидент 46.)

**Pack 47.16 — расширение того же правила:** apply-скрипт может **молча копировать v1 поверх v1** (контент идентичный). `shutil.copy2` не сравнивает — просто копирует. `git diff` после этого пустой, `git add` без эффекта, коммит уходит без обновления файла. Симптом: на проде остаётся старая логика хотя в выдаче apply-скрипта было "✓ Updated".

Защита: при каждом apply, **обязательно** в `git status` после `git add` — посмотреть что нужный файл в "Changes to be committed". Если файла нет — apply скопировал то же что и было. Нужно вручную взять файл из выдачи Claude (через "Скачать") и положить в `backend/...`. (Инцидент 47.A.)

### 🔥 Правило 70 — OOXML schema strict: нормализация после picture/table edits

Word при открытии DOCX проверяет соответствие схеме OOXML строже чем LibreOffice. Нарушения, на которые Word ругается (а LibreOffice — нет):

1. **`<pic:cNvPr id="...">` должен иметь id >= 1**. python-docx по умолчанию ставит `id="0"` при каждом `add_picture()`. Несколько картинок с id=0 → Word "не удаётся прочитать содержимое" → восстановление с потерей картинки.
2. **Каждый `<w:tc>` обязан заканчиваться на `<w:p>`**. Если функция `_strip_empty_paragraphs_*` удалила последний параграф ячейки, или `add_picture` создал ячейку без завершающего `<w:p>` — Word ругается "Обнаружено неоднозначное сопоставление ячеек".
3. **Дубликаты `<wp:docPr id="X">` запрещены** — каждый docPr должен быть уникальным в документе.

После ЛЮБЫХ манипуляций с picture/table через python-docx — прогонять документ через:
```python
def _ensure_paragraphs_at_tc_end(doc):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    for tc in doc.element.iter(qn("w:tc")):
        children = list(tc)
        if not children or not children[-1].tag.endswith("}p"):
            tc.append(OxmlElement("w:p"))

def _normalize_picture_ids(doc, start_id=1002):
    from docx.oxml.ns import qn
    next_id = start_id
    for el in doc.element.iter():
        if el.tag.endswith("}cNvPr") and el.get("id") == "0":
            el.set("id", str(next_id))
            next_id += 1
```

LibreOffice headless эти проблемы не показывает (мягче проверяет schema). Финальная сверка — только в Word.

(Pack 47.18/47.19, Инцидент 47.B, связь с Правилом 25.)

### 🔥 Правило 71 — Apply-скрипты пишущие Python код: raw-strings + pre-write py_compile + CRLF-aware

Apply-скрипт, который записывает Python-код в файл через `str_replace` на triple-strings, **должен использовать `r'''...'''`** для всех ANCHOR/INSERT констант. Иначе:

- `'''...\n...'''` (без `r`) — Python интерпретирует `\n` как newline ПРИ ЧТЕНИИ apply-скрипта. В строку попадает реальный newline. При записи в Python-файл этот newline ломает строковые литералы или комментарии.
- `'''...\u00a0...'''` — аналогично интерпретируется как NBSP-символ при чтении.

Pre-write `py_compile` check во временный файл — обязателен:
```python
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
    tmp.write(text)
    tmp_path = tmp.name
try:
    py_compile.compile(tmp_path, doraise=True)
except py_compile.PyCompileError as e:
    _fail(f"pre-write compile FAILED: {e}\nБитый текст НЕ записан.")
finally:
    Path(tmp_path).unlink(missing_ok=True)
```

Если compile failed — ничего не пишется на диск, оригинал не тронут. Атомарный apply.

**CRLF-aware** для Windows-репо: читать с `newline=""`, нормализовать к LF для поиска ANCHOR, при записи восстанавливать CRLF если файл был CRLF:
```python
data = path.read_bytes()
text_raw = data.decode("utf-8")
crlf_count = text_raw.count("\r\n")
newline_kind = "\r\n" if crlf_count > 0 else "\n"
text_lf = text_raw.replace("\r\n", "\n")
# ... apply на text_lf ...
out = text_lf.replace("\n", "\r\n") if newline_kind == "\r\n" else text_lf
path.write_bytes(out.encode("utf-8"))
```

**Sentinel design**: должен быть **специфичен к post-apply состоянию**, не пересекаться с pre-existing паттернами. Pack 48.0 v1 имел sentinel `_apply_tbank_postprocess(bank_data` который **совпадал и с определением функции** `def _apply_tbank_postprocess(bank_data, ...)` после первой правки → второй str_replace silent-skip'нулся → на проде функция была добавлена но никогда не вызывалась. Правильный sentinel — `bank_data = _apply_tbank_postprocess(bank_data,` (с `bank_data =` слева, специфично к вызову, не к определению).

(Pack 48.0 v2 шаблон, Инцидент 48.A.)

### 🔥 Правило 72 — Floating-anchors в DOCX: прод-LibreOffice ≠ локальный LibreOffice

При работе с `<wp:anchor>` (floating-картинки) в DOCX, рендерящимися через `soffice --headless --convert-to pdf`:

**Локальный LibreOffice (мой sandbox) и прод-LibreOffice (Railway Linux) рендерят floating-anchors ПО-РАЗНОМУ.** В частности — клипинг по границам строки таблицы:

- **Локально (моё превью):** anchor с `relativeFrom="paragraph"` и большим отрицательным Y (например -200мм) КЛИПУЕТСЯ на границе строки 0 таблицы. y=-30мм и y=-200мм рендерятся идентично.
- **На проде (Railway):** клипинга НЕТ. y=-200мм буквально поднимает картинку на 200мм выше параграфа = в шапку страницы / за пределы видимой области.

**Последствия:** если итеративно тюнить позицию по локальному превью с большими Y → на проде получишь катастрофу. Открывается только после первого реального деплоя на реальной выписке.

**Принципы:**
1. **Прод = единственный source of truth** для floating-anchor positions. Локальное превью — только для синтаксической проверки docx.
2. **Якорить floating к параграфу со ВСТАВЛЕННОЙ INLINE-картинкой** (если такая есть в той же области). Inline-картинка с `vAlign=BOTTOM` ячейки делает paragraph_top детерминированным = точка отсчёта стабильна. Это решило Pack 52 (все 3 печати якорятся к параграфу прямоугольной inline-печати).
3. **Маленькие Y offsets** (±5мм). Если на проде нужно сильное смещение — что-то не так с anchor reference (см. п.2).
4. **`layoutInCell="0"`** обязательно для floating'ов внутри ячейки таблицы — иначе клипуется ячейкой.
5. **`relativeFrom="column"` для X внутри table cell** = колонка ячейки, не section column. Отрицательный X → влево от ячейки (картинка выходит за пределы, что нужно для смещения относительно cell-paragraph при якоре к R0C2).

(Pack 52 серия, Инцидент 50.)

### 🔥 Правило 73 — `_add_floating_picture` API и константы (Pack 54 серия)

После Pack 54 функция `_add_floating_picture` в `docx_renderer.py` имеет полную сигнатуру:

```python
def _add_floating_picture(
    paragraph,            # docx Paragraph — якорь, к параграфу будет привязан wp:anchor
    png_path,             # str/Path — путь к PNG
    width_mm,             # int — ширина в мм, высота вычисляется по aspect ratio
    x_offset_mm=0,        # отступ X в мм от reference точки
    y_offset_mm=0,        # отступ Y в мм от reference точки (положительное = вниз)
    z_order=None,         # int — relativeHeight. None = random (для Альфы Pack 52).
                          #       Явный int = детерминированный z-порядок между floating'ами.
                          #       Выше = поверх. Пример: signature z=10, stamp z=20.
    rotation_deg=0,       # int — поворот через <a:xfrm rot="N"> где N = degrees × 60000.
                          #       Положительное = по часовой. 25° = rot=1500000.
):
```

**Системы координат:**
- **X**: `<wp:positionH relativeFrom="column">` → отсчёт **от ЛЕВОГО ПОЛЯ страницы**, НЕ от ячейки якорного параграфа.  Чтобы поместить картинку в C3 при cell layout 2400/2700/2900/2204 dxa = 42/48/51/39 мм → x_offset ≈ 141+ (= конец C2 / начало C3).
- **Y**: `<wp:positionV relativeFrom="paragraph">` → относительно якорного параграфа. Точная семантика зависит от наличия inline-картинки в параграфе (Pack 52 Альфа использовала 55мм inline employee stamp как якорь — стабильно; Pack 54 Sber использует пустой параграф — нужно подбирать Y эмпирически по прод-скрину).
- **Положительное Y = ВНИЗ**, отрицательное = вверх.

**Финальные координаты Pack 54 Sber v2** (для ориентира при следующих банках):
- Подпись Кирьянова: `width=25, x=112, y=-3, z_order=10` (после слова «Подпись» в C2 left-aligned 97-109мм, поднята к верху ячейки)
- Круглая печать: `width=35, x=150, y=-10, z_order=20, rotation_deg=25` (поверх подписи, центр в C3 ~158мм, повёрнута на 25° по часовой)

**Sber v2 footer table layout (для следующих банков как референс):**
- Cells: 2400/2700/2900/2204 dxa = 42/48/51/39 мм (content width 180мм)
- C0: «Дата формирования» (label slabel)
- C1: значение даты (`{{ bank.statement_date_formatted }}`)
- C2: «Подпись» (label, indent 7мм слева в template)
- C3: маркер `__STAMP_SIGNATURE__` (изначально с bottom-border = линия подписи, в runtime убирается fix8)

**Runtime XML модификации в `_insert_v2_<bank>_signatures` (паттерн Pack 54.0-fix8/10):**

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

footer_tbl_el = target_p._element.getparent().getparent().getparent()  # tc → tr → tbl

# Снять bottom-border со всех ячеек Row 0:
for c_el in footer_tbl_el.findall(qn("w:tr"))[0].findall(qn("w:tc")):
    tcPr = c_el.find(qn("w:tcPr"))
    if tcPr is None: continue
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is None: continue
    bottom = tcBorders.find(qn("w:bottom"))
    if bottom is not None:
        bottom.set(qn("w:val"), "nil")
        # обязательно очистить атрибуты sz/space/color, иначе рендерер может всё равно отрисовать
        for attr in ("sz", "space", "color"):
            attr_qn = qn(f"w:{attr}")
            if attr_qn in bottom.attrib:
                del bottom.attrib[attr_qn]

# Добавить spacer перед footer table:
spacer = OxmlElement("w:p")
sp_pPr = OxmlElement("w:pPr")
sp_spacing = OxmlElement("w:spacing")
sp_spacing.set(qn("w:line"), "1700")  # 1mm = 56.7 twips, 30mm = 1700
sp_spacing.set(qn("w:lineRule"), "exact")
sp_pPr.append(sp_spacing)
spacer.append(sp_pPr)
footer_tbl_el.addprevious(spacer)
```

**КРИТИЧНО (Pack 54.0-fix10)**: Layout-правки и чистка маркера должны быть ДО `if mode == "markers_only": return`. Иначе ES-версия в combined PDF (для перевода через Pack 53) получит template-defaults и будет отличаться от RU-версии по layout. Правильный порядок:

```python
def _insert_v2_<bank>_signatures(doc, *, mode):
    # 1. найти target_p
    # 2. Этап 1.5 — layout-правки (применяются ВСЕГДА)
    # 3. чистка маркера __STAMP_SIGNATURE__ (применяется ВСЕГДА)
    # 4. if mode == "markers_only": return   ← выход после общего layout
    # 5. вставка PNG floating'ов (только mode=full)
```

**Что НЕ делать (Pack 54.0-fix3 disaster):**
- ❌ НЕ редактировать template DOCX через PIL/zip-rewrite на лету
- ❌ НЕ добавлять `vAlign` в `tcPr` в неканоническом порядке schema (CT_TcPrInner: tcW → tcBorders → shd → tcMar → vAlign)
- ❌ НЕ пересохранять PNG через PIL.save() — теряются метаданные/profile, python-docx ругается `Invalid input tag of type cython_function_or_method`

(Pack 54 серия fix1..fix10.)

## Применение и Apply-скрипты

### Правило 30 — Все разведочные команды одним PowerShell-блоком
При просьбе разведки/grep'а — всегда собирать команды в один блок с `Write-Host "=== N. ==="` разделителями.

### Правило 33 — Apply-скрипты на больших файлах через точные строковые блоки
Не regex с предположениями. Сначала точечный grep структуры, потом apply с точно скопированными строками. После применения — verify-grep на ключевые добавленные строки.

### Правило 44 — Patcher'ы для typed JS/TS — точные строковые блоки
Не regex. Prettier мог переформатировать (Инцидент 24).

### Правило 50 — DOCX templates: artist's first work always biased
Hard-coded имена первого клиента остаются в шаблонах. Поиск `Алиев|Aliyev|АЛИЕВ` после копирования шаблона.

## Прочее

### Правило 27 — Railway log levels: default не показывает `log.info()`
Для диагностики на проде — `log.warning()` или `log.exception()` (Pack 35.6).

### Правило 29 — Override JSON `bank_transactions_override` блокирует генератор
Чтобы протестировать новую логику — `UPDATE application SET bank_transactions_override = NULL WHERE id = X;`.

### Правило 31 — Defensive default OCR auto-apply имеет обратную сторону
`_auto_apply_ocr_to_applicant` обновляет ТОЛЬКО ПУСТЫЕ поля по умолчанию. Для категорий где документ важнее ручной правки (DIPLOMA_MAIN) — явный замещающий путь.

### Правило 32 — Frontend для backend-фич сразу
Pack 25.10 первый UI через 4 пакета после backend. Бэкенд без фронта — отрицательная ценность.

## Уроки общие

- SQLModel **NotNullViolation** на enum'ах в production (Pack 11).
- LLM-перевод: pre-substitution + skip ловушка — явно вызывать `_set_paragraph_text(p, text)` до `continue` (Pack 15).
- SNRIP импорт: lxml + ZIP-stream висит → читать в BytesIO; `execute_values` raw psycopg2 быстрее ORM; `BATCH_SIZE=500` оптимум для прокси Railway.
- `id` в URL `/admin?id=N` — это **application.id**, не applicant.id.
- `BackgroundTasks` нуждаются в собственной `Session(engine)` — за пределами HTTP контекста.

---

<a id="миграции"></a>

# 7. Применённые миграции БД

**Все миграции идемпотентны.**

| Pack | Что |
|---|---|
| `migration_pack17_0` | Region + KLADR + диаспоры (10 регионов) |
| `migration_pack17_2_4` | SelfEmployedRegistry, RegistryImportLog |
| `migration_pack17_6` | `region_code` в self_employed_registry |
| `migration_pack18_9_0` | `mfc_office.is_universal`, INSERT МФЦ Новоясеневский |
| `migration_pack18_9` | `applicant.apostille_signer_*` |
| `migration_pack18_10` | `applicant.birth_country` (ISO-3) |
| `migration_pack19_0` | University + Specialty + 4 новые таблицы |
| `migration_pack20_0` | DROP `position.company_id`, ADD `primary_specialty_id` + `level` |
| `migration_pack20_2_*` | Position seed (28 должностей) |
| `migration_pack21_0` | 5 представителей + 11 spain_address |
| `migration_pack25_9` | `application.bank_statement_date` |
| `migration_pack27_0` | `application.deleted_at` |
| `migration_pack33_4` | 21 Position × Middle |
| `migration_pack34_2` | `application.is_ready_for_pickup` |
| `migration_pack35_2` | `applicant.passport_issuer_ru VARCHAR(256)` |
| `migration_pack36_1` | `application.fingerprint_date` |
| `apply_pack37_0_migration` | `application_audit_report` + `audit_finding` |
| `apply_pack39_0_A_migration` | 3 таблицы Final Submission, привязка к applicant_id, UNIQUE PARTIAL `idx_fsd_applicant_sha_active` |
| `apply_pack39_0_A2_migration` | RENAME `s3_key` → `storage_key` + ADD `original_storage_key VARCHAR(512)` |
| **`apply_pack41_0_A_migration`** | `applicant.passports JSONB DEFAULT '[]'::jsonb` + `applicant.passport_id_for_ru_docs VARCHAR(36)`. Backfill 35 applicant'ов из legacy скаляров |
| **`apply_pack41_0_L_seed`** (26.05.2026) | INSERT `ifns_office` ИФНС № 29 по г. Москве (code=7729, region=77, address=119192 Мосфильмовская 82А, coverage_keywords=[раменки, очаково, очаково-матвеевское, ново-переделкино, тропарёво-никулино, проспект вернадского, солнцево, внуково и др. — 12 ключей]). Применено через `app.db.engine` в транзакции с pre-check sanity. **Не идёт в git** (seed-данные, не код) |
| **`apply_pack41_0_M_migration`** (26.05.2026) | `applicant.npd_ifns_name VARCHAR(500) NULL` — ручной override наименования ИФНС для НПД-справки (через сервис service.nalog.ru/addrno.do). Применено через `app.db.engine` ALTER TABLE с IF NOT EXISTS + dump_schema до/после. **Правило 18** соблюдено (не DROP), **Правило 20** соблюдено (dump_schema) |
| **`apply_pack50_14_migration`** (28-29.05.2026) | `application.business_trip_order_date DATE NULL` — дата приказа Т-9, фиксируется при первой генерации (today−7) |
| **`apply_pack50_15_migration`** (28-29.05.2026) | `applicant.phone_ru VARCHAR(32) NULL` — русский телефон для русских документов (СТД-Р, договоры). Испанские PDF используют `phone` |
| **`apply_pack50_38_A1_migration`** (29-30.05.2026) | `application.submission_city VARCHAR(64) NULL` + `application.submission_province VARCHAR(64) NULL` — город/провинция ПОДАЧИ (≠ город проживания). Место подписи в 6 PDF-формах берёт город подачи (хелпер submission_location.py), адрес проживания не трогается. Fallback на addr.city для старых заявок |
| **Pack 50.9-A** (ранее) | `position.okz_code VARCHAR(10) NULL` — код ОКЗ для §3 СТД-Р. Заполнен для 68 должностей через `fill_okz.py` (29.05) |
| **`company.okpo/oktmo/phone`** (Pack 50.13) | поля компании (ОКПО, ОКТМО, телефон) — перенесены из drawer заявки в карточку компании |
| **`migrate_pack50_41_doc_view_state`** (03.06.2026) | `document_view_state(application_id, doc_key, seen_at, seen_by)` + UNIQUE(application_id, doc_key) + ON DELETE CASCADE на application + индекс по application_id. Состояние «просмотрено» документов (сетки + сканы клиента, общее на команду). Через свой engine из `$env:DATABASE_URL` с защитой от «задвоенного» URL. **Правило 18/20** соблюдены |
| **`apply_pack56_0_migration`** (16.06.2026) | `applicant.cita_fill_type VARCHAR(16)` + `cita_cert_owner VARCHAR(128)` + `cita_email VARCHAR(128)` + `cita_phone VARCHAR(32)` — окно «Ситы» (контакты для портала записи, отдельные от контактов клиента) |
| **`apply_pack56_2_migration`** (16.06.2026) | `applicant.cita_location VARCHAR(16)` — локация ситы (`Madrid`/`Barcelona`) |
| **`apply_pack56_3_migration`** (16.06.2026) | `applicant.cita_catching BOOLEAN DEFAULT FALSE` — флаг «отлов сит запущен» (заглушка алгоритма; кнопки Start/Stop на плашке «Ситы») |

⚠️ **Pack 43.0, 44.0, 45.0, 46.0 миграций НЕ требуют** — только новый код. Pack 46.0 расширяет JSONB `applicant.education[]` новыми ключами (`diploma_number`, `registration_number`, `protocol_number`, `protocol_date`, `issue_date`, `signers`), но `ALTER TABLE` не нужен — JSONB принимает любые ключи.

---

<a id="шаблоны"></a>

# 8. Активные шаблоны DOCX/PDF

## DOCX `D:\VISA\visa_kit\templates\docx\`

| Файл | Используется | Pack |
|---|---|---|
| `contract_template.docx` (default) + per-company `contracts/by_company/<slug>/` | render_contract → 01_Договор.docx | 16.7 + 25.5 + 29.0 + 33.6 + **41.0-G override** |
| `act_template.docx` | render_act → 02-04_Акт.docx | 14 + 25.5 + 25.6 v2 |
| `invoice_template.docx` | render_invoice → 05-07_Счёт.docx | 14 + 25.5 + 25.6 v2 |
| `employer_letter_template.docx` | render_employer_letter → 08_Письмо.docx | 14 + 25.5 + 33.6 + **40.0-G** |
| `cv_template.docx` | render_cv → 09_Резюме.docx | 20.5 + 25.7 + 37.6 |
| `bank_statement_template.docx` (default) | render_bank_statement → 10_Выписка.docx (Альфа, bik=044525593) | 25.2 + 25.x |
| `bank_statement_template_v2.docx` (Pack 52) | render_bank_statement → 10_Выписка.**pdf** (Альфа Ч/Б, bik=044525593, **новый default для НОВЫХ заявок** через флаг `Application.bank_template_legacy_v1=False`). Минималистичный Ч/Б шаблон без цветных шапок. Сигнатур-таблица 4-колоночная: C0=2500 C1=2000 C2=4000 C3=2448 dxa (специально широкая C2 под inline-печать). R1 gridSpan=2/2 (лейбл «(должность, Ф.И.О....» на одной строке). 3 текстовых маркера `__STAMP_*__` в R0 заменяются на runtime через `_insert_v2_signature_images`: signature.png (floating, x=-60, y=+2, anchor=R0C2 paragraph), stamp_employee.png (inline 55мм, vAlign=BOTTOM ячейки = низ на линию), stamp_bank.png (floating, x=+80, y=-5, anchor=R0C2). После рендера DOCX → `soffice --headless --convert-to pdf` через `render_bank_statement_to_pdf()` → байты PDF. Эндпоинт возвращает `10_Выписка.pdf`. Frontend `DocumentsGrid.tsx` swap'ит filename и иконку по `bank_template_legacy_v1` флагу | **52 серия (base, fix1-fix22)** |
| `bank_statement_template_044525225.docx` (Pack 47) | render_bank_statement → 10_Выписка.docx (Сбер, bik=044525225). Header СБЕР + лого + период; info-блок 2 колонки (владелец/счёт слева, ИТОГО+балансы справа с зелёной линией); tx-таблица 4 колонки [38,55,50,37] с разрывами через trHeight=1100 exact + white right borders; маркер `__EP_BADGE__` для runtime PNG; **Pack 49.0** `<w:tblHeader/>` repeat; **Pack 49.1** footer `word/footer1.xml` с compound IF-field `{ IF { PAGE } = { NUMPAGES } "" "Продолжение..." }` + `<w:updateFields w:val="true"/>` в settings.xml | 47.0–47.23 + 49.0 + 49.1 |
| `bank_statement_template_044525974.docx` (Pack 48) | render_bank_statement → 10_Выписка.docx (ТБанк, bik=044525974). Шапка с tbank_logo.png + реквизиты ТБанка; адаптивный блок паспорта по `applicant.nationality` (RUS — 4-колоночная таблица; иностранец — компактная строка); tx-таблица 6 колонок с multiline датами `DD.MM.YYYY\nHH:MM`; жирные линии sz=8 color=909090 между tx-строками; `<w:tblHeader/>` repeat (Pack 48.4); подпись + печать tbank_signature.png; PT Sans шрифт везде (Pack 48.4) | 48.0 v2 – 48.4 |
| `npd_certificate_template.docx` | render_npd_certificate → 15_Справка_НПД.docx | 17 |
| `npd_certificate_lkn_template.docx` | render_npd_certificate_lkn → 15b_Справка_НПД_ЛКН.docx | 18.3.3 |
| `apostille_template.docx` | render_apostille → 16_Апостиль.docx | 18.9 |
| `tech_opinion_template.docx` | render_tech_opinion → 17_Техническое_заключение.docx | 40.0-G + **43.0** (LLM-перевод RU→ES) + **44.0** (фикс подписи) + **45.0** (LLM-генерация RU) |
| `stdr_template.docx` | render_stdr → 19_СТД-Р.docx (Сведения о трудовой деятельности СФР). Эталон ЭТК_Орлов. T0 (после 2019, 15 слотов table1_rows, кол.6 okz_code), T1 (до 2019, 8 слотов table2_rows), T2 подпись. **Вёрстка Pack 50.23-50.29**: page_break перед до-2019, footer «Страница X из Y», шрифт 5.5pt, центрирование, удаление пустых строк (post_process), ширины T1 2/33/33/33, воздух в шапке. `_stdr_strip_empty_rows` в docx_renderer | **50.9-B + 50.23–50.29** |
| `soo_template.docx` | render_soo → 24_Свидетельство_об_отъезде.docx (СОО, справка СФР РФ-Испания). Шапка 8pt + заголовки 8pt + тело 10pt. naimOnly | **50.12** |
| `apostille_sfr_template.docx` | render_apostille_sfr → 25_Апостиль_СФР.docx (апостиль Минфина/СФР для найма). 4 плейсхолдера: подписант СФР (Высоцкая Ю.В.), дата, номер 77-NNNNN/26, блок Байрамова. naimOnly. docxtpl | **50.20** |

## PDF AcroForm `D:\VISA\visa_kit\templates\pdf\` (Pack 36.0+36.1)

| Файл | Используется | Источник | SHA256 |
|---|---|---|---|
| `MI_T.pdf` | render_mi_t → 11_MI-T.pdf | inclusion.gob.es | `da62b3408decc54cf48a1c7f0eb9c36b0133961708c1df5a5ed70be3b719f012` |
| `DESIGNACION DE REPRESENTANTE. Editable.pdf` | render_designacion → 12_Designacion_representante.pdf | inclusion.gob.es | TODO |
| `DECLARACION RESPONSABLE...pdf` | render_declaracion → 14_Declaracion_antecedentes.pdf | inclusion.gob.es | TODO |
| `COMPROMISO DE ALTA EN LA SEGURIDAD SOCIAL pdf.pdf` | render_compromiso → 13_Compromiso_RETA.pdf | inclusion.gob.es | TODO |
| `EX_17.pdf` | render_ex17 → 17_EX-17_TIE.pdf | inclusion.gob.es | TODO |

⚠️ После заполнения через `pypdf.update_page_form_field_values()` — все формы прогоняются через `flatten_pdf_form()`.

## PDF Code-Generated (без шаблонного файла) — Pack 46.0

В отличие от DOCX/AcroForm в проекте есть **один документ который собирается с нуля через ReportLab** прямо в Python-коде, без шаблонного файла:

| Документ | Рендерер | Шрифты | Pack |
|---|---|---|---|
| Диплом для хурадо (PDF) | `backend/app/services/diploma_pdf_renderer.py:render_diploma_pdf()` | `backend/app/fonts/LiberationSerif-{Regular,Bold,Italic}.ttf` (~1.5 МБ закоммичены) | **46.0** |

**Почему без шаблонного файла:** pixel-perfect раскладка с засечками, кириллица + точные координаты текстовых блоков. DOCX/AcroForm плохо переносят абсолютное позиционирование. Координаты прописаны явно в коде — раскладку подбирали 10 итераций по эталону Кости. См. §3.17 для деталей.

**Шрифты:** Liberation Serif (open-source Times New Roman). Закоммичены в `backend/app/fonts/`. Двухуровневый fallback в рендерере: bundled → системные `/usr/share/fonts/truetype/liberation/` → встроенный `Times-Roman` (без кириллицы, аварийный путь).

## PNG-ассеты для выписок (runtime overlay)

| Файл | Что | Pack |
|---|---|---|
| `templates/docx/sber_ep_card.png` | PNG плашка ЭП Сбера 1134×537, белый фон, лого СБЕР + "Документ подписан электронной подписью*" + синяя полоса "СВЕДЕНИЯ О СЕРТИФИКАТЕ ЭП" + пустая нижняя зона для реквизитов. Вырезан из эталонной выписки Сбера. Runtime overlay через `ep_badge_renderer.py` (см. §3.18) | 47.20 |
| `templates/docx/tbank_signature.png` | PNG 1937×360 @ 300 DPI, печать "Акционерное общество ТБанк / Управление БэК-офис / г. Москва" + подпись Е.С. Шадриной + "С уважением, Руководитель Управления Бэк-офис" текстом слева. Вставлена напрямую в шаблон (не runtime overlay, потому что динамических данных нет) | 48.1 |
| `templates/docx/tbank_logo.png` | PNG лого ТБанка 207×207, жёлтый щит с буквой T. Вставлен в шапку шаблона | 48.1 |
| `templates/docx/assets/v2/signature.png` | Подпись Агеевой 914×587, обрезаны прозрачные поля 79px со всех сторон. Floating-anchor в bank_statement_template_v2.docx (Pack 52). Размер при рендере 38мм | 52-fix3 |
| `templates/docx/assets/v2/stamp_employee.png` | Прямоугольный штамп ДО «Бульвар Дмитрия Донского», ~563×240. Очищен через numpy от серых артефактов сканирования (только синий канал). Inline в bank_statement_template_v2.docx, размер 55мм, сидит в ячейке R0C2 с vAlign=BOTTOM = низом на линию (Pack 52) | 52-fix3 |
| `templates/docx/assets/v2/stamp_bank.png` | Круглая печать «Альфа-Банк» 451×451, без обработки. Floating в bank_statement_template_v2.docx, размер 35мм (Pack 52) | 52-fix3 |

---

<a id="долг"></a>

# 9. Технический долг и Roadmap

## Известный технический долг

1. **Position id=2 геодезист** дублирует уровень с id=13. Tie-breaker работает.
2. **applicant.languages** в модели есть, UI editor отсутствует.
3. **CV занимает 3 страницы**. Можно сократить до 2 если убрать `profile_description`.
4. **company id=15 ИНЖГЕОСЕРВИС** содержит мусор. TODO: ручной cleanup. Также id=1, id=10.
5. **🟡 Railway Postgres volume на 95%** (~475 МБ из 500 МБ Free tier). Основной потребитель — `self_employed_registry`. **Перед каждым SNRIP-импортом — проверять размер volume.** Решение: upgrade до Hobby plan ($5/мес → 5 ГБ).
6. **OPENROUTER_API_KEY** — отозвать старый ключ.
7. **Translation worker auto-timeout** — не реализован. Backlog: `try/finally` с timeout-job >5 минут → FAILED.
8. **Mojibake-кириллица в `backend/app/api/import_package.py`** — комментарии нечитаемы, Python работает (UTF-8). Требует codepage-safe patcher якоря.
9. **apostille_signer_short** в payload-типе ApplicantUpdate (TS-ошибка унаследованная, не блокер).
10. **Pack 41.x отложенки** — консолидация дублирующейся OCR auto-apply логики (41.1), AI-аудит учитывает passport_id_for_ru_docs (41.0-F), отдельный паспорт для НПД-справки (41.0-C.1).
11. **Untracked мусор в репо** (25.05.2026, после Pack 49.1): в корне `D:\VISA\visa_kit\` — `inspect_position.py`, `inspect_director.py`, `inspect_director_data.py`, `inspect_tech_opinion_template.py`, `inspect_applicant.py` (Pack 48), `test_director_helpers.py`, `check_*.py` (4 файла), `debug_workhistory_dup.py`, `sync_app51.py`, `sync_app52.py`, `clear_pm.py`, `positions_export.json`, дубли шаблонов `bank_statement_template_044525225.docx`/`bank_statement_template_044525974.docx`, ассеты `tbank_logo.png`/`tbank_signature.png`/`sber_ep_card.png`/`ep_badge_renderer.py`, build-скрипты `build_tbank_template_v1.py`/`build_tbank_template_v2.py`, `check_tbank.py`, Cyrillic-папка «Добавление тех задания для новых должностей/». Плюс backup файлы в `backend/app/templates_engine/*.bak_pre_pack*` (50+ штук). Требует cleanup-Pack — см. Pack 23.x в Roadmap.

## 🚀 Roadmap

### Pack 57.x — Алгоритм отлова сит (ГЛАВНАЯ ЗАДАЧА, заглушка готова) — TODO

Флаг `applicant.cita_catching` и кнопки Start/Stop уже есть (Pack 56.4). Нужен сам
алгоритм, который при `cita_catching = true` мониторит портал записи и ловит слот.

Требуется уточнить у Кости перед проектированием:
1. **Портал записи** — какой сайт/endpoint (sede консульства / icp.administracionelectronica / другой), есть ли публичный API или только HTML-форма (тогда нужен headless-браузер).
2. **Частота опроса** — раз в N секунд/минут; сколько клиентов параллельно.
3. **Действие при найденном слоте** — (а) автобронь: подставить `cita_phone` (придёт SMS-код) + `cita_email` (подтверждение) + `nie` + `cita_location`, или (б) только уведомить менеджера.
4. **Куда писать результат** — дата/время пойманной ситы (например в `application.submission_date` или новое поле `cita_appointment_at`), статус «поймана».
5. **Роль «с сертификатом»** — что делает сертификат в процессе записи (отдельный поток?).
6. **Где крутится воркер** — Railway worker / cron / отдельный процесс; как стартует/останавливается по флагу `cita_catching`.

### Pack 22.x — Languages editor в Drawer (~30 мин)
Chips/tags input для `applicant.languages`.

### Pack 23.x — Cleanup мусорных шаблонов и БД (~30-60 мин, накопилось)

После 47-48-49 серии в репо накопилось много untracked файлов и `.bak_pre_pack*` бэкапов в `backend/app/templates_engine/`. Также есть мусор в корне репо (`build_tbank_template_v1.py`, `build_tbank_template_v2.py`, `inspect_*.py`, `check_*.py`, `sync_*.py`, дубли png/docx файлов, Cyrillic-папка «Добавление тех задания для новых должностей/»).

- Физически удалить `_RENDERED_test_*`, `_*_original.docx`, `bank_statement_template.before_*.docx`, все `.bak_pre_pack*` (git история сохранена)
- Удалить untracked `inspect_*.py`, `check_*.py`, `sync_*.py`, `clear_pm.py`, `debug_workhistory_dup.py`, `positions_export.json` (одноразовые скрипты для дебага БД, отработали)
- Удалить из корня репо `build_tbank_template_v1.py`, `build_tbank_template_v2.py`, `bank_statement_template_044525225.docx`, `bank_statement_template_044525974.docx`, `tbank_logo.png`, `tbank_signature.png`, `sber_ep_card.png`, `ep_badge_renderer.py` (apply-source файлы, не в репо)
- DELETE company id=1, id=10, id=15 (если не используется)
- Обновить `.gitignore` с паттернами для apply-source и debug-скриптов

### Pack 55.x — Шаблоны для ВТБ (BIK 044525187) и Открытие (BIK 044525985) — TODO (следующая выписка)

⚠️ **Перенумеровано из Pack 50.x → 51.x → 53.x → 55.x:** номер 50 ушёл на NAIM-линию, 51 — на append-mode выписки, 52 — на Ч/Б шаблон Альфы v2, 53 — на перевод выписки RU→ES (combined PDF), 54 — на Sber v2 (Кирьянов + круглая печать + поворот 25°). При возврате к выпискам ВТБ/Открытие — нумеровать как **55.x**.

ВТБ и Открытие уже зарегистрированы в `bank` таблице (id=3 и id=5), но шаблонов выписки нет — клиенты этих банков получают default Альфа-шаблон. По образцу Pack 47 (Сбер v1) / Pack 48 (ТБанк) / Pack 54 (Sber v2):

1. Найти эталонные выписки (через клиента или интернет-образцы)
2. Собрать build-скрипт через python-docx с правильным форматом колонок, шапкой, шрифтом, реквизитами банка
3. Добавить bank-specific postprocessor в `context.py` если нужны специфичные форматы (как для Сбера/ТБанка)
4. `_resolve_bank_statement_template_path` уже generic — изменений не требует
5. **Использовать готовую инфраструктуру из Pack 54:** функция `_add_floating_picture` с kwargs `z_order` + `rotation_deg`, паттерн `_insert_v2_<bank>_signatures(doc, *, mode)` с Этапом 1.5 layout-правок (вызывается ДО проверки `mode=markers_only` чтобы перевод RU→ES получал ту же layout-правку — см. Pack 54.0-fix10).
6. Перевод RU→ES автоматически заработает через ту же кнопку «✨ Перевести выписку» (Pack 53), если в dispatcher `render_bank_statement` будет добавлен elif для нового банка.

**Стандартный чеклист нового банк-шаблона (опытом Pack 54):**
- [ ] PNG-ассеты в `templates/docx/assets/v2_<bank>/` (подпись + печать). НЕ в корне, НЕ в `pack<N>_assets/`!
- [ ] DOCX-шаблон в `templates/docx/bank_statement_template_<BIK>_v2.docx`
- [ ] elif в dispatcher `render_bank_statement` для нового банка
- [ ] функция `_insert_v2_<bank>_signatures(doc, *, mode)` с обязательным mode-handling (fix10 pattern)
- [ ] начальные координаты consrvative — потом подгонка по прод-скрину (Правило 72)
- [ ] SQL-флип `bank_template_legacy_v1=FALSE` для тестовой заявки через Railway Data tab

### Pack 50.X — следующие шаблоны Трудового договора для NAIM (по мере подключения новых компаний)

Архитектура готова (Pack 50.1-G). Добавление нового шаблона = 3 шага (полная инструкция в docstring `employment_contracts_registry.py`):
1. Положить docx в `templates/docx/contracts/naim/by_company/<slug>/employment_contract_template.docx`
2. Добавить запись в `EMPLOYMENT_CONTRACT_TEMPLATES_REGISTRY`
3. (Опц.) Добавить ИНН-маппинг в `EMPLOYMENT_COMPANY_INN_TO_SLUG` — иначе менеджер выберет в модалке вручную

### Pack 26.x — PDF/JPG-импорт реквизитов компании (~2 часа)
PDF — pypdf для текстовых, fallback Vision для скан-PDF. JPG/PNG — Vision-путь.

### Pack 26.x — `tax_id_kpp` рефакторинг (~1 час)
Миграция: добавить колонку `company.tax_id_kpp`, backfill, обновить шаблоны и UI.

### Pack 28 Часть 2 — переключение pipeline на `npd_candidate` (отложено)
`inn_suggest` всё ещё читает `self_employed_registry`. Часть 2: cron/Railway scheduler, admin UI кнопка «Пополнить пул», переключение.

### Pack 28.5 — Реальная дата НПД (когда вернёмся)
ФНС API урезали (Инцидент 19). Варианты: `dt_support_begin` из rmsp-pp (B), бинпоиск (D), гибрид B+D.

### Pack 37.x — будущие улучшения AI-аудита
- Badge `🛂 Аудит: FAIL/WARN/PASS` в карточке заявки на главной странице
- Кнопка «Пересобрать пакет + повторная проверка» (сейчас в 2 шага)
- Подкрутить промпт чтобы не давал WARN на `KAMRONMIRZO vs Kamronmirzo` (false positive)

### Pack 39.x — будущие улучшения Final Submission Audit
- **39.0-E3** — селект для переключения между несколькими прогонами
- **39.1** — Badge `📋 Финальная: FAIL/WARN/PASS` в карточке заявки на главной
- **39.2** — Visual quality check через Vision claude-sonnet-4-5 для печатей/подписей
- **39.3** — Автоудаление документов при `application.deleted_at`

### Translation worker auto-timeout (>5 минут → FAILED)

---

<a id="работает"></a>

# 10. Что точно работает (smoke-tested)

✅ Кнопка ✨ «Подобрать опыт работы» → Pack 30.0 + Pack 37.8 (DN-employer первой записью)
✅ work_history синхронизирован с БД на 3 точках (Pack 37.2 + 37.7)
✅ Position по specialty/level, duties[] снапшотом
✅ Генерация пакета DOCX → CV с DN-employer-ом (Pack 37.6 идемпотентный)
✅ Tags из application.position в боковой панели «Навыки»
✅ Банковская выписка — серая подсветка, жирные суммы, период 3 мес минус 1 день
✅ Сокращения адресов по Минфину 171н во всех документах
✅ Нумерация актов/счетов `АКТ № 04/26`, `Счёт № 04/26`
✅ DN-наниматель первой записью в work_history (БД + CV)
✅ UI кнопка Pack 25.10 в ApplicantDrawer
✅ DIPLOMA OCR замещает `applicant.education`
✅ DOCX-импорт компании через LLM (Pack 26.0)
✅ Корзина с автоудалением через 7 дней (Pack 27.0)
✅ `is_ready_for_pickup`, фикс длинных названий компаний (Pack 34.x)
✅ passport_issuer_ru локализация, отмена зависших переводов, шапка испанского перевода 2 параграфа, латинские инициалы в подписи (Pack 35.x)
✅ **Pack 36.0** — PDF AcroForm flatten на iOS/Telegram preview
✅ **Pack 36.1** — EX-17 TIE форма + `fingerprint_date`
✅ **Pack 37.x — AI Document Audit:**
   - Светофор PASS/WARN/FAIL, polling, 8 fix-handlers, DOCX export
   - `passport_expiry_date` из OCR (37.3), ГОСТ info severity (37.5)
   - work_history sync на 3 точках (37.2/37.7/37.8)
✅ **Pack 39.0 — Final Submission Audit (физическая проверка):**
   - Drag&drop, гибрид extraction (pypdf/Vision/docx2txt), AI-классификатор Haiku-4-5
   - Inline-редактор категории, история версий, дедупликация по SHA256
   - Sonnet-4-5 за ~60 сек, 8 категорий A-H, ~80 правил
   - DOCX-экспорт через RFC 5987
   - ~$0.10 за прогон
✅ **Pack 40.0-G** — autogen `outgoing_number`/`outgoing_date` для employer_letter в `context.py`
✅ **Pack 41.0 A-G — Multi-passport на applicant (база):**
   - `applicant.passports[]` (JSONB) + `passport_id_for_ru_docs` (VARCHAR)
   - PassportsSection.tsx с inline-редактированием + dropdown «Паспорт для русских документов»
   - OCR auto-добавление через `upsert_by_number`
   - Backfill 35 applicant'ов из legacy
✅ **Pack 41.0 H-Q (26.05.2026 вечер) — финал multi-passport + НПД ИФНС + UX:**
   - **41.0-K** — централизованный override RUS+RU_INTERNAL в `build_context`: внутренний паспорт во ВСЕ русские документы (договор + акты + счета + employer_letter + CV + tech_opinion + business_trip + employment_contract + bank_statement + НПД-справка). Pack 41.0-H/I в render_bank_statement откачен (стал избыточным)
   - **41.0-J** — bugfix hourly_rate_rub/hours_per_month для archetype=vozmezdnoe_hourly (ООО КНС ГРУПП, Buki Vedi)
   - **41.0-L** — `_resolve_region_code` Tier 0: извлечение региона из home_address (keyword-таблица 13 регионов, длинные ключи раньше коротких). Plus seed: ИФНС № 29 по г. Москве (Раменки/Очаково/Солнцево/Внуково) — Инна Лясковец получила правильную инспекцию
   - **41.0-M** — `applicant.npd_ifns_name` (ALTER TABLE + модель + API whitelist + приоритет в `build_npd_certificate_context`). Менеджер копирует точное название из service.nalog.ru/addrno.do
   - **41.0-N** — UI: кнопки 📋 «Скопировать адрес» + 🔗 «Определить ИФНС в сервисе ФНС» под home_address, поле «Название ИФНС для НПД-справки» в Drawer
   - **41.0-O** — UX: поле «Название ИФНС» перенесено выше (между NpdCheckBadge и inn_registration_date)
   - **41.0-P** — UX: кнопка 📋 — inline ✓ Скопировано на 2 сек (зелёный border-green-500), без блокирующего alert
   - **41.0-Q** — UX: PassportsSection обёрнут в Section-стиль div (rounded-md p-4 + bg-secondary + border) — больше не висит в воздухе
✅ **Pack 42.x — UX-полировка админки:**
   - **42.0** — статус «Документы готовы» только вручную через dropdown
   - **42.1** — кнопка 🗑 Удалить документ клиента (БД + R2) с `window.confirm()`
   - **42.2** — паспорта НЕ перезаписываются при загрузке (каждый паспорт = отдельная запись)
   - **42.3** — Drag-and-drop в секцию «Документы клиента»
✅ **Pack 43.0 — кнопка «✨ Сгенерировать испанский» в TechOpinionSection:**
   - Endpoint `POST /admin/positions/{id}/translate-spanish` (НЕ пишет в БД)
   - Sonnet 4.6 через OpenRouter, ~30-60 сек, JSON-выход, Pydantic-валидация
   - 5 ES-полей за раз (description, tools, steps, grounds, contract_clause)
   - `window.confirm()` при перезаписи непустых ES-полей
   - Disabled для новой несохранённой должности
   - ~$0.02-0.05 за прогон
✅ **Pack 44.0 — фикс подписи директора в испанском tech_opinion:**
   - `_short_latin_from_full` в `context.py` переписан для русского порядка ФИО
   - `KAYTUKTI KONSTANTIN PETROVICH` → `K.P. KAYTUKTI` (было `K. PETROVICH`)
   - `Vasilevskaia Anna Vadimovna` → `A.V. VASILEVSKAIA` (было `V. Vadimovna`)
✅ **Pack 45.0 — кнопка «✨ Сгенерировать всё» в шапке PositionDrawer:**
   - Endpoint `POST /admin/positions/generate-russian` (НЕ пишет в БД)
   - Принимает 4 обязательных поля (title_ru, title_es, primary_specialty_id, level)
   - Возвращает 9 RU-полей: duties, tags, profile_description + 5 tech_opinion_*_ru + international_analog_ru
   - title_ru_genitive и salary_rub_default остаются менеджеру
   - Disabled пока не заполнены 4 обязательных поля
   - `window.confirm()` при перезаписи непустых RU-полей
   - Sonnet 4.6 с max_tokens=6144, ~30-50 сек, ~$0.05-0.08 за прогон
✅ **Pack 46.0 — Диплом для хурадо (PDF):**
   - Endpoint `POST /admin/applicants/{id}/education/{idx}/generate-fields` (Sonnet 4.6, ~$0.01-0.02 за прогон)
   - Endpoint `GET /admin/applicants/{id}/education/{idx}/diploma.pdf` (ReportLab, inline PDF, RFC 5987 для кириллического filename)
   - 6 LLM-полей в правильном формате конкретного ВУЗа (не реальные ID): diploma_number, registration_number, protocol_number, protocol_date, issue_date, signers
   - PDF собирается с нуля через ReportLab (НЕТ шаблонного файла) — координаты в коде
   - Раскладка pixel-perfect по эталону Кости (10 итераций подбора)
   - Шрифты Liberation Serif в `backend/app/fonts/` (~1.5 МБ закоммичены, двухуровневый fallback)
   - В `ApplicantDrawer.tsx` подсекция «📄 Диплом для хурадо» на каждую запись education с 6 inputs + 2 кнопками (✨ Сгенерировать + 📄 Скачать диплом)
   - fix1: автосохранение education в БД через `updateApplicant + onSaved()` после ✨ (Инцидент 47)
   - fix2: protocol_number 1-3 (итоговое заседание ГЭК, ~70% число 1)
✅ **Pack 47 серия — Sber statement template (47.0–47.23):**
   - `_resolve_bank_statement_template_path(bik)` — multi-bank resolution в `docx_renderer.py`
   - Шаблон `bank_statement_template_044525225.docx` — header СБЕР + лого + 4-колоночная tx-таблица [38,55,50,37]
   - `_apply_sber_postprocess(bank_data, applicant, session)` — категории, running_balance, формат номера счёта `XXXXX XXX X XXXX XXXXXXX`
   - **Runtime PNG плашка ЭП** через `ep_badge_renderer.py` + static asset `sber_ep_card.png` + PIL overlay 4 строк реквизитов (см. §3.18)
   - 4 фазы рендера: docxtpl Jinja → python-docx tx-clone → `_replace_ep_badge_marker` → `_ensure_paragraphs_at_tc_end` + `_normalize_picture_ids`
   - OOXML compliance (Правило 70) — Word открывает без жалоб, LibreOffice тоже
✅ **Pack 48 серия — TBank statement template (48.0 v2 – 48.4):**
   - `_apply_tbank_postprocess` в `context.py` — `fmt_amount_tbank` (+574.00 ₽), `fmt_amount_tbank_totals` (799 033,00 ₽), детерминированный `card_number` по hash bank_account
   - Шаблон `bank_statement_template_044525974.docx` — tbank_logo.png в шапке + tbank_signature.png внизу
   - Адаптивный блок паспорта по `applicant.nationality` через Jinja-условия `{%p if applicant.nationality == 'RUS' %}` / `{%p else %}` / `{%p endif %}`
   - **Детерминированная генерация договора** (`bank.contract_date_formatted`, `bank.contract_number` — 18-24 мес. назад, 10 цифр)
   - **Детерминированные времена tx** (`tx.date_formatted` = multiline `"DD.MM.YYYY\nHH:MM"`, `tx.settle_date_formatted` аналогично)
   - Жирные линии sz=8 color=909090 между tx-строками
   - PT Sans шрифт везде (заменил Arial)
   - `<w:tblHeader/>` — шапка tx-таблицы повторяется на новых страницах
   - Apply-скрипт Pack 48.0 v2: raw-strings `r'''...'''` + pre-write py_compile + CRLF-aware (Правило 71)
✅ **Pack 49 серия — Sber tblHeader repeat + footer IF-field:**
   - Pack 49.0: `<w:tblHeader/>` в `<w:trPr>` первой строки tx-таблицы — шапка повторяется на новых страницах
   - Pack 49.1: compound Word field `{ IF { PAGE } = { NUMPAGES } "" "Продолжение на следующей странице" }` в footer1.xml. Cached значения пустые (если Word не пересчитает — пусто на всех страницах, не литерал на последней). `<w:updateFields w:val="true"/>` в settings.xml для триггера пересчёта при открытии

✅ **Pack 50.0 серия — типизация заявок Самозанятый/Найм (25-26.05.2026):**
   - `Application.application_type: SAMOZANYATYI | EMPLOYMENT` + миграция + Pydantic (Pack 50.0-A/B)
   - Модалка выбора типа открывается первой при `/admin/applications/new` (Pack 50.0-C3)
   - Badge «НАЙМ» в шапке ApplicationDetail + кнопка «Сменить тип» (Pack 50.0-C4)
   - `ImportPackageDialog` принимает `application_type` (Pack 50.0-C5)

✅ **Pack 50.7 серия — Приказ Т-9 о командировке:**
   - Поля `business_trip_start_date/end_date/destination` на Application + LLM-генератор `business_trip_purpose` (Pack 50.7-A/B)
   - Шаблон `templates/docx/orders/T-9_business_trip_template.docx` + `render_business_trip_order` + фильтр naimOnly (Pack 50.7-C)
   - `applicant.full_name_accusative` (Pack 50.7-C-prep)
   - UI поля в ApplicantDrawer / Application / Company / PositionDrawer (Pack 50.7-D/D2)

✅ **Pack 50.1 серия — Трудовой договор + per-company customization (финал 26.05.2026, коммит 0f3d684):**
   - `company.ogrn` + `company.email` для шапки трудового (Pack 50.1-A/E)
   - `render_employment_contract` + шаблон ФАКТОР СТРОЙ + `employment_contracts_registry.py` (Pack 50.1-C)
   - Фикс шаблона + фильтр документов naimOnly/selfEmployedOnly (Pack 50.1-F1/F3)
   - `applicant.snils` с UI генератором по контрольной сумме (Pack 50.1-F2)
   - Кнопки 🎲 inline внутри input (Pack 50.1-F2-UX)
   - `company.contract_font_family` + post-processor `_replace_fonts_in_docx` (Pack 50.1-H + fix1)
   - `company.employment_contract_template_slug` + `employment_contract_font_family` + универсальная модалка `ContractTemplatePickerModal` (kind=contract|employment) + табы [Самозанятый][Найм] в CompanyDrawer (Pack 50.1-G)

   - Компромисс: ~70-90% Word корректно показывает фразу только на стр.1..N-1, в LibreOffice/Google Docs/Word Online может быть пусто

✅ **Pack 50.32–50.39 (29-30.05.2026):**
   - СТД-Р: полное дублирование записи пересекающей 2020 по правке юриста (50.37 отменяет часть 50.32)
   - Запрет остаточной кириллицы в транслит. инициалах — правило хурадо-промпта (50.36)
   - **ФИЧА автозаполнение заявки из текста менеджера (50.38):** парсер + fuzzy-резолвер справочников (без LLM, устойчив к транслитерации RENKONS→Rekkons) + применение (скан=истина) + город подачи (≠ проживания) + textarea в импорте. Тест Юсуф #67 ✓
   - Город подписания автоподстановка из юр.адреса компании без «г.» (50.39)

✅ **Pack 51 (append-выписка)**: кнопка «Дополнить период» добавляет 2-4 транзакции к существующей выписке без перегенерации (избегает пересчёта подписей/печатей)

✅ **Pack 52 серия — Ч/Б Альфа v2 (DEPLOYED 10.06.2026, серия base + fix1..fix22):**
   - `bank_statement_template_v2.docx` (Альфа Ч/Б, default для НОВЫХ заявок через `bank_template_legacy_v1=False`)
   - 3 PNG (Агеева signature + ДО employee stamp + круглая Альфа stamp) через `_insert_v2_signature_images`
   - **Pack 52-fix17 пивот**: все 3 картинки якорятся к параграфу маркера `__STAMP_EMPLOYEE__` в R0C2. Прямоугольная INLINE + vAlign=BOTTOM = низом на линию. Подпись и круглая floating с маленькими y_off (±5мм)
   - Финальные координаты: signature `x=-60, y=+2, width=38`, stamp_bank `x=+80, y=-5, width=35`
   - **Правило 72** (Прод-LibreOffice = единственный source of truth для floating-anchors)

✅ **Pack 53 — Перевод банковской выписки RU→ES (DEPLOYED 10.06.2026):**
   - `Application.bank_statement_translation_storage_key` (VARCHAR, миграция)
   - POST `/admin/applications/{id}/bank-statement/translate` — async LLM (~30-60 сек, ~$0.05)
   - `render_bank_statement(app, sess, *, for_translation=False)` kwarg
   - `render_bank_statement_combined_to_pdf` (RU PDF + ES PDF → pypdf.merge)
   - GET `/download-file/bank_statement` возвращает combined PDF если translation_storage_key есть
   - Frontend кнопка «✨ Перевести выписку» в дровере для v2-выписок
   - `_insert_v2_signature_images(doc, *, mode)` с `mode="markers_only"` для перевода

✅ **Pack 54 — Sber v2 (DEPLOYED 10.06.2026 поздний вечер, серия base + fix1..fix10):**
   - `bank_statement_template_044525225_v2.docx` (Ч/Б, Кирьянов Е.В., Сбер cells 2400/2700/2900/2204 dxa)
   - `_insert_v2_sber_signatures(doc, *, mode)` диспетчер по template name в `render_bank_statement`
   - Подпись Кирьянова FLOATING `width=25, x=112, y=-3, z_order=10` справа от слова «Подпись» в C2
   - Круглая печать FLOATING `width=35, x=150, y=-10, z_order=20, rotation_deg=25` (повёрнута на 25° по часовой)
   - Линия подписи (bottom-border) убрана runtime через `val=nil` на всех ячейках Row 0
   - Spacer `line=1700 twips` (~30мм) перед footer table опускает таблицу вниз страницы
   - `_add_floating_picture` расширен: kwargs `z_order` (детерминированный relativeHeight) + `rotation_deg` (поворот через `a:xfrm@rot`)
   - **fix10 критический**: layout-правки ДО проверки `mode=markers_only` → combined PDF (RU+ES) симметричный
   - Перевод RU→ES автоматически работает через ту же кнопку «✨ Перевести выписку» (Pack 53)
   - **Правило 73** (`_add_floating_picture` API + координаты + паттерн для следующих банков)

---

<a id="инциденты"></a>

# 11. Критические инциденты — НЕ повторять

**Только активные уроки.** Решённые инциденты которые не повторятся и больше не требуют внимания — в конце списком.

## Инцидент 34 (11.05.2026) — Кириллический инициал в подписи

В шаблоне `{{ applicant.initials_native }}` → «Шахин И.». LLM заменяет «Шахин» на «SAHIN», но «И.» остаётся. Pack 35.10: 4 целевые пары для подписи.

## Инцидент 35 (15-16.05.2026) — PDF AcroForm не рендерятся на iOS/Telegram preview + шаблон содержит ALIYEV

`pypdf.update_page_form_field_values()` обновляет `/V`, но не appearance streams. Pack 36.0 решение через `flatten_pdf_form()`. **Правило 58.**

## Инцидент 36 (18.05.2026) — Кириллический инициал в подписи + СБП регрессия после Pack 35.10

`substitutions.apply()` вызывался ДО LLM, LLM откатывал латиницу обратно. Решение: `substitutions.apply()` ПОСЛЕ LLM в `docx_translator.py`. **Правило 59.**

## Инцидент 37 (18.05.2026) — work_history рассинхрон БД vs CV (Pack 37.x — каскадная серия)

Pack 25.7 `_build_cv_work_history` подменял на лету, БД оставалась со старым. Каскад из 5 паков (37.2/37.6/37.7/37.8). Урок: при логике «подмены на лету» — продумать что будет с источником истины в БД.

## Инцидент 38 (20.05.2026) — Pack 39.0-E2 apply-скрипт: 4 из 6 `str.replace` «применились», но файл не изменился

Fuzzy whitespace/EOL mismatch. `str.replace` не нашёл точное совпадение → молча вернул unchanged → скрипт думал что применил. **Правило 60.**

## Инцидент 39 (20.05.2026) — Кириллический filename в Content-Disposition → UnicodeEncodeError

HTTP headers требуют ASCII. Решение: ASCII fallback в `filename=` + RFC 5987 `filename*=UTF-8''{quote(name)}`. **Правило 61.**

## Инцидент 40 (20.05.2026) — Многоуровневое экранирование `"` в `_repair_truncated_json`

Apply-скрипт записывал Python через triple-quoted string. Внутри функции `elif ch == \\'"\\':` → невалидный Python после записи. **Правило 62.**

## Инцидент 41 (20.05.2026) — PowerShell не находит файлы с `[id]` в пути

PS интерпретирует `[id]` как wildcard pattern. Решение: `Get-Content -LiteralPath`. **Правило 63.**

## Инцидент 42 (22.05.2026) — Pack 41.0-E patcher тихо no-op'ил 3 из 5 правок в context.py

Многострочные якоря с пустыми строками между блоками. Якоря не сматчились, но `str.replace` молча вернул unchanged. Patcher напечатал «applied» для 5 блоков, по факту применилось 2. Серия fix1/fix2/fix3_v2. Падало в проде с `NameError: name 'get_passport_dict_for_ru_docs' is not defined`. **Правило 64.**

## Инцидент 43 (22.05.2026) — Pack 41.0-G в проде: `AttributeError: 'str' object has no attribute 'strftime'`

`passports[].issue_date` хранится в JSONB как ISO-string `"2026-04-10"`. Pack 41.0-G override блок в `render_contract` передавал `_ru_passport["issue_date"]` (строку) в `fmt_date_ru()` который вызывает `strftime`. Hotfix fix2 — конвертация через `date.fromisoformat()`. **Правило 65.**

## Инцидент 44 (24.05.2026) — Pack 43.0 fix1: silent skip 2 правок из-за слишком общего idempotent-маркера

Apply-скрипт A проверял идемпотентность по подстроке `"Pack 43.0"`, скрипт B — по `"translatePositionToSpanish"`. После того как ПЕРВАЯ правка в файле добавляла эти строки (импорт), ВТОРАЯ правка (endpoint / handleTranslate) silent-skip'алась — маркер уже «найден». Лог скрипта показывал `[SKIP] idempotent` для обеих правок, по факту endpoint и функция handleTranslate в файлах не появились. Падало 404 / `handleTranslate is not defined` на проде. Хотфикс — `apply_pack43_0_fix1.py` с **уникальными** маркерами `'@router.post("/{position_id}/translate-spanish")'` и `'async function handleTranslate()'`. **Правило 66.**

## Инцидент 45 (24.05.2026) — Pack 44.0: ложный диагноз из-за молчащего грeps + helper-функции для другого формата данных

Расследование бага «K. PETROVICH» в подписи tech_opinion заняло 6 итераций потому что:
1. `Get-ChildItem -Recurse | Select-String` молча возвращал ноль на присутствующий паттерн (3 раза: `tech_opinion`, `director_full_name_latin_initials`, `_to_director_position_*`). Сделан ложный вывод что переменных «нет в коде». Workaround: `Select-String -LiteralPath`. **Правило 67.**
2. Функция `_short_latin_from_full()` была написана с docstring `"John Robert Smith → J. Smith"` (западный порядок), но в БД хранится `KAYTUKTI KONSTANTIN PETROVICH` (русский порядок). Smoke-test `print(_short_latin_from_full("KAYTUKTI..."))` на реальных данных за 30 сек показал бы проблему — но запустили только когда исчерпали другие гипотезы. **Правило 68.**

## Инцидент 46 (24.05.2026 вечер) — Pack 46.0: `git add` несуществующих файлов молча проходит

`apply_pack46_0_A_backend.py` упал на шаге скачивания шрифтов Liberation Serif (HTTP 404 на угаданном GitHub URL — релизные TTF лежат tar.gz архивом, а не отдельными файлами). Из-за `sys.exit(1)` в шаге fonts скрипт **не дошёл** до создания `diploma_pdf_renderer.py` и `diploma_field_generator.py`. Костя выполнил `git add backend/app/services/diploma_*.py` — PowerShell **не падает** на `git add несуществующий_файл`, просто молча ничего не добавляет в staged. `git commit` ушёл без двух сервисов. На проде Railway упал с `ModuleNotFoundError: No module named 'app.services.diploma_pdf_renderer'` (импорт из `applicants.py` который **успешно применился** через apply B). Hotfix — выдал готовые .py файлы для копирования вручную, второй коммит. **Правило 69.**

## Инцидент 47 (24.05.2026 вечер) — Pack 46.0: PDF читал старые данные из БД после ✨ Сгенерировать

UI: менеджер открыл applicant Демира, через ✨ Подобрать вуз изменил institution на «Ижевский ГТУ» + специальность «Строительство» + год 2015. Потом нажал ✨ Сгенерировать → 6 полей заполнились в state. Жмёт 📄 Скачать диплом → PDF выдал почти пустой документ. Причина: в БД у Демира всё ещё лежали старые данные («РУДН 2010 Прикладная математика», без 6 LLM-полей) — менеджер не нажал «Сохранить». PDF-рендерер читает из БД, а не из state. Hotfix `apply_pack46_0_fix1.py` — после успешной генерации в `handleGenerateDiplomaFields` сразу вызывать `updateApplicant({education: next})` и `onSaved()`. Это PATCH'ит education в БД + parent component перечитывает свежие данные. Дополнительно fix2 — улучшение промпта `protocol_number` (1-3 вместо 1-30, 70% число 1).

## Инцидент 47.A (24.05.2026 поздний вечер) — Pack 47.16/47.17: git silent skip при apply-скриптах

**Что случилось:** Pack 47.16 apply-скрипт копировал `ep_badge_renderer.py` v2 в `backend/app/templates_engine/`, рапортовал `✓ Updated`. Но `git add` ничего не подцепил — потому что **локальный файл уже совпадал с HEAD** (apply скопировал v1 поверх v1, контент идентичный). `git status` показывал только PNG asset, который реально менялся. git commit + push прошли успешно. На Railway деплой подтянул только PNG, но `ep_badge_renderer.py` остался v1.

Потеряли 4 сессии (~1 час) на дебаге "почему плашка не обновляется на проде, хотя я закоммитил Pack 47.16". Каждый раз генерировал выписку, видел старую плашку, пытался применить новый Pack — и так по кругу.

**Причина**: apply-скрипты показывают "Updated: file.py" даже если контент идентичный — `shutil.copy2` не сравнивает, а только копирует. git diff после этого пустой → git add не имеет эффекта → commit пустой по этому файлу.

**Решение**: Правило 69 расширено — `git status` обязателен ПЕРЕД `git commit`. Если ожидаемого файла нет в "Changes to be committed" — apply скопировал v1 поверх v1. Нужно вручную взять файл из выдачи Claude (через скачать кнопку) и положить в backend.

## Инцидент 47.B (24.05.2026 поздний вечер) — Pack 47.15/47.17/47.19: Word ругается на OOXML schema

**Что случилось:** После Pack 47.15 (runtime PNG плашки ЭП через `add_picture`) Word при открытии выписки выдавал диалог "К сожалению не удаётся открыть файл из-за проблем с его содержимым". При нажатии "Сведения" — "Обнаружено неоднозначное сопоставление ячеек. Наличие элементов `<p>` перед каждым `</tc>` является обязательным".

Word предлагал "Восстановить содержимое" — при подтверждении удалял PNG-плашку, оставлял пустое место. LibreOffice **тот же файл открывал без жалоб** — поэтому проблема не была видна на этапе разработки.

Корневая причина — **две** разных:
1. `pic:cNvPr id="0"` дубликат: python-docx ставит id=0 для каждого `add_picture()`. Sber_logo (в шаблоне) и наша плашка ЭП (runtime) обе получали id=0. Word считает дубликат повреждением.
2. `<w:tc>` без завершающего `<w:p>`: `cell_right` ("ИТОГО ПО ОПЕРАЦИЯМ") в Sber-шаблоне заканчивалась на `<w:tbl>` (последняя подтаблица balance_row). По OOXML schema каждая ячейка обязана заканчиваться параграфом.

**Решение**: Правило 70 — после ЛЮБЫХ picture/table edits прогонять документ через `_ensure_paragraphs_at_tc_end` + `_normalize_picture_ids`. Финальная сверка — Word, не LibreOffice (Правило 25).

**Lessons learned**: LibreOffice headless игнорирует ряд OOXML нарушений. Финальная проверка ВСЕГДА в Word. python-docx удобный но рассчитывает на то что разработчик знает schema-инварианты — он их не валидирует.

## Инцидент 48.A (25.05.2026) — Pack 48.0 v1: apply-скрипт писал escape-sequences вместо литералов → SyntaxError на проде

**Что случилось:** apply_pack48_0_tbank_foundation.py (v1) использовал обычные `'''...'''` triple-strings для ANCHOR/INSERT блоков, которые содержали комментарии с `\n` и f-strings с `\u00a0`. Python при чтении apply-скрипта интерпретировал escape-sequences → в строку попадали реальные newline'ы → они попадали в комментарии `context.py` → ломали строковые литералы в комментариях (`"DD.MM.YYYY\nHH:MM"` → буквально с переводом строки внутри). Результат: `SyntaxError: unterminated string literal (detected at line 499)`.

Apply-скрипт честно сообщил `❌ FAIL: context.py НЕ компилируется`. **Но пользователь не остановился** и закоммитил + запушил битый код (потому что PowerShell-блок после команды python включал `git add → git commit → git push` без проверки exit code). Railway задеплоил битый файл — `from .context import build_context` упал при импорте модуля — генерация документов **встала** для **всех клиентов**, не только ТБанк.

**Hotfix**: `git revert HEAD --no-edit` + `git push origin main` восстановило прод за минуту.

Pack 48.0 v2 — переработка с тремя ключевыми фиксами:
1. `r'''...'''` raw-strings везде — escape-sequences остаются литералами
2. CRLF-aware read/write (исходники на Windows CRLF, apply-скрипт нормализует к LF для поиска, при записи восстанавливает)
3. Pre-write `py_compile` check во временный файл — если синтаксис битый, **ничего не пишется** на диск, оригинал не тронут (атомарный apply)

**Бонус-фикс**: sentinel #2 в v1 был `_apply_tbank_postprocess(bank_data` — совпадал и с определением функции, и с вызовом. После применения INSERT_1 (где добавилось определение функции), sentinel #2 уже был найден → INSERT_2 (вызов в `build_context`) silent-skip'нулся. На проде функция была бы добавлена но никогда не вызывалась. В v2 sentinel = `bank_data = _apply_tbank_postprocess(bank_data,` — специфично к вызову.

**Решение**: Правило 71 — apply-скрипты для Python кода: `r'''...'''` + pre-write `py_compile` + CRLF-aware + специфичный sentinel.

**Дополнительное правило**: если apply-скрипт пишет `❌ FAIL` — НЕ выполнять `git add/commit/push`, даже если PowerShell-блок их содержит. Прервать выполнение. (Это уже включено в Правило 69 расширение.)

---


## Инцидент 49 (26.05.2026) — Pack 50.1-H apply: `str.replace()` × 3 раза с одним якорем — поле добавилось 3 раза в один класс

**Что случилось:** Apply-скрипт `apply_pack50_1_H_font.py` должен был добавить поле `contract_font_family: Optional[str] = None` в три класса (`CompanyCreate`, `CompanyUpdate`, `CompanyRead`). Использовал `_replace_once(text, old, new, label)` три раза подряд с **одним и тем же якорем** `"    contract_template_slug: Optional[str] = None  # Pack 29.0"`, наивно полагая что Python найдёт **три разных** вхождения.

`str.replace(old, new, 1)` всегда ищет **с начала строки**. После первой замены в `CompanyCreate` Python:
1. Первый вызов: нашёл якорь в `CompanyCreate`, заменил → добавил `contract_font_family` после `contract_template_slug`. Но **сам якорь остался** (мы дописывали ПОСЛЕ него, не заменяли его)
2. Второй вызов: снова нашёл тот же якорь в `CompanyCreate` (с начала строки), добавил `contract_font_family` ещё раз — теперь дубль
3. Третий вызов: ещё раз — теперь тройной дубль в `CompanyCreate`, при этом `CompanyUpdate` и `CompanyRead` остались **без поля**

В проде endpoint `PATCH /api/admin/companies/{id}` использует `payload.model_dump(exclude_unset=True)` → поле `contract_font_family` в `CompanyUpdate` **отсутствовало** → бэк **молча игнорировал** выбор шрифта при сохранении. UI сохранял, бэк дропал, шрифт не применялся.

**Симптом:** Костя выбирал шрифт в UI → жал «Сохранить» → перезагружал страницу → шрифт сбрасывался обратно. Без ошибок в Network/Console (фронт честно отправлял PATCH с полем, бэк отвечал 200, но поле не попадало в БД из-за Pydantic-фильтрации).

**Диагностика:**
```powershell
python -c "from app.models.company import CompanyUpdate; print('contract_font_family' in CompanyUpdate.model_fields)"
# False  ← вот корень
```

**Фикс:** `apply_pack50_1_H_fix1.py` сделал три вещи:
1. Убрал дубли из `CompanyCreate` (оставил 1 поле)
2. Добавил `contract_font_family` в `CompanyUpdate` (после `contract_template_slug # Pack 29.0` через построчный обход)
3. Добавил `contract_font_family` в `CompanyRead` (тем же способом)

Идемпотентность проверяется через `_fields_count(text, class_name)` helper — считает поле в теле каждого класса. Если cc=1 и cu=1 и cr=1 → skip.

**Урок (расширение Правила 66):** `str.replace(old, new, 1)` не находит «следующее» вхождение — всегда ищет **с начала**. Для нескольких одинаковых правок в разных классах:
- Либо использовать **построчный обход** через `text.split("\n")` с состоянием (in_create/in_update/in_read)
- Либо делать якорь который **меняется** в результате замены (тогда второй вызов найдёт следующее вхождение)
- Либо использовать **разные** якоря для каждого класса (имена классов как часть якоря)

**Также урок:** обязательная sanity-проверка после применения пака — `python -c "from app.models.X import Y; print('field' in Y.model_fields)"`. Если бы я сделал её сразу после Pack 50.1-H — поймал бы баг до пуша в прод.

## Инцидент 50 (09-10.06.2026) — Pack 52-fix4..fix15: local LibreOffice клипует floating-anchor, прод НЕ клипует → подпись и круглая печать улетали в шапку страницы

**Что случилось:** В Pack 52 серии разрабатывалась вставка 3 PNG (подпись Агеевой + 2 печати) в Ч/Б Альфа-шаблон выписки v2 через `<wp:anchor>` floating-картинки. Цель: подпись и круглая печать должны **пересекать линию подписей** (часть выше, часть ниже линии).

В моём локальном LibreOffice превью floating-anchor с большими отрицательными Y (например `<wp:positionV relativeFrom="paragraph"><wp:posOffset>-2000000</wp:posOffset>` = -54мм) **клипуется на границе строки таблицы**. Значения y=-30, y=-50, y=-100, y=-200 рендерятся **идентично** — все упираются в потолок строки 0.

Сделал вывод: «LibreOffice клипает все большие отрицательные Y, нужно подбирать большие значения и смотреть какое сработает». Итерации fix7→fix13: y=-22 → -27 → -33 → -34 → -54 → -114 → -204. Каждый деплой `git push` + Railway-rebuild — а локально превью одно и то же.

**На проде LibreOffice ПОВЁЛ СЕБЯ ИНАЧЕ:** клипинга НЕТ. y=-33 буквально поднял подпись на 33мм выше своего маркера в R0C0 — а маркер в R0C0 находится в середине страницы 2 (после транзакций), поэтому подпись оказалась **в середине транзакций** (в области данных, поверх строк операций). y=-214 для круглой печати в R0C3 буквально поднял её на 214мм = **в шапку страницы 2 над лого «А»**.

Только когда пользователь прислал реальный скрин из проды (с реальными транзакциями) — стало видно что Y буквально соблюдается. До этого все мои локальные превью с пустым шаблоном (1-страничная выписка, маркер в R0C0 в верху страницы) рендерились «как будто клипуется» — из-за того что Y=-33 от маркера в верху страницы все равно остался на странице.

**Корень проблемы:** локальный LibreOffice (snap-пакет 2023?) на Ubuntu в моём sandbox `bash_tool` отличается от прод-LibreOffice (debian apt-package в Docker image на Railway). Разные версии = разное поведение клипинга для floating-anchors с `layoutInCell="0"`.

**Эффект на пользователя:** 4 ложных деплоя (fix9, fix10, fix11, fix12) с одинаковым визуальным результатом на проде (все Y клипуются у меня, на проде разные позиции). Пользователь принимал решения по моим локальным превью → удивлялся когда деплоил.

**Pack 52-fix17 пивот — решение:** все 3 картинки якорятся к **одному и тому же параграфу** — параграфу маркера `__STAMP_EMPLOYEE__` в R0C2. Прямоугольная сидит INLINE в этом параграфе (= ровно на линии благодаря `vAlign=BOTTOM` ячейки). Подпись и круглая floating, anchor = этот же R0C2 paragraph, с маленькими y_off (±5мм). Маркеры в R0C0 и R0C3 чистятся (пустые параграфы остаются).

**Почему сработало:** inline-картинка с `vAlign=BOTTOM` в ячейке делает paragraph_top детерминированным независимо от рендерера — параграф «прижат» к низу ячейки = к линии подписей. Floating'и якорятся к этой же стабильной Y-координате с маленькими дельтами. Локальный/прод-LibreOffice одинаково корректно рендерят малые Y offsets.

**Финальные Y offsets** (после fix17-fix22 итераций по реальным прод-скринам):
- signature: y=+2 (2мм НИЖЕ paragraph → крестится с линией низом)
- bank: y=-5 (5мм выше → крестится верхом)

**Решение → Правило 72**: floating-anchors в DOCX — прод = единственный source of truth, якорить к параграфу с inline-картинкой (стабильная Y-координата), маленькие Y offsets ±5мм.

**Дополнительный урок про итеративный деплой:** когда фича требует визуальной проверки на проде — нельзя итерировать «локально подкрутил → push → ждать деплоя 2-3мин → юзер смотрит → новый push». Лучше большой пивот архитектуры (как fix17) который один раз даёт стабильную базу, а потом маленькие подкрутки (±1-3мм за раз).

---

## Решённые инциденты (НЕ рассказывать в новых сессиях если не спросят прямо)

Полностью устранены, не повторятся, упоминаются только в git history:

- **Инцидент 6** (Pack 25.x) — hardcoded даты в DOCX-шаблоне → Правило 28
- **Инцидент 12** (Pack 27.0) — endpoints забыли зарегистрировать → Правило 38
- **Инцидент 19** (07.05.2026) — ФНС урезали NPD API → блокер для Pack 28 Часть 2
- **Инцидент 20** (09.05.2026) — Pack 19.1a/20.3 endpoint забыли 5 дней → Правило 38
- **Инцидент 21** (10.05.2026) — Position raw SQL INSERT без DB DEFAULT → Правило 43
- **Инцидент 22** (10.05.2026) — `git add -A` потянул stray файлы → Правило 40
- **Инцидент 23** (10.05.2026) — PowerShell 5.1 + cp1251 → Правило 41
- **Инцидент 24** (11.05.2026) — Patcher 34.2 упал на regex → Правила 44-45
- **Инцидент 25** (10.05.2026) — hard line break в per-company договорах → исправлен Pack 33.6
- **Инцидент 30** (11.05.2026) — Translation worker зомби → Pack 35.8 кнопка «Отменить»
- **Инцидент 31** (11.05.2026) — Pack 35.4 каскадный NameError → Правило 54
- **Инцидент 32** (11.05.2026) — Railway Query UI multi-statement drop → Правило 55
- **Инцидент 33** (11.05.2026) — Pack 35.9 patcher проглотил fail → Правило 56

---

```powershell
# Активировать venv
cd D:\VISA\visa_kit\backend
.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway"
$env:PYTHONIOENCODING = "utf-8"
$env:OPENROUTER_API_KEY = "<новый_ключ_после_отзыва_старого>"

# Проверка прода
curl https://visa-kit-production.up.railway.app/docs

# https://visa-kit.vercel.app/admin
```

---

**Версия документа:** 10.0 (10.06.2026 поздний вечер — **Pack 54 (Sber v2) FULLY DEPLOYED — серия base + fix1..fix10**. Sber v2 финализирован: подпись Кирьянова FLOATING 25мм + круглая печать FLOATING 35мм повёрнута на 25° + линия убрана + spacer 30мм + перевод RU→ES автоматом через Pack 53. `_add_floating_picture` расширен kwargs `z_order` и `rotation_deg`. **Новое Правило 73** — `_add_floating_picture` API + координаты Sber v2 + паттерн для следующих банков (ВТБ/Открытие = Pack 55.x). **fix10 критический** — layout-правки перенесены ДО проверки `mode=markers_only`). Прежнее: 9.0 (10.06.2026 вечер — Pack 53 + Pack 54 IN PROGRESS). Прежнее: 8.0 (10.06.2026 — **Pack 51 append-выписка + Pack 52 серия Ч/Б Альфа v2 + PDF + 22 fix-итерации, финал fix22**). Прежнее: 7.0 (03.06.2026 — **Pack 50.40 разбег номеров + Pack 50.41 подсветка непросмотренных документов**). Прежнее: 6.0 (26.05.2026 — **Pack 50.0 типизация + Pack 50.7 Т-9 + Pack 50.1 трудовой договор**).

**Базируется на:** 9.0 (10.06.2026 вечер — Pack 53 + Pack 54 IN PROGRESS) ← 8.0 (10.06.2026 — Pack 51+52) ← 7.0 (03.06.2026 — Pack 50.40+50.41) ← 6.0 (26.05.2026 — Pack 50.0/50.7/50.1 трудовой договор) ← 5.0 (25.05.2026 — Pack 47/48/49 банковские выписки Сбер/ТБанк) ← 4.4 (24.05.2026 — Pack 46.0) ← 4.3 (Pack 43.0+44.0+45.0) ← 4.2 (Pack 40-42) ← 4.1 (Pack 39.0) ← 4.0 (Pack 37.x).

**Следующее обновление:** в конце следующей рабочей сессии.
