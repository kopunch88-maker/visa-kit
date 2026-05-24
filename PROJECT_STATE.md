# VISA KIT — PROJECT_STATE (мастер-документ)

> **🔴 КРИТИЧЕСКАЯ ИНСТРУКЦИЯ для нового Claude:**
> 1. Прочитать **этот файл целиком** перед первым ответом.
> 2. **НЕ дозагружать** старые PROJECT_STATE_*.md, _PATCH.txt, _копия*.md и пр. — этот файл единственный источник правды.
> 3. У Кости (владельца) контекст плотный — отвечать **по делу, без воды**.
> 4. **Перед любыми DROP COLUMN или breaking changes** — Правило 18 (глобальный grep).
> 5. **Перед SQL** — Правило 20 (dump схемы таблицы).
> 6. **Финальная проверка DOCX** — ВСЕГДА в Word, не в LibreOffice (Правило 25).

> **Дата последнего обновления:** 24.05.2026 — Pack 43.0 (LLM-перевод RU→ES) + Pack 44.0 (фикс инициалов директора) + Pack 45.0 (✨ Сгенерировать всё).

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

---

<a id="архитектура"></a>

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

## 3.7 Банковская выписка (Pack 25.8-25.11 + 35.7)

**Шаблон:** `templates/docx/bank_statement_template.docx`

**Двухфазный рендер** (`docx_renderer.py:render_bank_statement`):
1. **Фаза 1** — docxtpl подставляет шапку через Jinja
2. **Фаза 2** — python-docx клонирует строку-маркер `__TX_*__` для каждой транзакции

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

**Бизнес-логика после Pack 41.0-G:**
- **01_Договор.docx** → `get_passport_dict_for_ru_docs()` (выбранный менеджером, может быть устаревший — исторический документ)
- **Все остальные документы** → primary через `applicant.passport_*` скаляры

**Override механизм** в `docx_renderer.py render_contract()`:
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

⚠️ **Pack 43.0, 44.0, 45.0 миграций НЕ требуют** — только новый код.

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
| `bank_statement_template.docx` | render_bank_statement → 10_Выписка.docx | 25.2 + 25.x |
| `npd_certificate_template.docx` | render_npd_certificate → 15_Справка_НПД.docx | 17 |
| `npd_certificate_lkn_template.docx` | render_npd_certificate_lkn → 15b_Справка_НПД_ЛКН.docx | 18.3.3 |
| `apostille_template.docx` | render_apostille → 16_Апостиль.docx | 18.9 |
| `tech_opinion_template.docx` | render_tech_opinion → 17_Техническое_заключение.docx | 40.0-G + **43.0** (LLM-перевод RU→ES) + **44.0** (фикс подписи) + **45.0** (LLM-генерация RU) |

## PDF AcroForm `D:\VISA\visa_kit\templates\pdf\` (Pack 36.0+36.1)

| Файл | Используется | Источник | SHA256 |
|---|---|---|---|
| `MI_T.pdf` | render_mi_t → 11_MI-T.pdf | inclusion.gob.es | `da62b3408decc54cf48a1c7f0eb9c36b0133961708c1df5a5ed70be3b719f012` |
| `DESIGNACION DE REPRESENTANTE. Editable.pdf` | render_designacion → 12_Designacion_representante.pdf | inclusion.gob.es | TODO |
| `DECLARACION RESPONSABLE...pdf` | render_declaracion → 14_Declaracion_antecedentes.pdf | inclusion.gob.es | TODO |
| `COMPROMISO DE ALTA EN LA SEGURIDAD SOCIAL pdf.pdf` | render_compromiso → 13_Compromiso_RETA.pdf | inclusion.gob.es | TODO |
| `EX_17.pdf` | render_ex17 → 17_EX-17_TIE.pdf | inclusion.gob.es | TODO |

⚠️ После заполнения через `pypdf.update_page_form_field_values()` — все формы прогоняются через `flatten_pdf_form()`.

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
11. **Untracked мусор в репо** (24.05.2026): `inspect_position.py`, `inspect_director.py`, `test_director_helpers.py`, `inspect_tech_opinion_template.py`, `check_*.py`, `debug_workhistory_dup.py`, `sync_app51.py`, `sync_app52.py`, `clear_pm.py`, `positions_export.json`, папка «Добавление тех задания для новых должностей/». Требует разборки и .gitignore.

## 🚀 Roadmap

### Pack 22.x — Languages editor в Drawer (~30 мин)
Chips/tags input для `applicant.languages`.

### Pack 23.x — Cleanup мусорных шаблонов и БД (~30 мин)
- Физически удалить `_RENDERED_test_*`, `_*_original.docx`, `bank_statement_template.before_*.docx`
- DELETE company id=1, id=10, id=15 (если не используется)
- Разобрать untracked мусор и обновить `.gitignore` (см. техдолг #11)

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
✅ **Pack 41.0 — Multi-passport на applicant:**
   - `applicant.passports[]` (JSONB) + `passport_id_for_ru_docs` (VARCHAR)
   - PassportsSection.tsx с inline-редактированием + dropdown «🇷🇺 Паспорт для договора»
   - OCR auto-добавление через `upsert_by_number`
   - **Бизнес-логика:** только 01_Договор.docx использует passport_id_for_ru_docs (исторический документ), все остальные — primary через скаляр-зеркало
   - Backfill 35 applicant'ов из legacy
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

**Версия документа:** 4.3 (24.05.2026 — Pack 43.0 LLM-перевод RU→ES + Pack 44.0 фикс подписи директора + Pack 45.0 ✨ Сгенерировать всё. Добавлены: §3.16 расширен workflow создания новой должности, Правила 66-68, Инциденты 44-45. Чистка: история до Pack 30 в один параграф, решённые инциденты вынесены в краткий список, Pack 41.x отложенки сжаты в одну строку техдолга).

**Базируется на:** 4.2 (22.05.2026 — Pack 40-42) ← 4.1 (20.05.2026 — Pack 39.0) ← 4.0 (18.05.2026 — Pack 37.x).

**Следующее обновление:** в конце следующей рабочей сессии.
