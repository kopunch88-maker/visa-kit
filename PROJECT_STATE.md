# VISA KIT — PROJECT_STATE (мастер-документ)

> **🔴 КРИТИЧЕСКАЯ ИНСТРУКЦИЯ для нового Claude:**
> 1. Прочитать **этот файл целиком** перед первым ответом.
> 2. **НЕ дозагружать** старые PROJECT_STATE_*.md, _PATCH.txt, _копия*.md и пр. — этот файл единственный источник правды.
> 3. У Кости (владельца) контекст плотный — отвечать **по делу, без воды**.
> 4. **Перед любыми DROP COLUMN или breaking changes** — Правило 18 (глобальный grep).
> 5. **Перед SQL** — Правило 20 (dump схемы таблицы).
> 6. **Финальная проверка DOCX** — ВСЕГДА в Word, не в LibreOffice (Правило 25).

> **Дата последнего обновления:** 20.05.2026 — Pack 39.0 — Final Submission Audit (физическая проверка пакета документов перед подачей: 6 подпаков A-F полностью готовы и в проде, end-to-end рабочая фича: drag&drop загрузка → AI-классификация → визовый инспектор Sonnet-4-5 проверяет по 8 категориям A-H → findings UI с acknowledge/dismiss → DOCX-экспорт).

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
- **LLM:** OpenRouter `anthropic/claude-sonnet-4.6` (используется и в OCR, и в LLM-переводе, и в AI-аудите)
- **DB:** PostgreSQL на Railway, миграции через `apply_packXX_migration()` функции в `backend/app/db/migrations.py` (не alembic — таблицы создаются через `SQLModel.metadata.create_all()` автоматически + точечные миграции через lifespan)

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

## Сессии 02-04.05.2026 — основа

- **Pack 13.x** — клиентский кабинет, OCR через Claude Vision, GOST транслит, PDF.js
- **Pack 14.x** — bulk import с manual classification + 3 foreign-client doc типа, AI classifier + EGRYL → авто-создание компании, 60+ стран, PDF page picker, nationality
- **Pack 15.x** — испанский перевод документов (jurada-черновик через LLM)
- **Pack 16.x** — банки + генерация банковской выписки. Финал: 16.5e (сокращения адресов по Минфину 171н), 16.7 (договор: merge address + keepNext)
- **Pack 17.x** — ИНН самозанятого (импорт SNRIP-дампа ФНС, 546k+ записей)
- **Pack 18.x** — индикаторы ИНН, fallback при блокировке Railway-IP в ФНС API, batch-чекер, парсинг паспортов, апостиль к справке НПД, отдельное поле `birth_country`
- **Pack 19.x** — справочник вузов (38 шт.) + специальностей (30 ОКСО) + 111 паттернов маппинга должность→специальность, генератор work_history (LegendCompany 71 запись)

## Сессия 05.05.2026 — Position рефакторинг, CV, DN-employer (16 пакетов)

- **Pack 20.x** — Position отвязан от Company, 28 должностей, work_history_generator на Position с duties-snapshot, профессиональный двухколонный CV-шаблон
- **Pack 21.0** — Seed представителей (5) и испанских адресов (11)
- **Pack 25.0-25.7** — починка bank_statement (trHeight без hRule, spacing, bottom border), abbreviate_address во ВСЕХ документах, нумерация акт/счёт по месяцу периода (`АКТ № 04/26`), **Pack 25.7 — DN-наниматель первой записью в CV work_history (динамически, БД не модифицируется)**

## Сессия 06.05.2026 — банковская выписка v2 + UI + DOCX-импорт компаний

- **Pack 25.8-25.12** — переработка `bank_statement_generator.py` (period_end = statement_date - 1 день, hard-фильтр транзакций, СБП себе с РФ-телефоном, онлайн-подписки без географической привязки), миграция `bank_statement_date`, UI секция «Банковская выписка» в `ApplicantDrawer`, DIPLOMA_MAIN всегда замещает `applicant.education`
- **Pack 26.0** — DOCX-импорт реквизитов компании через LLM (один вызов → все поля + склонения директора)
- **Pack 27.0** — Корзина с автоудалением через 7 дней (soft-delete через `deleted_at`, lazy cleanup)

## Сессия 07.05.2026 — Pack 28: пул чистых самозанятых из rmsp-pp

Pack 18.3.4 ставил синтетическую дату НПД. Расследование вскрыло: SNRIP-дамп ФНС содержит **только ИП**, не самозанятых физиков. Все 546k ИНН потенциально засвечивают клиентов через гугл/rusprofile/list-org.

- **Pack 28 Часть 1** — новая таблица `npd_candidate` (отдельно от `self_employed_registry`), `EgrulChecker`, `npd_pool.refill_pool_for_region` (rmsp-pp → EGRUL → NPD), CLI `refill_npd_pool`. Smoke-test: 3 verified для региона 23 (Краснодар) за 70 сек.
- **Часть 2 отложена**: переключение `pipeline.suggest_inn_for_applicant`, cron, admin UI. `inn_suggest` и `inn_accept` всё ещё читают из legacy SNRIP.
- **Открытие:** ФНС урезали NPD API — `registrationDate` больше не возвращается. См. Инцидент 19.

## Сессия 09.05.2026 — Pack 30.0 — фикс 404 на «Подобрать опыт работы»

Pack 19.1a и 20.3 числились «работают», но endpoint `POST /admin/applicants/{id}/regen-work-history` забыли зарегистрировать → 5 дней 404 в проде. Точечная правка в `inn_generation.py`: добавлен импорт `WorkHistorySuggestion` + endpoint-обёртка. См. Инцидент 20.

## Сессия 10.05.2026 — Pack 33.x (10 пакетов)

- **33.0** — page-break перед «Адреса и реквизиты Сторон» через runtime postprocess в `_apply_page_break_before_requisites` (без правки шаблонов)
- **33.1** — алиас `fmt_date_quoted_ru` — починен 500 у avtodom/hayat договоров
- **33.2** — NBSP (`\u00A0`) в long-form датах — Word justify больше не разрывает «2026 г.» через строку
- **33.3** — honest 422 в `/regen-work-history` (4 различные причины None) + PR specialty seed (22 PR-агентства в 7 регионах)
- **33.4** — Position seed (21 specialty × Middle), сократили специальности без должностей с 22 до 1. Hotfixes 33.4.1/33.4.2 для NOT NULL без DB DEFAULT (Инцидент 21, Правило 43)
- **33.5** — Pack 33.4 hotfix для миграций
- **33.6** — починка per-company договоров (полное merge legal_address как в Pack 16.7, но для per-company шаблонов которые появились только в Pack 29.0)
- **33.6.1** — Костя руками доработал 5 per-company договоров в Word
- **33.6.2** — cleanup-Pack: `.gitignore` расширен (12 паттернов), `git rm --cached` 22 stray файла из коммита Pack 33.6.1 (Инциденты 22-23, Правила 40-41)

## Сессия 11.05.2026 — Pack 34.x (УТРО) + 35.x (ВЕЧЕР)

- **Pack 34.x** — каскад багов вокруг компании РЕНКОНС (длинное название ОПФ выявило): wrap в выписке, wrap в адресе договора, justify-растяжку, hard line break из-за `line1/line2` в per-company шаблоне
- **Pack 34.2** — кнопка «Готово к получению» в шапке заявки. Hotfix 34.2.1 — fix regex toggleUrgent (Инцидент 24)
- **Pack 35.0-35.5** — bank statement NPD-фикс, NPD/апостиль в рабочих днях, passport_issuer_ru локализация + миграция, кнопка ✨ Сгенерировать, `_build_bank_context` принимает applicant, СБП-получатель + условный сдвиг
- **Pack 35.6** — `log.exception` в render endpoint — критично для диагностики Шахина
- **Pack 35.7** — hotfix Pack 35.4 (signature change без обновления делегирующей функции, Инцидент 31, Правило 54)
- **Pack 35.8** — кнопка «Отменить зависшие переводы» в `TranslationPanel`
- **Pack 35.9 + 35.9.1 + 35.9.2** — разбиение шапки «город+дата» на 2 параграфа в испанских переводах через post-processing в `docx_translator.translate_docx` (Инцидент 33, Правило 56)
- **Pack 35.10** — копирование rPr в split-функции + латинские инициалы в подписи через `name_substitution`
- **Pack 36.0** — фикс рендера PDF AcroForm-форм на iOS/Telegram preview, новый `flatten_form.py`, заменён `MI_T.pdf` на чистый официальный (Инцидент 35, Правило 58)

## Сессия 16.05.2026 — Pack 36.1 (EX-17 TIE форма)

Добавлен 5-й AcroForm PDF в pdf_forms_engine. Шаблон `templates/pdf/EX_17.pdf` с inclusion.gob.es. Новое поле `Application.fingerprint_date`. Кнопка «Сгенерировать EX-17 TIE» в Drawer админки. Статус «Подана» автоматически ставит флаг `is_filed`.

## Сессия 18.05.2026 — Pack 37.x — AI Document Audit (10 подпаков)

**Главная новая фича сессии** — симуляция приёма документов в консульстве через LLM. Менеджер собирает пакет 16+ документов (DOCX+PDF) → нажимает «🛂 Симуляция приёма документов» → ИИ-аудитор находит несоответствия → менеджер принимает/отклоняет/правит фиксы.

| Pack | Что | Результат |
|---|---|---|
| **37.0-A** | БД: `application_audit_report` + `audit_finding` с индексами. Enum'ы: AuditVerdict (PASS/WARN/FAIL), AuditCategory (identity/financial/company/education/spain_pack/formal), AuditSeverity, AuditFindingStatus | ✅ В проде |
| **37.0-B** | context_builder + document_extractor + prompts (~14579 chars промпта, 80 правил по 6 категориям A-F, few-shot). `_gost_transliterate()` для русских имён, `_looks_like_gibberish()` для детекции мусорных полей. Whitelist 8 fix_actions | ✅ В проде |
| **37.0-B.1** | hotfix gibberish detector (regex `^\d{6,}$` ложно срабатывал на валидные ИНН) + GeneratedDocument поля `filename` / `s3_key` (не `file_name`/`storage_key`) | ✅ В проде |
| **37.0-C** | `auditor.py` — async `run_audit` через BackgroundTasks, рендерит full_package в памяти, извлекает текст из ZIP через `docx2txt + pypdf`. `fix_handlers.py` — 8 handler'ов с Pydantic-валидацией, whitelist полей. 7 API endpoints: POST `/audit/run`, GET reports/findings, accept/dismiss/manual-fix. **Стоимость: ~$0.17 за прогон, длительность 30-200 сек.** | ✅ В проде |
| **37.0-C.1** | hotfix ASCII-safe headers в `openrouter.py` (`_ascii_safe` для site_url/site_name) | ✅ В проде |
| **37.0-C.2** | hotfix JSON repair для обрезанных ответов (`max_tokens` 8192→16384 + `_repair_truncated_json`) | ✅ В проде |
| **37.0-D rev2** | Frontend: страница `/admin/applications/[id]/audit` со светофором FAIL/WARN/PASS, polling каждые 2 сек, summary cards, история прогонов. `AuditFindingCard.tsx` с 3 кнопками Принять/Отклонить/Изменить. `AuditManualFixDialog.tsx` модалка. Кнопка «🛂 Симуляция приёма документов» **под StatusDropdown** в правой панели заявки (`ApplicationDetail.tsx` ~строка 323) | ✅ В проде |
| **37.1** | DOCX export: `services/audit/audit_export.py` через python-docx, endpoint `GET /api/audit/reports/{id}/export.docx` со StreamingResponse, имя файла `audit_<Фамилия>_<Имя>_<YYYY-MM-DD>.docx` с RFC 5987 quoting для кириллицы. Кнопка «Скачать DOCX» на странице `/audit`. Структура отчёта: метаданные, светофор вердикта, сводка, резюме от ИИ, findings по категориям (critical→warning→info) с цветной разметкой и таблицами diff. **Включает все findings** (открытые/принятые/отклонённые/исправленные) | ✅ В проде |
| **37.2** | **Sync `applicant.work_history` с DN-employer на уровне БД.** Был баг: Pack 25.7 `_build_cv_work_history` (templates_engine/context.py:1158) подменял на лету при рендере CV, но БД оставалась со старой компанией → админка показывала старое, аудит ловил как critical. Новый сервис `services/work_history_sync.py` с `sync_dn_work_record_safe()`. Хуки: PATCH `/applications/{id}` и legacy POST `/assign`. Бэкфилл 27 заявок | ✅ В проде |
| **37.3** | `passport_expiry_date` через весь pipeline. OCR-промпт уже распознавал поле (foreign_passport, passport_national), но при apply терялось — в `OCR_FIELD_MAP` его не было. Добавлено в маппинг (2 места в `client_documents_admin.py`, отступ 16 пробелов). Frontend: `useState` + payload + `<Field>` в `ApplicantDrawer.tsx` (grid 2→3 колонки: выдача/окончание/рождение). Бэкфилл по `applicant_document` где `parsed_data.passport_expiry_date` есть. **ВАЖНО:** `ApplicantDocument` имеет `application_id`, не `applicant_id` | ✅ В проде |
| **37.4 → 37.5** | Сначала попытка ограничить ГОСТ-чек постсоветскими странами (37.4). Откачено в 37.5 в пользу другого подхода: применяем ГОСТ ко всем, но переписан пункт A4 в `prompts.py` — LLM создаёт finding только `info` (не warning/critical), и только если латиница в БД отличается И от ГОСТ, И от паспорта. Для китайцев (пиньинь XIA), японцев (Хэпбёрн SATO), арабов — паспорт всегда главнее | ✅ В проде |
| **37.6** | `_build_cv_work_history` идемпотентный. После Pack 37.2 БД уже содержит правильный work_history, но рендерер (Pack 25.7) продолжал подмешивать DN-record поверх → дубликат работодателя в CV с битыми датами «Февраль 2026 → Январь 2026». Добавлена проверка идемпотентности в начало функции с нормализацией кавычек: если `base[0].company == company.full_name_ru` и `period_end='по настоящее время'` — return base без подмешивания | ✅ В проде |
| **37.7** | Хук sync в PATCH `/applicants/{id}` (applicants.py). Pack 37.2 покрывал только изменения `company_id/position_id/contract_sign_date` в Application. Но `applicant.work_history` меняется ещё через PATCH `/applicants/{id}` — после кнопки «Сгенерировать опыт работы» когда менеджер жмёт «Сохранить» в Drawer. Импорт `from app.services.work_history_sync import sync_dn_work_record_safe` перед `@router.patch` endpoint'ом + блок после `session.refresh(applicant)`: если `"work_history" in patch` — найти Application и вызвать sync | ✅ В проде |
| **37.8** | Кнопка «Подобрать опыт работы» сразу даёт DN-employer первой записью. Endpoint `regen_work_history` (inn_generation.py:773) возвращал 1-3 правдоподобных записи от `suggest_work_history()` без DN-employer-а — менеджер видел странную первую работу, должен был сохранить + переоткрыть Drawer. Теперь после `suggest_work_history` сохраняем `result.records` в `applicant.work_history` (через `model_dump()`), commit, ищем Application с company+contract_sign_date, зовём `sync_dn_work_record_safe`, перечитываем `applicant.work_history`, переупаковываем в `WorkRecordSuggestion` список, возвращаем фронту обновлённый `result`. Hotfix `apply_pack37_8_hotfix.py` — anchor имел пустую строку между `raise HTTPException(...404...)` и `result = suggest_work_history(...)` | ✅ В проде |

**Главный итог Pack 37.x:**
1. **Рабочая фича уровня продакшена** — AI-аудит реально находит баги в данных перед подачей.
2. **5 паттернов багов, выявленных самим аудитом, починены отдельными подпаками** (работают вместе):
   - 37.2: work_history рассинхрон БД vs CV — добавлен sync в БД
   - 37.3: passport_expiry_date терялся при OCR apply — добавлен в маппинг и UI
   - 37.5: ГОСТ-чек ругался на китайцев (XIA vs SYA) — переведён в info severity
   - 37.6: дубликат DN-employer в CV после Pack 37.2 — идемпотентность _build_cv_work_history
   - 37.7: work_history не синкался при сохранении Drawer
   - 37.8: «Подобрать опыт работы» не показывала DN-employer первой
3. **Стоимость:** ~$0.17 за прогон, ~$25/мес на 50 заявок × 3 прогона.
4. **27+ заявок засинхронизированы** через бэкфилл скриптами (Pack 37.2 и 37.3).
5. **docx2txt==0.9** добавлен в `backend/requirements.txt`. **python-docx** уже был.

## Сессия 19-20.05.2026 — Pack 39.0 — Final Submission Audit (6 подпаков A-F)

**Главная новая фича сессии** — финальная проверка **физических документов** клиента перед подачей в консульство. В отличие от Pack 37.0 (который проверяет СГЕНЕРИРОВАННЫЕ DOCX из БД), Pack 39.0 проверяет реальные сканы паспорта, апостили, переводы jurada, банковские выписки, которые менеджер собрал в пакет для физической подачи. Менеджер открывает страницу `/admin/applications/{id}/final-check`, перетаскивает документы → AI-классификатор определяет категорию → визовый инспектор Sonnet-4-5 находит хвосты прошлых клиентов, несоответствия ФИО, паспортных данных, сумм.

| Pack | Что | Результат |
|---|---|---|
| **39.0-A** | БД: 3 таблицы (`final_submission_document`, `final_submission_audit_report`, `final_submission_finding`). Привязка к `applicant_id` (документы переиспользуются между подачами одного клиента). История версий через `is_active + previous_version_id + replaced_at`. 6 enum'ов: FinalSubmissionVerdict (PASS/WARN/FAIL), FinalSubmissionCategory (A-H — 8 категорий A_identity/B_numeric/C_dates/D_company/E_translation/F_completeness/G_quality/H_stale), FinalSubmissionSeverity, FinalSubmissionFindingStatus (open/acknowledged/dismissed — БЕЗ fix_action, только пометки), FinalSubmissionDocCategory (21 категория документов), FinalSubmissionExtractionMethod (pypdf/vision/docx2txt/mixed) | ✅ В проде |
| **39.0-A2** | Переименование колонок: `s3_key` → `storage_key` + добавлена `original_storage_key VARCHAR(512)` для хранения PDF-источника после конвертации в DOCX | ✅ В проде |
| **39.0-B** | Upload pipeline: 5 endpoints под router-level `Depends(require_manager)`. POST upload (multipart, дедуп по SHA256, поддержка ZIP с распаковкой `MAX_ZIP_DEPTH=2`), GET list (`include_history` toggle), POST replace (старый → `is_active=False + previous_version_id`), DELETE soft/hard, PATCH category. Лимиты: 200MB/файл, 400MB/запрос. MIME whitelist: pdf/jpg/png/webp/heic/heif/zip/docx. **Hotfix `Pack 39.0-B fix1`** — `uploaded_by VARCHAR` хочет str, а `current_user_id` возвращает int → каст через `str(user_id) if user_id is not None else None` | ✅ В проде |
| **39.0-C** | Extraction pipeline + AI-классификация (BackgroundTask после upload и replace). `extractor.py` (~370 строк): гибрид — pypdf для текстовых PDF (бесплатно), pypdfium2+Claude Vision (`claude-sonnet-4-5`) для сканов до 30 страниц, docx2txt для DOCX. `classifier.py` (~280 строк): Haiku-4-5, 21 категория. `extraction_pipeline.py` оркестратор. Smoke-test: `03_Acta_2.pdf` (80KB) → doc_category="act" с confidence=0.980, extraction_method="pypdf", page_count=1 за ~30 сек | ✅ В проде |
| **39.0-D** | LLM-аудитор визового инспектора. `audit_prompts.py` — промпт «опытный визовый офицер испанского консульства, 15 лет стажа» + 8 категорий A-H с ~80 правилами + JSON-схема + few-shot пример (ALIYEV-проблема: хвосты прошлых клиентов в шаблонах). `audit_context_builder.py` — собирает досье: applicant_db + company_db + computed_checks (gibberish detection, INN/OGRN/BIK format validation, passport expiry vs fingerprint_date) + список активных документов с extracted_text. `audit_runner.py` — sync wrapper + async runner с собственной Session, JSON repair для truncated ответов (как в Pack 37.0 auditor.py), валидация findings. **Smoke-test для applicant=47, application=54:** verdict=FAIL, 23 findings (20 critical + 2 warning + 1 info), duration=88.8 сек, cost=$0.0933, model=claude-sonnet-4-5. Sonnet поймал все хвосты: SAHIN ISMAIL вместо SELIMAJ ERMAL, FAKTOR STROY вместо Агаларов-Девелопмент, контракт 23-10/25 вместо 06-10/25. Inspector_summary: «Не приму: в акте указан другой клиент, другая компания, другой договор. Полная переделка.». **Hotfix `Pack 39.0-D fix1`** — исправлено многоуровневое экранирование `"` в функции `_repair_truncated_json` (питон-код внутри питон-строки сломался на `\\'"\\'` → SyntaxError) | ✅ В проде |
| **39.0-E1** | Frontend часть 1: drag&drop загрузка + список документов + inline-редактор категории. Маршрут `/admin/applications/{id}/final-check` открывается в **новой вкладке** через `window.open` (кнопка «📋 Финальная проверка» в `ApplicationDetail.tsx` под кнопкой Pack 37.0). Page загружает `applicant_id` через `getApplication(id)` → грузит список документов → polling каждые 5 сек на extraction в фоне. Новые компоненты: `FinalSubmissionDropZone.tsx` (dnd events + multiple files + ZIP), `FinalSubmissionDocumentCard.tsx` (карточка с категорией, confidence, extraction_method badge, кнопки Download/Replace/Delete). API клиент в `lib/api.ts`: типы + 5 функций (uploadFinalSubmissionDocuments, listFinalSubmissionDocuments, replaceFinalSubmissionDocument, deleteFinalSubmissionDocument, updateFinalSubmissionDocumentCategory) + `FINAL_DOC_CATEGORY_LABELS` (21 категория ru-labels) | ✅ В проде |
| **39.0-E2** | Frontend часть 2: кнопка запуска аудита + страница findings с acknowledge/dismiss. Кнопка в ДВУХ местах (хедер компактная + большая внизу под списком документов с placeholder/loader/error/result состояниями). Polling каждые 2 сек на `is_running`. Новые компоненты: `FinalSubmissionVerdictBanner.tsx` (PASS/WARN/FAIL баннер с inspector_summary + счётчики + метаданные), `FinalSubmissionFindingCard.tsx` (карточка finding с severity-иконкой, affected_documents клик → R2 download_url в новой вкладке, values_found diff-вью, кнопки **Иду исправлять** жёлтая / **False positive** серая с `prompt()` для опциональной заметки). API: 5 функций (runFinalSubmissionAudit, listFinalSubmissionAuditReports, getFinalSubmissionAuditReport, acknowledgeFinalSubmissionFinding, dismissFinalSubmissionFinding) + `FINAL_AUDIT_CATEGORY_LABELS` (8 категорий с буквами A-H). Помощник `FindingsByCategory` группирует findings по 8 категориям и сортирует внутри по severity (critical>warning>info). **Hotfix `Pack 39.0-E2 fix1`** — 4 из 6 крупных `str.replace` в `apply_pack39_0_E2.py` «применились» (no FAIL), но по факту не изменили файл — fuzzy YAML/whitespace mismatch. Диагноз: ИМПОРТЫ + STATE добавились (помечены has_*=False при старте), но 4 правки (расширение initial useEffect, кнопка в хедере, блок отчёта, FindingsByCategory helper) — нет. Решение: новый идемпотентный fix-скрипт с has_* проверками каждого блока и точечными якорями. Инцидент 38, Правило 60. | ✅ В проде |
| **39.0-F** | DOCX-экспорт отчёта. `services/final_submission/audit_export.py` копирует паттерн Pack 37.1 audit_export.py с адаптациями: 8 категорий A-H в заголовках («A. Личные данные», «B. Суммы и числа», ...), 3 статуса вместо 4, **зачёркнутый текст** для acknowledged/dismissed findings через XML `<w:strike>`, поля Pack 39 (`recommendation`, `affected_documents`, `values_found`, `field_name`), inspector_summary прямо из поля. Endpoint `GET /admin/final-submission/audit/reports/{id}/export.docx` с StreamingResponse и Content-Disposition (ASCII-fallback в `filename=` + RFC 5987 `filename*=UTF-8''` для кириллицы). Frontend: `downloadFinalSubmissionAuditReportDocx(reportId)` через fetch+Blob (нужен auth header), кнопка «Скачать DOCX» в хедере страницы (видна только когда есть готовый отчёт без is_running/error). **Hotfix `Pack 39.0-F fix1`** — `UnicodeEncodeError: 'latin-1' codec` в Starlette при `Content-Disposition: filename="Селимай_Ермал..."` — HTTP headers требуют ASCII. Решение: убран кириллический filename из обычного `filename=`, оставлен только в `filename*=UTF-8''{quote(name)}`. Инцидент 39, Правило 61. | ✅ В проде |

**Главный итог Pack 39.0:**
1. **Полная фича уровня продакшена** — менеджер открывает карточку заявки → клик «Финальная проверка» → drag&drop сканы клиента → AI определяет категории за 10-30 сек → клик «Запустить проверку» → Sonnet-4-5 за ~60 сек находит **все** хвосты прошлых клиентов, расхождения ФИО, паспортных данных, сумм → менеджер отмечает «иду исправлять» или «false positive» → скачивает DOCX-отчёт для архива.
2. **Архитектурное отличие от Pack 37.0:** проверяет физические документы клиента, а не сгенерированные шаблоны. Поэтому 8 категорий A-H с фокусом на cross-document consistency, переводы jurada и хвосты прошлых клиентов в шаблонах. БЕЗ fix_action — менеджер сам идёт переделывать документ (это не правка БД).
3. **Стоимость:** ~$0.10 за прогон (в 5 раз дешевле моих оценок и в 1.7× дешевле Pack 37.0 потому что меньше входного контекста — только extracted_text загруженных документов вместо всего ZIP-пакета).
4. **Гибрид extraction:** pypdf бесплатно для текстовых PDF, Claude Vision только для сканов (до 30 стр).
5. **Привязка к applicant_id** (не application_id) — документы переиспользуются между подачами одного клиента. Это спасает менеджера от повторной загрузки уже сданного апостиля, диплома и т.д.

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
- `title_ru`, `title_ru_genitive`, `primary_specialty_id`, `level` (1-4)
- `salary_rub_default`, `tags`, `duties` (9-11 обязанностей)
- `profile_description` — краткое описание профессии для блока «ПРОФЕССИЯ» в CV

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
- Логика:
  1. Если первая запись = DN-employer (с нормализацией кавычек) и `period_end='по настоящее время'` — return False (no-op, уже синхронизировано)
  2. Иначе: закрыть первую запись месяцем перед `contract_sign_date` (если она была «по настоящее время»)
  3. Создать DN-запись (company.full_name_ru + position.title_ru + duties + period_start = месяц contract_sign_date + period_end = «по настоящее время»)
  4. `applicant.work_history = [dn_record] + fixed_base`, commit

**3 точки sync (Pack 37.2/37.7):**
1. **PATCH `/admin/applications/{id}`** (Pack 37.2) — если затронуты `company_id`/`position_id`/`contract_sign_date`
2. **POST `/admin/applications/{id}/assign`** (Pack 37.2) — всегда
3. **PATCH `/admin/applicants/{id}`** (Pack 37.7) — если в patch есть `work_history` (покрывает: сохранение Drawer, ручное редактирование, повторное сохранение после генерации)

**CV-рендерер `_build_cv_work_history` (Pack 25.7 + Pack 37.6):** оставлен как защитный слой. Идемпотентен — если БД уже содержит DN-employer первой записью с нормализованным сравнением кавычек, делает no-op.

## 3.4 AI Document Audit (Pack 37.x — НОВОЕ)

**Концепция:** симуляция приёма документов в консульстве через LLM. Менеджер на полностью укомплектованной заявке нажимает «🛂 Симуляция приёма документов» → backend рендерит полный пакет в памяти → извлекает текст из ZIP → LLM (Sonnet 4.6) проверяет по 80 правилам в 6 категориях → возвращает findings с verdict (PASS/WARN/FAIL).

**Backend файлы:**
- `app/models/audit.py` — `ApplicationAuditReport`, `AuditFinding`, enum'ы
- `app/services/audit/context_builder.py` — собирает «досье кейса» (applicant + company + 16 рендеренных файлов + OCR оригиналов), `_gost_transliterate`, `_looks_like_gibberish`
- `app/services/audit/document_extractor.py` — извлечение текста из DOCX/PDF через `docx2txt + pypdf`
- `app/services/audit/prompts.py` — системный промпт ~14579 chars, 80 правил, few-shot пример
- `app/services/audit/auditor.py` — `run_audit` через `BackgroundTasks`, рендеринг `build_full_package` в памяти, вызов LLM через `get_llm_client().complete(system, user, model, max_tokens=16384, temperature=0.0)`
- `app/services/audit/fix_handlers.py` — 8 whitelist fix-actions с Pydantic-валидацией: `update_applicant_field`, `swap_first_and_last_name`, `fix_transliteration`, `normalize_name_case`, `update_company_field`, `fix_passport_issuer_ru`, `regenerate_applicant_inn`, `update_education_record`. `APPLICANT_WRITABLE_FIELDS` и `COMPANY_WRITABLE_FIELDS` whitelist
- `app/services/audit/audit_export.py` — DOCX-генератор через python-docx
- `app/api/audit.py` — 7 endpoints: POST `/applications/{id}/audit/run`, GET `/applications/{id}/audit/reports`, GET `/audit/reports/{id}`, POST `/audit/findings/{id}/accept|dismiss|manual-fix`, GET `/audit/reports/{id}/export.docx`

**Frontend файлы:**
- `frontend/app/admin/applications/[id]/audit/page.tsx` — страница со светофором, polling каждые 2 сек пока `is_running`, summary cards, history dropdown, группировка findings по категориям, кнопка «Скачать DOCX»
- `frontend/components/admin/AuditFindingCard.tsx` — 3 кнопки Принять/Отклонить/Изменить
- `frontend/components/admin/AuditManualFixDialog.tsx` — модалка ручного фикса
- `frontend/lib/api.ts` — функции `runAudit`, `listAuditReports`, `getAuditReport`, `acceptAuditFinding`, `dismissAuditFinding`, `manualFixAuditFinding`, `getAuditReportDocxUrl`, лейблы `AUDIT_CATEGORY_LABELS`, `AUDIT_VERDICT_LABELS`
- Кнопка «🛂 Симуляция приёма документов» в `ApplicationDetail.tsx` ~строка 323 **под StatusDropdown** в правой панели

**Стоимость:** ~$0.17 за прогон (~50k input + ~10k output токенов Sonnet 4.6), 30-200 сек.

## 3.5 ИНН-генератор (Pack 17 → 28)

Параллельно живут **ДВА** источника ИНН:

**Источник 1 — `self_employed_registry`** (legacy SNRIP, ежемесячный импорт, 546k+ ИП, ⚠️ гуглятся). **Сейчас используется** в продакшене через `pipeline.suggest_inn_for_applicant`.

**Источник 2 — `npd_candidate`** (Pack 28, новый, через `rmsp-pp.nalog.ru?sk=SZ` → EGRUL отсев → NPD верификация). **Не используется в выдаче** до Pack 28 Часть 2. В пуле: 3 verified для region 23.

**Дата НПД — синтетическая** (Pack 18.3.4: `submission_date - rng.randint(120, 210)` дней). ФНС API урезали (Инцидент 19) — `registrationDate` больше не возвращается. TODO Pack 28.5: гибрид `dt_support_begin` + бинпоиск.

**Pack 28 структура файлов:**
```
app/services/inn_generator/
├── rmsp_client.py    # с fix2 (m=SupportExt)
├── npd_status.py     # registrationDate теперь None
├── egrul_check.py    # Pack 28
├── npd_pool.py       # Pack 28 (главный сервис)
├── pipeline.py       # legacy, в Часть 2 переключим
├── region_picker.py
└── kladr_address_gen.py
```

## 3.6 LLM-перевод на испанский (Pack 15 + 35.9-35.10)

LLM-pipeline берёт **русские** документы и переводит на испанский. Для CV: «Modalidad: Remoto» в каждой работе + блок Declaración в конце.

**Pack 35.9-35.9.2** — разбиение шапки «город + дата» в `_split_city_date_paragraphs(doc)` в `docx_translator.py` (после перевода, регекс на испанскую дату, разбивка на 2 параграфа left-align с deepcopy `<w:rPr>`).

**Pack 35.10** — латинские инициалы в подписи через `_build_applicant_subs` в `name_substitution.py`: пары `(«{last_native} {first_native[0]}.», «{last_latin} {first_latin[0]}.»)` (например «Шахин И.» → «SAHIN I.»).

⚠️ **ВАЖНО:** русские шаблоны НЕ должны содержать испанских блоков (Modalidad/Declaración). Это работа LLM-pipeline.

## 3.7 Банковская выписка (Pack 25.8-25.11 + 35.7)

**Шаблон:** `templates/docx/bank_statement_template.docx`

**Двухфазный рендер** (`docx_renderer.py:render_bank_statement`):
1. **Фаза 1** — docxtpl подставляет шапку через Jinja
2. **Фаза 2** — python-docx клонирует строку-маркер `__TX_*__` для каждой транзакции

**Логика периода (Pack 25.11 финал):**
```python
if statement_date_override is not None:
    statement_date = statement_date_override
else:
    statement_date = today - timedelta(days=random.randint(7, 10))
period_end = statement_date - timedelta(days=1)
period_start = statement_date - relativedelta(months=3)
```

**Pack 25.8 hard-фильтр:** `transactions = [t for t in transactions if period_start <= t["transaction_date"] <= period_end]`

**Pack 35.7:** `_build_bank_context` и `_generate_fresh_bank_context` оба принимают `applicant` (фикс NameError у Шахина).

**UI Pack 25.10:** в `ApplicantDrawer.tsx` секция «Банковская выписка» с date-picker, кнопкой ✨ Auto, кнопкой «Сгенерировать/Перегенерировать выписку».

## 3.8 Нумерация актов/счетов (Pack 25.6 v2)

Два разных поля:
- **`sequence_number`** = `int idx` (1, 2, 3) — для lookup в `docx_renderer.py`
- **`display_number`** = `"04/26"` — в шаблонах акта и счёта

Шаблоны: `АКТ № {{ act.display_number }}`, `Счёт № {{ invoice.display_number }}`.

## 3.9 OCR auto-apply (Pack 13 + 25.12 + 37.3)

**Файл:** `backend/app/api/client_documents_admin.py:_auto_apply_ocr_to_applicant`.

**Правила применения:**
| Поле | Правило |
|---|---|
| `last_name_native`, `first_name_native`, `passport_*`, **`passport_expiry_date`** (Pack 37.3), `birth_*`, `email`, `phone` | Только если в applicant поле пусто |
| **`education`** (DIPLOMA_MAIN) | **ВСЕГДА замещает** (Pack 25.12) |

⚠️ **Pack 37.3:** `passport_expiry_date` теперь в `OCR_FIELD_MAP` в двух местах (под `passport_issue_date` с отступом 16 пробелов).

## 3.10 DOCX-импорт компании (Pack 26.0)

**Бэкенд:** `services/company_extractor.py` + endpoint `POST /admin/companies/extract-from-document`. LLM в одном вызове генерирует все поля компании включая **склонения директора** (именительный/родительный/краткий/латиница) + `director_position_ru` в **родительном падеже**.

**Frontend:** `CompanyImportDialog.tsx` (drag&drop, конфликт ИНН → «Обновить / Создать новую / Отмена»), `CompanyDrawer.tsx` с prop `initialFields?`.

**Pack 26.0.1** — маппинг `inn`/`kpp` → `tax_id_primary`/`tax_id_secondary` через helper `mapFieldsToCompany()`.

## 3.11 Корзина с автоудалением (Pack 27.0)

**Архитектура:** soft-delete через `application.deleted_at`, lazy cleanup записей старше 7 дней при открытии `/admin/trash`.

**3 endpoint'а:** `DELETE /admin/applications/{id}` (soft), `POST /admin/applications/{id}/restore`, `DELETE /admin/applications/{id}/permanent`.

**Permanent delete:** удаляет R2 файлы (3 типа: `applicant_document`, `generated_document`, `uploaded_file`) + 7 связанных таблиц + сама application. **applicant НЕ удаляется**.

**list_applications:** новый параметр `trash: bool = Query(False)`.

## 3.12 PDF AcroForm flatten (Pack 36.0 + 36.1)

**Файл:** `backend/app/pdf_forms_engine/flatten_form.py` → `flatten_pdf_form(bytes) -> bytes`.

После `pypdf.update_page_form_field_values()`:
- Переписывает `/AP /N` каждого Tx-виджета своим content stream (9pt Helvetica, baseline 3.117pt, /Q-центрирование через AFM-таблицу ширин)
- `pdf.generate_appearance_streams()` для radio/checkbox
- `pdf.flatten_annotations()` — впечатывает appearances, удаляет AcroForm + остаточные Widget-аннотации
- Идемпотентно

**Применяется в:** `render_mi_t.py`, `render_designacion.py`, `render_ex17.py` (Pack 36.1), `builder.py` для compromiso/declaracion.

⚠️ **Шаблоны** обязательно с inclusion.gob.es (см. §8). Mobile viewer'ы (Telegram preview, iOS Files) НЕ делают runtime regeneration appearance streams — без flatten рендерятся пустыми.

## 3.13 Final Submission Audit — физическая проверка пакета (Pack 39.0)

**Архитектурное отличие от Pack 37.0:** проверяет реальные сканы документов клиента (паспорт, апостили, переводы jurada, банковские выписки), а не сгенерированные DOCX из БД.

**3 таблицы БД** (привязка к **`applicant_id`**, не application_id):
- `final_submission_document` — физические документы. Колонки: `applicant_id` (FK ON DELETE CASCADE), `application_id` (опционально), `original_filename`, `mime_type`, `file_size_bytes BIGINT`, `storage_key`, `original_storage_key`, `sha256`, `doc_category VARCHAR(50)`, `doc_category_confidence NUMERIC(4,3)`, `doc_category_source` ('ai'/'manual'), `extracted_text TEXT`, `extraction_method` (pypdf/vision/docx2txt/mixed), `extraction_cost_usd NUMERIC(10,4)`, `page_count`, `is_active BOOL`, `previous_version_id` (FK self для истории версий), `replaced_at`, `uploaded_at`, `uploaded_by VARCHAR(255)`. UNIQUE PARTIAL `idx_fsd_applicant_sha_active WHERE is_active=TRUE` — дедупликация по содержимому.
- `final_submission_audit_report` — прогоны проверки. Поля: verdict (PASS/WARN/FAIL), is_running, started_at/finished_at/duration_ms, model_used, prompt_version, input_tokens/output_tokens/vision_pages, cost_usd, summary_counts JSON, **`inspector_summary`** (одна фраза от инспектора), `included_document_ids INT[]`, `document_categories_snapshot JSONB`, error, triggered_by.
- `final_submission_finding` — findings. category (A-H), severity (critical/warning/info), title/description/`recommendation`, `affected_documents JSONB` (массив {document_id, filename, page}), field_name, `values_found JSONB` (dict key→value для diff-вью), status (open/acknowledged/dismissed — БЕЗ fix_action), resolved_at/resolved_by/resolution_note, sort_order.

**8 категорий проверок A-H** (вместо 6 в Pack 37.0):
- **A_identity** — cross-document consistency ФИО, ДР, паспорта (включая MRZ ICAO 9303)
- **B_numeric** — суммы по договору = акты = счета = выписка, НДС=0 (самозанятый)
- **C_dates** — хронология (договор ДО актов, паспорт +6 мес от fingerprint_date)
- **D_company** — реквизиты компании одинаковы во всех документах
- **E_translation** — переводы jurada для всех русских документов (паспорт, апостиль НПД, диплом)
- **F_completeness** — обязательные документы (passport_main, contract, act, invoice, bank_statement, cv, npd_certificate, apostille, mi_t_form, designacion, compromiso, declaracion, photo_3x4, medical_insurance)
- **G_quality** — `[unreadable]` пометки от OCR, отсутствие печатей/подписей
- **H_stale** — **хвосты прошлых клиентов в шаблонах** (главная проблема: менеджер копирует шаблон, забывает заменить ФИО/ИНН/компанию)

**Гибрид extraction** (`services/final_submission/extractor.py`):
- pypdf для текстовых PDF — **бесплатно**
- pypdfium2 + Claude Vision (`claude-sonnet-4-5`) для сканов — до 30 страниц/документ
- docx2txt для DOCX
- Триггерится BackgroundTask после upload и replace

**AI-классификатор** (`classifier.py`): Haiku-4-5 (дёшево), 21 категория, confidence 0-1, source 'ai'/'manual'. Менеджер может править через PATCH endpoint — source автоматически становится 'manual'.

**LLM-аудитор** (`audit_runner.py` + `audit_prompts.py`):
- Модель: `anthropic/claude-sonnet-4-5`, `max_tokens=32768` (до 100 findings)
- temperature=0.0 для воспроизводимости
- Промпт: «опытный визовый офицер испанского консульства, 15 лет стажа» + 8 категорий A-H с ~80 правилами + JSON-схема + few-shot (ALIYEV-проблема)
- JSON repair для truncated ответов (копия из Pack 37.0)
- Sync wrapper `run_final_submission_audit_in_background(report_id)` для FastAPI BackgroundTasks (внутри asyncio.run)

**API endpoints** (router prefix `/admin`, все защищены `Depends(require_manager)`):
- `POST /admin/applicants/{id}/final-submission/upload` — multipart, ZIP распаковывается
- `GET /admin/applicants/{id}/final-submission/documents?include_history=false`
- `POST /admin/applicants/{id}/final-submission/documents/{doc_id}/replace`
- `DELETE /admin/applicants/{id}/final-submission/documents/{doc_id}?hard=false`
- `PATCH /admin/applicants/{id}/final-submission/documents/{doc_id}/category`
- `POST /admin/applicants/{id}/final-submission/audit/run`
- `GET /admin/applicants/{id}/final-submission/audit/reports`
- `GET /admin/final-submission/audit/reports/{report_id}`
- `POST /admin/final-submission/findings/{finding_id}/acknowledge`
- `POST /admin/final-submission/findings/{finding_id}/dismiss`
- `GET /admin/final-submission/audit/reports/{report_id}/export.docx`

**Frontend** (`app/admin/applications/[id]/final-check/page.tsx`):
- Открывается в **новой вкладке** через `window.open` (кнопка «📋 Финальная проверка» в `ApplicationDetail.tsx` под Pack 37.0)
- Загружает applicant_id через `getApplication(id)`
- Drag&drop зона + список карточек с inline-категорией
- Polling каждые 5 сек на extraction в фоне
- Кнопка «Запустить проверку» в ДВУХ местах (хедер + блок внизу)
- Polling каждые 2 сек на `report.is_running`
- 4 состояния: нет прогона / прогон идёт / ошибка / готовый отчёт с FindingsByCategory
- Кнопки **Иду исправлять** (жёлтая) / **False positive** (серая) с `prompt()` для заметки
- Кнопка «Скачать DOCX» (видна когда отчёт готов) — fetch+Blob с auth header, имя файла `final_check_<Фамилия>_<Имя>_<YYYY-MM-DD>.docx` через RFC 5987

**Стоимость:** ~$0.10 за прогон (Sonnet-4-5), ~$15-25/мес на 50 заявок × 3 прогона. В 1.7× дешевле Pack 37.0 потому что меньше входного контекста (только extracted_text загруженных документов вместо всего ZIP с 16 файлами шаблонов).

---

<a id="бд"></a>

# 4. Активные данные в БД

## Position table — 53 строки (Pack 33.4 +21)

Основные специальности: 08.03.01 Строительство, 09.03.04 Прог. инжен., 38.03.01 Экономика, 38.03.02 Менеджмент, 38.03.06 Торговое дело, 40.03.01 Юриспруденция, 42.03.01 Реклама (PR), 45.03.02 Лингвистика + 21 specialty × Middle от Pack 33.4.

⚠️ **Position id=2 геодезист** дублирует уровень с id=13 на 08.03.01 L2. `SPECIFIC_KEYWORDS` tie-breaker корректно работает.

## representative — 5 активных
TELEPNEVA, BUGARIN, DMITREV, ORLOVA, KORENEVA — все в Барселоне.

## spain_address — 13 активных
11 новых из списка Кости + Balmes 128 (Барселона) + Castelló 5 (Мадрид).

## company table — 18+ записей

Ключевые:
- **id=16** ООО АГАЛАРОВ-ДЕВЕЛОПМЕНТ — Pack 25 сессия
- **id=18** ООО РЕНКОНС ХЭВИ ИНДАСТРИС — триггер каскада багов Pack 34.4-34.7

⚠️ **Мусор для cleanup:** id=1 (`xzcxzc`), id=10 (`gfgdfgdfgfd`), id=15 (ИНЖГЕОСЕРВИС с тестовыми реквизитами).

### Структура полей company

```
tax_id_primary       — ИНН (обязательно)
tax_id_secondary     — КПП (для ОПФ "ООО" — обязательно). ⚠️ Имя обманчивое.
country              — ISO-3 ('RUS', 'KAZ'). У многих legacy в country лежит short_name латиницей.
short_name           — 'ООО "НАЗВАНИЕ"' кириллицей
full_name_ru/es      — 'Общество с ограниченной...' / 'Sociedad de Responsabilidad Limitada...'
legal_address        — юр. адрес одной строкой (после Pack 16.7 — это основной)
legal_address_line1/line2  — legacy, в per-company шаблонах после Pack 33.6 не используется
postal_address       — почт. адрес. Если NULL — берётся legal_address.
director_full_name_ru          — именительный
director_full_name_genitive_ru — родительный (для «в лице ...»)
director_short_ru              — 'Беляев Р.К.' (для актов/счетов)
director_full_name_latin       — GOST 7.79 (Pack 15.1)
director_position_ru           — РОДИТЕЛЬНЫЙ ПАДЕЖ ('Генерального директора')
bank_name, bank_account, bank_bic, bank_correspondent_account
notes                — ОГРН, КПП-историческое
```

⚠️ **ОГРН не имеет отдельного поля** — кладём в `notes`.

## applicant table

⚠️ **Полей `full_name_ru` или `full_name_es` НЕТ.** Реальные поля:
- `last_name_native`, `first_name_native`, `middle_name_native`
- `last_name_latin`, `first_name_latin`
- `passport_number`, `passport_issue_date`, **`passport_expiry_date`** (Pack 37.3), `passport_issuer`, `passport_issuer_ru` (Pack 35.2-35.3)
- `birth_date`, `birth_place_latin`, `birth_country` (Pack 18.10)
- `nationality`, `sex`, `marital_status`
- `inn`, `inn_registration_date`, `inn_source`, `inn_kladr_code`
- `home_country`, `home_address`
- `education: List[EducationRecord]`, `work_history: List[WorkRecord]`, `languages: List[LanguageRecord]`
- `apostille_signer_*` (Pack 18.9)

Когда нужно «полное имя на русском» — `f"{first_name_native} {last_name_native}".strip()`.

## application table

Ключевые поля: `applicant_id`, `company_id`, `position_id`, `representative_id`, `spain_address_id`, `contract_number`, `contract_sign_date`, `contract_sign_city`, `salary_rub`, `bank_statement_date` (Pack 25.9), `bank_transactions_override` (JSON), `submission_date`, **`fingerprint_date`** (Pack 36.1), `nie`, `deleted_at` (Pack 27.0), `is_filed`, `is_archived`, `is_urgent`, `is_paid`, `is_ready_for_pickup` (Pack 34.2).

## ИНН-реестр

- `self_employed_registry`: total ~546k, used минимально, последний импорт от 25.04.2026
- `npd_candidate` (Pack 28): 10 записей, 3 verified (region 23)

## Pack 37 — audit таблицы

- `application_audit_report`: id, application_id, verdict (PASS/WARN/FAIL), model_used, input/output_tokens, cost_usd, started_at, finished_at, duration_ms, is_running, error, triggered_by, summary_counts (JSON)
- `audit_finding`: id, report_id, category, severity, title, description, evidence, field_path, current_value, suggested_value, fix_action, fix_payload (JSON), can_auto_apply, status (open/accepted/dismissed/manually_fixed), resolved_at, resolved_by, resolution_note, sort_order

---

<a id="pipeline"></a>

# 5. Pipeline генерации документов

```
Менеджер → Drawer applicant'а → ✨ «Подобрать опыт работы»
   ↓
POST /admin/applicants/{id}/regen-work-history (Pack 30.0)
   ↓
suggest_work_history():
   - specialty из applicant.education[-1].specialty
   - region из applicant.inn_kladr_code[:2]
   - count 1/2/3, уровни Senior+Middle, Position по (specialty_id, level)
   - LegendCompany по region+specialty
   ↓
Pack 37.8: применяем sync_dn_work_record_safe → DN-employer первой записью
   ↓
WorkHistorySuggestion → менеджер сохраняет
   ↓
Менеджер заполняет компанию+договор+position → PATCH /applications/{id}
   ↓
Pack 37.2 хук: sync_dn_work_record_safe (если изменились company_id/position_id/contract_sign_date)
   ↓
Менеджер «Сгенерировать пакет» → POST /applications/{id}/render-package
   ↓
templates_engine/docx_renderer.py:
   - render_contract → 01_Договор.docx
   - render_act × N → 02-04_Акт.docx (display_number "04/26")
   - render_invoice × N → 05-07_Счёт.docx
   - render_employer_letter → 08_Письмо.docx
   - render_cv → 09_Резюме.docx (Pack 20.5 + 25.7 + 37.6 идемпотентный _build_cv_work_history)
   - render_bank_statement → 10_Выписка.docx (Pack 25.x + 35.7)
   - render_npd_certificate → 15_Справка_НПД.docx
   - render_npd_certificate_lkn → 15b_Справка_НПД_ЛКН.docx
   - render_apostille → 16_Апостиль.docx
   ↓
pdf_forms_engine (Pack 36.0):
   - render_mi_t → 11_MI-T.pdf (flatten_pdf_form)
   - render_designacion → 12_Designacion_representante.pdf
   - render_compromiso → 13_Compromiso_RETA.pdf
   - render_declaracion → 14_Declaracion_antecedentes.pdf
   - render_ex17 → 17_EX-17_TIE.pdf (Pack 36.1)
   ↓
ZIP пакет → R2 storage → доступен через UI

[ОПЦИОНАЛЬНО] Менеджер → 🛂 «Симуляция приёма документов» (Pack 37.0-D)
   ↓
POST /applications/{id}/audit/run → BackgroundTasks
   ↓
build_full_package (в памяти) → document_extractor (текст из ZIP)
   ↓
context_builder (досье кейса) → prompts → LLM Sonnet 4.6
   ↓
Findings в БД → UI /audit с polling, кнопки Принять/Отклонить/Изменить
   ↓
DOCX export через /audit/reports/{id}/export.docx
```

---

<a id="правила"></a>

# 6. Правила проекта (МАСТЕР-СПИСОК)

## Workflow и деплой

### 🔥 Правило 34 — Apply-скрипты `apply_pack*.py` в стиле точечных правок

Стандарт проекта: каждый Pack оформляется отдельным `apply_pack*.py` скриптом который:
1. Делает backup затрагиваемых файлов в `*.bak_pre_pack*`
2. Применяет точечные `str.replace(OLD, NEW, 1)` правки с проверкой `if old not in text → FAIL`
3. Идемпотентен (повторный запуск не делает повторных правок)
4. Поддерживает `--backfill-only` где нужно (для миграций данных)

Скрипты в корне репо `D:\VISA\visa_kit\`, запуск `python apply_pack37_X.py`. После применения — `git status`, точечный `git add <file>`, коммит, push на main → автодеплой Railway+Vercel.

### 🔥 Правило 40 — `git add -A` категорически ЗАПРЕЩЁН

Если в `git status` есть untracked мусор — `git add -A` потащит всё. Перед коммитом: `git status` → чистка untracked (либо локально, либо в `.gitignore`) → точечный `git add <file1> <file2>` (Инцидент 22).

### 🔥 Правило 56 — Patcher должен `sys.exit(1)` при FAIL якоре

Если anchor не нашёлся в `str.replace` — `return 1` или `sys.exit(1)`, **не** `print + pass`. Иначе patcher завершается «успешно», но правка не применилась (Инцидент 33).

### Правило 38 — Smoke-test нового endpoint'а: всегда `/docs` + клик в UI

Импорт сервиса в файле endpoint'а ≠ endpoint зарегистрирован. После деплоя: открыть https://visa-kit-production.up.railway.app/docs → Ctrl+F новый роут → клик в UI → DevTools Network проверить 200. Иначе ловим Инциденты 12, 20.

### Правило 54 — При signature change функции — grep ВСЕХ вызовов

Pack 35.4 правил `_build_bank_context`, но забыл что внутри есть делегирующий вызов `_generate_fresh_bank_context(application, company)` без `applicant`. У клиентов с пустым override — `NameError`. Перед deployment signature change — `grep -rn "имя_функции(" .` (Инцидент 31).

## PowerShell специфика

### Правило 35 — PowerShell ps1 файлы ВСЕГДА в UTF-8 with BOM
Без BOM PS читает как cp1251 → ломается кириллица.

### Правило 39 — Команды для пользователя: реальные пути, без `<placeholder>`
`cd $env:USERPROFILE\Downloads` ✅, `cd C:\Users\<you>\Downloads` ❌ (PS ругается «недопустимые знаки»).

### Правило 41 — PowerShell 5.1 + UTF-8: `[Console]::OutputEncoding` обязательно
`>` редирект mangles UTF-8 на ru-Windows. `::new()` это PS 7+, в PS 5.1 — `New-Object`. HashSet через `-contains` (Инцидент 23).

### Правило 45 — PowerShell `>>` запускает команды параллельно
Провал первой не блокирует остальные. Patcher всегда отдельной командой + проверка вывода (Инцидент 24).

### Правило 48 — Один `git add` на строку
В PowerShell `\` continuation не работает как в bash. Писать `git add file1` на отдельной строке.

## БД и миграции

### Правило 18 — Перед DROP COLUMN или breaking changes — глобальный grep
`Get-ChildItem ... | Select-String -Pattern "имя_поля"` по всему проекту перед удалением.

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
В Pack 25.x ушло 30 минут на дебаг кода, оказалось что в шаблоне `bank_statement_template.docx` были hardcoded даты периода.

### Правило 42 — DOCX шаблоны: первый клиент оставляет следы
Hardcoded имена/должности/специальности первого клиента. Параметризовать всё, не только очевидные поля.

### Правило 57 — `<w:r>` без `<w:rPr>` = Word применяет default стиль
При создании нового run из старого ВСЕГДА копировать `<w:rPr>` через `deepcopy` (Pack 35.10).

### 🔥 Правило 58 — PDF AcroForm-шаблоны только официальные с государственного ведомства
Никогда не сохранять заполненный AcroForm PDF поверх шаблона. SHA256 шаблонов в §8 — обязательный артефакт (Инцидент 35).

### 🔥 Правило 59 — После любого LLM-перевода прогонять `substitutions.apply()` на результате
LLM может откатывать substitution (например кириллический «И.» → «I.» обратно). Прогон `substitutions.apply()` после ответа LLM защищает от реверсии латинских инициалов и меток (Инцидент 36).

### 🔥 Правило 60 — Apply-скрипт с большими `str.replace` блоками: ВСЕГДА верификация after-apply
Точечный `str.replace(OLD, NEW, 1)` может «применился» (no FAIL) но по факту не изменил файл — fuzzy whitespace/EOL mismatch. После апплая ОБЯЗАТЕЛЬНО: `Select-String -Pattern "уникальная_строка_из_NEW"` для каждого блока, чтобы убедиться. Если правок много (5+) — собирать как отдельный verification step в скрипте + has_* проверки каждого блока перед записью (Инцидент 38).

### 🔥 Правило 61 — HTTP-заголовки только ASCII, кириллические значения через RFC 5987
`Content-Disposition: filename="Селимай..."` → `UnicodeEncodeError: 'latin-1' codec can't encode characters` в Starlette. Правильно: `filename="ascii_fallback.docx"; filename*=UTF-8''{urllib.parse.quote(unicode_name)}`. Браузеры понимают `filename*` приоритетнее. Применимо ко всем header values с кириллицей (Инцидент 39).

### 🔥 Правило 62 — Многоуровневое экранирование Python-строк в Python-скрипте: проверять ast.parse сразу
Когда apply-скрипт записывает Python-код через триple-quoted string, лёгко сломать экранирование символов `'` `"` `\\` (особенно внутри regex/JSON-парсера). После создания файла — `python -c "import ast; ast.parse(open('новый_файл.py').read())"`. Если SyntaxError — точный line+column. Часовой fix-цикл превращается в 5-минутный (Инцидент 40).

### 🔥 Правило 63 — PowerShell + квадратные скобки в путях: `-LiteralPath`
`Get-Content frontend\app\admin\applications\[id]\page.tsx` падает с `ObjectNotFound` — PS интерпретирует `[id]` как wildcard. Решение: `Get-Content -LiteralPath "..."`. То же для `Set-Content`, `Test-Path` (Инцидент 41).

## Применение и Apply-скрипты

### Правило 30 — Все разведочные команды одним PowerShell-блоком
При просьбе разведки/grep'а — всегда собирать команды в один блок с `Write-Host "=== N. ==="` разделителями. Не дробить.

### Правило 33 — Apply-скрипты на больших файлах через точные строковые блоки
Не regex с предположениями. Сначала точечный grep структуры (как реально выглядит сигнатура/импорт/JSX), потом apply с точно скопированными строками. После применения — verify-grep на ключевые добавленные строки (Pack 27.0 5 hotfix'ов).

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
`_auto_apply_ocr_to_applicant` обновляет ТОЛЬКО ПУСТЫЕ поля по умолчанию. Для категорий где документ важнее ручной правки (DIPLOMA_MAIN) — явный замещающий путь (Pack 25.12).

### Правило 32 — Frontend для backend-фич сразу
Pack 25.10 первый UI через 4 пакета после backend (25.8). Бэкенд без фронта — отрицательная ценность.

## Уроки общие

- SQLModel **NotNullViolation** на enum'ах в production (Pack 11).
- LLM-перевод: pre-substitution + skip ловушка — явно вызывать `_set_paragraph_text(p, text)` до `continue` (Pack 15).
- SNRIP импорт: lxml + ZIP-stream висит → читать в BytesIO; `execute_values` raw psycopg2 быстрее ORM; `BATCH_SIZE=500` оптимум для прокси Railway.
- `id` в URL `/admin?id=N` — это **application.id**, не applicant.id (закреплено в нескольких сессиях).
- `BackgroundTasks` нуждаются в собственной `Session(engine)` — за пределами HTTP контекста.

---

<a id="миграции"></a>

# 7. Применённые миграции БД

**Все миграции идемпотентны.**

| Pack | Что |
|---|---|
| `migration_pack17_0` | Region + KLADR + диаспоры (10 регионов), CRUD `/api/admin/regions` |
| `migration_pack17_2_4` | SelfEmployedRegistry, RegistryImportLog |
| `migration_pack17_6` | `region_code` в self_employed_registry |
| `migration_pack18_9_0` | `mfc_office.is_universal`, INSERT МФЦ Новоясеневский |
| `migration_pack18_9` | `applicant.apostille_signer_*` |
| `migration_pack18_10` | `applicant.birth_country` (ISO-3) |
| `migration_pack19_0` | University + Specialty + 4 новые таблицы |
| `migration_pack20_0` | DROP `position.company_id`, ADD `primary_specialty_id` + `level` |
| `migration_pack20_2_*` | Position seed (28 должностей в нескольких batch) |
| `migration_pack21_0` | 5 представителей + 11 spain_address |
| `migration_pack25_9` | `application.bank_statement_date` |
| `migration_pack27_0` | `application.deleted_at` |
| `migration_pack33_4` | 21 Position × Middle с realistic duties/tags/salary |
| `migration_pack34_2` | `application.is_ready_for_pickup` |
| `migration_pack35_2` | `applicant.passport_issuer_ru VARCHAR(256)` |
| `migration_pack36_1` | `application.fingerprint_date` |
| **`apply_pack37_0_migration`** | `application_audit_report` + `audit_finding` с индексами |
| **`apply_pack39_0_A_migration`** | 3 таблицы Final Submission: `final_submission_document` + `final_submission_audit_report` + `final_submission_finding` с индексами. Привязка к applicant_id (ON DELETE CASCADE). UNIQUE PARTIAL `idx_fsd_applicant_sha_active WHERE is_active=TRUE` |
| **`apply_pack39_0_A2_migration`** | RENAME `s3_key` → `storage_key` + ADD `original_storage_key VARCHAR(512)` для хранения исходного PDF после конвертации в DOCX |

---

<a id="шаблоны"></a>

# 8. Активные шаблоны DOCX/PDF

## DOCX `D:\VISA\visa_kit\templates\docx\`

| Файл | Используется | Pack |
|---|---|---|
| `contract_template.docx` (default) + per-company `contracts/by_company/<slug>/` | render_contract → 01_Договор.docx | 16.7 + 25.5 + 29.0 + **33.6** |
| `act_template.docx` | render_act → 02-04_Акт.docx | 14 + 25.5 + 25.6 v2 + ручная правка Кости |
| `invoice_template.docx` | render_invoice → 05-07_Счёт.docx | 14 + 25.5 + 25.6 v2 |
| `employer_letter_template.docx` | render_employer_letter → 08_Письмо.docx | 14 + 25.5 + 33.6 |
| `cv_template.docx` | render_cv → 09_Резюме.docx | **20.5 + 25.7 + 37.6** |
| `bank_statement_template.docx` | render_bank_statement → 10_Выписка.docx | **25.2 + 25.x** |
| `npd_certificate_template.docx` | render_npd_certificate → 15_Справка_НПД.docx | 17 |
| `npd_certificate_lkn_template.docx` | render_npd_certificate_lkn → 15b_Справка_НПД_ЛКН.docx | 18.3.3 |
| `apostille_template.docx` | render_apostille → 16_Апостиль.docx | 18.9 |

## PDF AcroForm `D:\VISA\visa_kit\templates\pdf\` (Pack 36.0+36.1)

| Файл | Используется | Источник | SHA256 |
|---|---|---|---|
| `MI_T.pdf` | render_mi_t → 11_MI-T.pdf | inclusion.gob.es | `da62b3408decc54cf48a1c7f0eb9c36b0133961708c1df5a5ed70be3b719f012` |
| `DESIGNACION DE REPRESENTANTE. Editable.pdf` | render_designacion → 12_Designacion_representante.pdf | inclusion.gob.es | TODO |
| `DECLARACION RESPONSABLE...pdf` | render_declaracion → 14_Declaracion_antecedentes.pdf | inclusion.gob.es | TODO |
| `COMPROMISO DE ALTA EN LA SEGURIDAD SOCIAL pdf.pdf` | render_compromiso → 13_Compromiso_RETA.pdf | inclusion.gob.es | TODO |
| `EX_17.pdf` | render_ex17 → 17_EX-17_TIE.pdf | inclusion.gob.es | TODO |

⚠️ **Все PDF-шаблоны AcroForm** должны быть чистыми (без остаточных данных клиента). Проверка:
```powershell
python -c "from pypdf import PdfReader; r=PdfReader('templates/pdf/MI_T.pdf'); ne=[(n,f.get('/V')) for n,f in (r.get_fields() or {}).items() if f.get('/V') not in (None,'','/Off')]; print('non-empty:', len(ne))"
# non-empty: 0
```

После заполнения через `pypdf.update_page_form_field_values()` — все формы прогоняются через `flatten_pdf_form()`.

---

<a id="долг"></a>

# 9. Технический долг и Roadmap

## Известный технический долг

1. **Position id=2 геодезист** дублирует уровень с id=13. Tie-breaker корректно работает.
2. **applicant.languages** в модели есть, UI editor отсутствует. Заполнение — ручное в БД.
3. **CV занимает 3 страницы**. Можно сократить до 2 если убрать `profile_description` блок.
4. **company id=15 ИНЖГЕОСЕРВИС** содержит мусор в реквизитах. TODO: ручной cleanup.
5. **🟡 Railway Postgres volume на 95%** (~475 МБ из 500 МБ Free tier). Основной потребитель — `self_employed_registry` (546k × ~400 МБ). **Перед каждым SNRIP-импортом 25 числа — ОБЯЗАТЕЛЬНО проверить размер volume.** Решение: upgrade до Hobby plan ($5/мес → 5 ГБ).
6. **OPENROUTER_API_KEY** — старый ключ светился в чате (Pack 37 сессия 10+ раз). Отозвать обязательно.
7. **Translation worker auto-timeout** — не реализован. Если воркер падает с exception до записи статуса в БД — запись `IN_PROGRESS` живёт вечно. Пока — кнопка «Отменить зависшие переводы» (Pack 35.8) или SQL DELETE с UPPERCASE статусами. Backlog: `try/finally` с timeout-job >5 минут → FAILED.

## 🚀 Roadmap

### Pack 22.x — Languages editor в Drawer (~30 мин)
Chips/tags input для `applicant.languages`.

### Pack 23.x — Cleanup мусорных шаблонов и БД (~30 мин)
- Физически удалить `_RENDERED_test_*`, `_*_original.docx`, `bank_statement_template.before_*.docx`
- DELETE company id=1, id=10, id=15 (если не используется)

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
- Закодить fix_action для `application.amount_per_month` / `contract_period_months`

### Pack 39.x — будущие улучшения Final Submission Audit
- **Pack 39.0-E3** — селект для переключения между несколькими прогонами (когда их станет много, как в Pack 37.0 audit page)
- **Pack 39.1** — Badge `📋 Финальная: FAIL/WARN/PASS` в карточке заявки на главной странице (как у Pack 37.x)
- **Pack 39.2** — Visual quality check: после текстовой проверки кнопка «Визуальная проверка сканов» прогоняет Vision claude-sonnet-4-5 по критичным документам (passport, apostille) — ищет печати, подписи, обрезанные углы. Дополняет G_quality по реальным изображениям, не только по тексту.
- **Pack 39.3** — Автоудаление документов при `application.deleted_at` (сейчас documents привязаны к applicant, application удаление их не трогает — но если у applicant нет активных application, документы тоже надо чистить)

---

<a id="работает"></a>

# 10. Что точно работает (smoke-tested)

✅ Кнопка ✨ «Подобрать опыт работы» → endpoint `regen-work-history` → Pack 30.0 + **Pack 37.8 (DN-employer первой записью сразу)**
✅ work_history синхронизирован с БД на 3 точках (Pack 37.2 + 37.7): PATCH applications, POST /assign, PATCH applicants
✅ Position по specialty/level, duties[] снапшотом
✅ Генерация пакета DOCX → `09_Резюме.docx` через Pack 20.5 шаблон с DN-employer-ом (Pack 37.6 идемпотентный)
✅ Tags из application.position в боковой панели «Навыки»
✅ Банковская выписка после Pack 25.x + 35.7 — серая подсветка, жирные суммы, период 3 мес минус 1 день
✅ Сокращения адресов по Минфину 171н во всех документах
✅ Нумерация актов/счетов `АКТ № 04/26`, `Счёт № 04/26`
✅ DN-наниматель первой записью в work_history (БД + CV)
✅ UI кнопка Pack 25.10 в ApplicantDrawer
✅ Pack 25.12 — DIPLOMA OCR замещает `applicant.education`
✅ Pack 26.0 — DOCX-импорт компании через LLM
✅ Pack 27.0 — Корзина с автоудалением через 7 дней
✅ Pack 30.0 + 33.0-33.4 + 33.6 — endpoint regen-work-history, page-break, NBSP, honest 422, Position seed, per-company договоры
✅ Pack 34.x — `is_ready_for_pickup`, фикс длинных названий компаний (РЕНКОНС)
✅ Pack 35.x — passport_issuer_ru локализация, отмена зависших переводов, шапка испанского перевода 2 параграфа, латинские инициалы в подписи
✅ **Pack 36.0 — PDF AcroForm flatten** — рендерятся на iOS/Telegram preview
✅ **Pack 36.1 — EX-17 TIE форма** — 5-й AcroForm PDF + `fingerprint_date`
✅ **Pack 37.x — AI Document Audit:**
   - Светофор PASS/WARN/FAIL на странице `/audit`
   - Polling каждые 2 сек пока is_running
   - 8 fix-handlers с whitelist полей
   - DOCX export с цветной разметкой и метаданными
   - **passport_expiry_date** заполняется автоматически из OCR (Pack 37.3)
   - **ГОСТ-чек только info severity** для всех (Pack 37.5)
   - **work_history sync** на всех 3 точках изменения (Pack 37.2/37.7/37.8)
   - **27+ заявок** засинхронизированы через бэкфилл
✅ **Pack 39.0 — Final Submission Audit (физическая проверка пакета):**
   - Drag&drop загрузка физических документов клиента (PDF/JPG/PNG/WEBP/HEIC/DOCX/ZIP) на странице `/admin/applications/{id}/final-check`
   - Гибрид extraction: pypdf бесплатно для текстовых PDF, Vision claude-sonnet-4-5 для сканов до 30 стр, docx2txt для DOCX
   - AI-классификатор Haiku-4-5 определяет категорию из 21 (passport_main/contract/act/.../other) за 10-30 сек в фоне
   - Inline-редактор категории — менеджер правит ошибку AI (source становится 'manual')
   - История версий: replace создаёт новую запись + старая `is_active=False + previous_version_id`
   - Soft/hard delete (soft = `is_active=False`, hard = удаление из R2)
   - Дедупликация по SHA256 (UNIQUE PARTIAL индекс на активные)
   - Визовый инспектор Sonnet-4-5 за ~60 сек проверяет по 8 категориям A-H (~80 правил)
   - **Поймал ALIYEV-проблему** в реальном smoke-тесте: SAHIN ISMAIL вместо SELIMAJ ERMAL, FAKTOR STROY вместо Агаларов-Девелопмент, контракт 23-10/25 вместо 06-10/25
   - Findings UI: 8 секций с категориями, severity иконки, affected_documents clickable, values_found diff-вью, recommendation, кнопки Acknowledge (жёлтый «Иду исправлять») / Dismiss (серый «False positive») с опциональной заметкой
   - DOCX-экспорт `final_check_<Фамилия>_<Имя>_<YYYY-MM-DD>.docx` — все findings (open + acknowledged + dismissed), acknowledged/dismissed зачёркнуты + цветная плашка статуса
   - **Стоимость:** ~$0.10 за прогон (Sonnet-4-5), ~$15-25/мес на 50 заявок × 3 прогона

---

<a id="инциденты"></a>

# 11. Критические инциденты — НЕ повторять

**Все инциденты ниже — это реальные баги в проде или нерабочие сборки. НЕ повторять.**

## Инцидент 6 (Pack 25.x) — Hardcoded даты в DOCX-шаблоне
Pack 25.x: 30 минут дебага кода, оказалось что в `bank_statement_template.docx` были hardcoded даты периода. **Правило 28:** сначала проверить шаблон, потом код.

## Инцидент 12 (Pack 27.0 Stage A) — Endpoints забыли зарегистрировать
Apply-скрипт упал, но silent. Кнопка → 405. **Правило 38:** /docs Swagger + клик в UI.

## Инцидент 19 (07.05.2026) — ФНС урезали NPD API
`registrationDate` больше не возвращается. Часть 2 Pack 28 отложена. Урок: внешние API могут урезаться без уведомления, проверить сырой ответ.

## Инцидент 20 (09.05.2026) — Pack 19.1a/20.3 endpoint забыли 5 дней
`regen-work-history` не был зарегистрирован, но в PROJECT_STATE числился «работает». Smoke-test был через сервисную функцию, не HTTP. **Правило 38.**

## Инцидент 21 (10.05.2026) — Position raw SQL INSERT упал 3 раза на NOT NULL без DB DEFAULT
Pack 33.4: `created_at`, `updated_at`, `profile_description` все NOT NULL без `DEFAULT`. SQLModel `default_factory` работает только через ORM. **Правило 43:** raw SQL INSERT обязан перечислять NOT NULL колонки без DB DEFAULT.

## Инцидент 22 (10.05.2026) — `git add -A` потянул 23 stray файла
Pack 33.6.1: `apply_pack*.ps1`, `*.bak_pre_pack*`, `CLAUDE.md.bak` ушли в коммит. Восстановление — Pack 33.6.2 cleanup + `.gitignore` расширен. **Правило 40.**

## Инцидент 23 (10.05.2026) — PowerShell 5.1 + cp1251 испортил git ls-files
`>` редирект mangles UTF-8 на ru-Windows. Решение: `[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding` + прямой capture (без файлов). **Правило 41.**

## Инцидент 24 (11.05.2026) — Patcher Pack 34.2 упал на regex, PowerShell `>>` скрыл
Regex искал многострочный `toggleUrgent`, а функция была компактная одной строкой. `>>` запустил `npm run build` после провала. **Правила 44-45.**

## Инцидент 25 (11.05.2026) — «Зрительный обман» в договоре оказался hard line break
Pack 16.7 чинил `legal_address_line1/2` в дефолтном шаблоне, но per-company шаблоны (Pack 29.0) скопированы со старой структурой. Pack 33.6 — merge во всех 11 per-company шаблонах. Урок: при копировании шаблона — синхронизировать с base.

## Инцидент 30 (11.05.2026) — Translation worker зомби в IN_PROGRESS
Воркер упал тихо, запись висит. UI крутит крутилку 6 часов. Решение Pack 35.8 — кнопка «Отменить». Backlog: auto-timeout в воркере.

## Инцидент 31 (11.05.2026) — Pack 35.4 каскадный NameError
`_build_bank_context` правился, но забыли что внутри есть `_generate_fresh_bank_context` без `applicant`. У клиентов с пустым override — crash. Pack 35.7 hotfix. **Правило 54.**

## Инцидент 32 (11.05.2026) — Railway Query UI silently drops multi-statement SQL
`SELECT count(*); SELECT min(id);` показал только последний. Я предположил «таблица пустая», но было 145 записей. **Правило 55.**

## Инцидент 33 (11.05.2026) — Pack 35.9 patcher проглотил fail
Patcher завершился exit 0 хотя patch 2 не нашёл якорь (был `print + pass` вместо `sys.exit(1)`). Функция определена, вызов не добавлен → мёртвый код. Pack 35.9.1/35.9.2. **Правило 56.**

## Инцидент 34 (11.05.2026) — Кириллический инициал в подписи
В шаблоне `{{ applicant.initials_native }}` → «Шахин И.». При переводе name_substitution заменяет «Шахин» на «SAHIN», но «И.» остаётся кириллицей. Решение Pack 35.10: 4 целевые пары для подписи в `_build_applicant_subs`.

## Инцидент 35 (15-16.05.2026) — PDF AcroForm не рендерятся на iOS/Telegram preview, шаблон содержит данные ALIYEV
1. `pypdf.update_page_form_field_values()` обновляет `/V`, но не appearance streams `/AP /N`. На iOS/Telegram preview — пустые поля.
2. Шаблон `MI_T.pdf` (639 KB) оказался заполненной формой ALIYEV. В `/V` и `/AP /N` лежали данные.
3. Решение Pack 36.0: `flatten_pdf_form()` переписывает `/AP /N` своим content stream (9pt Helvetica, baseline 3.117pt), генерит appearance для radio/checkbox, `pikepdf.flatten_annotations()`. Заменён шаблон на чистый с inclusion.gob.es. Заодно фикс `ec_map["Sp"]="/SP"` и `"Uh"="/UH"` UPPERCASE on-state. **Правило 58.**

## Инцидент 36 (18.05.2026) — Кириллический инициал в подписи + СБП регрессия после Pack 35.10
После Pack 35.10 инициалы в подписи (`ABIDZHANOV И.`) и СБП-получатель (`BAKHTIYAR Д.`) оставались кириллическими у всех клиентов. Корень: `substitutions.apply()` вызывался ДО LLM, LLM откатывал латиницу обратно на кириллицу. Решение: `substitutions.apply()` ПОСЛЕ LLM в `docx_translator.py`. СБП: добавлен параметр `applicant_short_name_latin` в `generate_default_transactions()`, формируется как `f"{first_latin} {last_latin[0]}."` Pack 35.10+. **Правило 59: после любого LLM-перевода прогонять `substitutions.apply()` на результате.**

## Инцидент 37 (18.05.2026) — work_history рассинхрон БД vs CV (Pack 37.x — каскадная серия)
AI-аудитор Pack 37.0 обнаружил у Икромова (заявка #26) critical finding: в БД `work_history[0]` = старая компания, в CV = DN-employer. Pack 25.7 `_build_cv_work_history` подменял на лету при рендере, но БД оставалась со старым. Каскад из 5 паков:
- **Pack 37.2** — sync_dn_work_record в БД при PATCH applications + бэкфилл 27 заявок
- **Pack 37.6** — `_build_cv_work_history` стал идемпотентным (no-op если БД синхронизирована) — иначе дубликат работодателя в CV «Февраль 2026 → Январь 2026»
- **Pack 37.7** — хук sync в PATCH applicants (когда менеджер сохраняет Drawer)
- **Pack 37.8** — endpoint `regen-work-history` сохраняет результат в БД + sync → фронту возвращается обновлённый список с DN-employer первой записью

Урок: при добавлении логики «подмены на лету» (Pack 25.7) — продумать что будет с источником истины в БД. Лучше сразу синкать в БД при изменении триггерных полей.

## Инцидент 38 (20.05.2026) — Pack 39.0-E2 apply-скрипт: 4 из 6 `str.replace` «применились», но файл не изменился
В `apply_pack39_0_E2.py` было 6 крупных правок page.tsx: расширение импортов + state + 4 больших блока (расширение initial useEffect, polling useEffect+handlers, кнопка в хедере, блок отчёта под списком документов, FindingsByCategory helper). Скрипт отработал без FAIL, sayed «replace применён» × 6 раз. Однако в браузере страница `/final-check` оказалась как E1: нет кнопки «Новый прогон» в хедере, нет блока с отчётом. Диагноз через `Select-String "currentReport|listFinalSubmissionAuditReports|FinalSubmissionVerdictBanner"`: импорты (L24, L36) + state (L68) на месте, остальные 4 блока — нет. Корень: fuzzy whitespace/EOL mismatch — мои якорные строки в OLD были близки но не идентичны реальному содержимому файла (возможно CRLF vs LF после первого apply, или невидимые символы от копипасты). `str.replace` не нашёл точное совпадение → молча вернул unchanged text → скрипт думал что применил. Решение Pack 39.0-E2 fix1: новый идемпотентный fix-скрипт с has_* проверками каждого блока (`has_polling_effect = "currentReport.is_running" in text`) + точечные якоря + поддержка LF/CRLF. **Правило 60.**

## Инцидент 39 (20.05.2026) — Кириллический filename в Content-Disposition → UnicodeEncodeError на latin-1
Pack 39.0-F: эндпоинт `/export.docx` возвращал `500 Internal Server Error` со стектрейсом в Starlette `init_headers`: `UnicodeEncodeError: 'latin-1' codec can't encode characters in position 34-40`. Причина: я задал `Content-Disposition: attachment; filename="Селимай_Ермал...docx"` напрямую. HTTP-заголовки по RFC 7230 — только ASCII. Дополнительно: 500 без CORS headers ломает браузерное сообщение об ошибке — выглядит как CORS-проблема (`Failed to fetch`, `No Access-Control-Allow-Origin`). Решение: ASCII fallback в обычном `filename=` + кириллица в RFC 5987 `filename*=UTF-8''{urllib.parse.quote(name)}`. **Правило 61.**

## Инцидент 40 (20.05.2026) — Многоуровневое экранирование `"` в _repair_truncated_json
Pack 39.0-D apply-скрипт записывал `audit_runner.py` через triple-quoted Python string. Внутри JSON repair функции были строки типа `elif ch == \\'"\\':`. После записи в файл получилось `elif ch == \'"\':` — невалидный Python, SyntaxError на строке 98 при `ast.parse`. Деплой на Railway упал бы целиком (импорт модуля при старте FastAPI). Спасло то что я предупредил пользователя про возможный exscaping issue и попросил прогнать `python -c "import ast; ast.parse(open('audit_runner.py').read()); print('OK')"` ПЕРЕД коммитом — поймали syntax error и выпустили fix-патч за 5 минут. Аналогичная ошибка позже всплыла в самом apply-скрипте (строка 1288 с curl-инструкцией). **Правило 62.**

## Инцидент 41 (20.05.2026) — PowerShell не находит файлы с `[id]` в пути
Целая серия попыток `Get-Content frontend\app\admin\applications\[id]\audit\page.tsx` → `ObjectNotFound: Объект для указанного пути ... не существует или отфильтрован`. Файл существует (виден в Get-ChildItem), но PowerShell интерпретирует `[id]` как wildcard pattern (PS наследует bash-подобный globbing). Затратили 10 минут диагностики прежде чем понять. Решение: `Get-Content -LiteralPath "frontend\app\admin\applications\[id]\audit\page.tsx"`. Применимо ко всем PS командам с путями Next.js App Router (`[id]`, `[slug]`, `[...slug]`). **Правило 63.**

---

```powershell
# Активировать venv (если нужно для миграций или apply-скриптов)
cd D:\VISA\visa_kit\backend
.venv\Scripts\Activate.ps1
$env:DATABASE_URL = "postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway"
$env:PYTHONIOENCODING = "utf-8"
$env:OPENROUTER_API_KEY = "<новый_ключ_после_отзыва_старого>"

# Проверка что прод жив
curl https://visa-kit-production.up.railway.app/docs

# Открыть https://visa-kit.vercel.app/admin → залогиниться → applications
```

---

**Версия документа:** 4.1 (20.05.2026 — добавлен Pack 39.0 Final Submission Audit полным блоком: §3.13 архитектура, миграции A/A2, 6 подпаков A-F в TL;DR, §10 «работает» дополнен, Roadmap Pack 39.x, инциденты 38-41, правила 60-63).

**Базируется на:** 4.0 (18.05.2026 — Pack 37.x AI Document Audit) ← 3.7 (16.05.2026 — Pack 36.0/36.1 + Инцидент 35 + Правило 58) ← 3.6 (Pack 35.x) ← 3.5 (Pack 33.x).

**Следующее обновление:** в конце следующей рабочей сессии. Открытые направления:
- Pack 28 Часть 2 (переключение pipeline на `npd_candidate`)
- Pack 28.5 (реальная дата НПД)
- Pack 22.x (Languages editor в Drawer)
- Pack 23.x (cleanup мусорных шаблонов и БД)
- Pack 26.x (PDF/JPG-импорт реквизитов + tax_id_kpp рефакторинг)
- Зафиксировать SHA256 4 PDF-шаблонов Минюста в §8 (TODO)
- Badge AI-аудита `🛂 FAIL/WARN/PASS` в карточке заявки на главной странице
- **Badge Final Submission `📋 FAIL/WARN/PASS` в карточке заявки** (Pack 39.1)
- **Pack 39.0-E3 — селект истории прогонов** на странице final-check
- **Pack 39.2 — Visual quality check** для печатей/подписей через Vision
- Translation worker auto-timeout (>5 минут → FAILED)
