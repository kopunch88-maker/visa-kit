# VISA KIT — состояние проекта на 03.05.2026 (поздний вечер)

> Передай этот файл в начале нового чата + скажи «продолжаем разработку».

## Контекст

Spain DN visa агентство (~50 заявок/мес, 4 менеджера + Костя владелец).

- Frontend: visa-kit.vercel.app (Next.js 16.2.4)
- Backend: visa-kit-production.up.railway.app (FastAPI, Python 3.12)
- Storage: Cloudflare R2 (account `93b044dabe95d0bf265540653ee681d2`, bucket `visa-kit-storage`)
- LLM: OpenRouter `anthropic/claude-sonnet-4-5`
- DB: PostgreSQL на Railway
- Repo: `D:\VISA\visa_kit\` (локально), GitHub `kopunch88-maker/visa-kit`
- DB URL: `postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway`
- DOCX templates: `D:\VISA\visa_kit\templates\docx\` (НЕ `backend/templates/docx/`!)

---

## ⚠️ КРИТИЧЕСКИЕ ПРАВИЛА для нового Claude (уроки 03.05.2026)

В сессии 03.05.2026 было много правок-возвратов из-за нарушений этих правил.
Зафиксированы — не повторять.

### Правило 1 — посмотри соседний рабочий файл

Прежде чем писать новый endpoint, **всегда** запроси у пользователя содержимое
**одного существующего рабочего endpoint'а** из той же папки. Скопируй оттуда
импорты, prefix роутера, паттерн зависимостей. Не угадывай.

### Правило 2 — реальные имена в проекте VISA KIT

```python
# Сессия БД
from app.db.session import get_session

# Авторизация менеджера
from .dependencies import require_manager  # из app.api.dependencies
# Не существует: app.api.deps, app.security, get_current_user, get_current_admin_user

# Префикс роутеров
router = APIRouter(prefix="/admin/...", ...)
# main.py добавляет /api сам через include_router(router, prefix="/api").
```

### Правило 3 — поля моделей: проверять перед использованием

```powershell
cd D:\VISA\visa_kit\backend
Get-Content app\models\<имя модели>.py
```

Часто ошибался: `Region.diaspora_for_countries` (не `_nationalities`),
`SelfEmployedRegistry.full_name` одной строкой, `kladr_address_gen.generate_address`.

### Правило 4 — публичный API при переписывании модуля

Перед переписыванием — найди ВСЕ файлы которые из него импортируют:

```powershell
Get-ChildItem -Recurse app -Filter *.py | Select-String "from <module> import"
```

Все импортируемые имена должны остаться.

### 🔥 Правило 5 — формат правок: ВСЕГДА полные файлы для замены

**НЕ присылать инструкции типа «найди строку X и добавь Y».** Это **ВСЕГДА**
путает пользователя — он либо вставляет дубль, либо ставит не туда.

**Правильно:** запросить содержимое файла, отдать ПОЛНУЮ новую версию через:

```powershell
Copy-Item -Path "$env:USERPROFILE\Downloads\<file>" -Destination "<path>" -Force
```

**Подправило 5а — уникальные имена файлов:** при отдаче файла который уже отдавался
ранее, всегда давать **новое имя с суффиксом** (`_v2`, `_FIX`, `_PACK18_5`).
Иначе браузер берёт старую версию из кэша Downloads.

**Подправило 5б — diagnostic check после Copy-Item:**

```powershell
Select-String -Path "<file>" -Pattern "<уникальный паттерн новой логики>"
```

Не доверять только `git status` — git может молча проглотить «бинарно
идентичный» файл.

**Подправило 5в — НЕ запускать Copy-Item команды до того как пользователь
скачал файл.** В сессии 03.05.2026 это произошло **3-4 раза**: я давал блок
команд `Remove-Item; Copy-Item`, пользователь запускал блок ДО скачивания
карточки → старое удалили, нового нет → Copy-Item падает. Лучше всегда давать
команды **по одной** с прямым указанием «сначала скачайте файл, потом скопируйте».

### Правило 6 — проверка синтаксиса до отдачи

Перед упаковкой:
```bash
python3 -c "import ast; ast.parse(open('<file>').read())"
```

### Правило 7 — Railway "DB not yet accepting connections"

Если Railway падает с этой ошибкой — БД не успела подняться после рестарта.
Подождать 1-2 мин и нажать **Redeploy** на том же коммите.

### Правило 8 — фронт хранит свой захардкоженный список карточек

При добавлении нового downloadable документа в backend — **обязательно**
проверить `frontend/components/admin/DocumentsGrid.tsx` (массив `DOCUMENTS:
DocItem[]`). Без правки фронта новая карточка в UI **НЕ появится**.

### 🔥 Правило 9 — DOCX-шаблоны: НЕ собирать «по тексту параграфов»

При правке DOCX через `python-docx` — **никогда** не использовать текстовые
замены вслепую (`paragraph.text = "..."`, `replace_in_runs(p, "1", ...)`).

DOCX хранит сложную run-структуру: один параграф = 5-10 runs с разными
шрифтами, табами, drawings, vertAlign, position. Текстовая замена ломает
форматирование.

**Правильно:**
1. Прочитать XML параграфа целиком, понять run-структуру
2. Найти **конкретный run** по атрибутам (sz, position, vertAlign)
3. Заменить ТОЛЬКО `<w:t>` внутри нужного run

### Правило 10 — DOCX в шаблоне ФНС: коды документа

Параграф с кодом документа (КНД 1122035) имеет **5 runs** на одной строке:

```
[0] sz=20 pos=2  — пустой run с drawing (декоративная подчёркнутая линия)
[1] sz=24        — "Код вида документа, удостоверяющего личность: "
[2] sz=24 vertAlign=superscript  — "1" (сноска ¹)
[3] sz=24        — <w:tab/>
[4] sz=20 pos=2  — САМ КОД ДОКУМЕНТА (на подчёркнутой линии)
```

Плейсхолдер `{{ certificate.passport_code }}` строго в **run[4]** (sz=20, position=2).
Если поставить в run[1] — код будет крупным шрифтом не на той позиции, «висит в воздухе».

**Реальные коды (по образцам ФНС):**
- `21` = паспорт гражданина РФ
- `10` = паспорт иностранного гражданина
- `1` рядом с кодом — это надстрочный знак сноски `¹`, НЕ код

### 🔥 Правило 11 — ASYNC vs SYNC endpoints

При интеграции httpx (или любого async-клиента) в FastAPI endpoint — endpoint
должен быть `async def`, не `def`. Замена `def → async def` совместима с
существующим `session: Session = Depends(get_session)` — FastAPI поддерживает
оба варианта, фронт ничего не замечает.

В сессии 03.05.2026 при добавлении Pack 18.2 (live-проверка ФНС) пришлось
переделать `inn_accept` с sync на async — это нормально и заняло минимум.

---

## Текущий статус (03.05.2026, конец дня) — Pack 18.5 backend в проде

### ✅ Задеплоено в production (всё работает)
- Pack 13.x — клиентский кабинет, OCR через Claude Vision, GOST транслит, PDF.js
- Pack 14a — bulk import с manual classification + 3 foreign-client doc типа
- Pack 14b+c — AI classifier + EGRYL → авто-создание компании
- Pack 14b+c FIX 1+2 — миграция enum applicantdocumenttype + auto-apply OCR
- Pack 14 finishing — 60+ стран + PDF page picker + nationality + транслит ✨
- Pack 15.x — испанский перевод документов (jurada-черновик)
- Pack 16.x — банки + генерация банковской выписки
- Pack 17.x — автогенерация ИНН самозанятого (база SNRIP, 546k записей)

### ✅ Pack 17.6 (применено 03.05.2026)
- Колонка `region_code` VARCHAR(2) для всех 546,145 записей
- Частичный индекс `idx_self_employed_region_available`
- Импорт SNRIP пишет `region_code` автоматически (`dump_importer.py:518`)

### ✅ Pack 18.0 (применено 03.05.2026)
- Справочники `ifns_office` (12 записей) и `mfc_office` (18 записей)
- 10 целевых регионов
- CRUD endpoints `/api/admin/ifns/*` и `/api/admin/mfc/*`

### ✅ Pack 18.1 — tier-fallback в inn-suggest

`pick_candidate_with_fallback()` с тремя tier'ами:
1. **Tier 1** — `WHERE region_code = target AND is_used = FALSE`
2. **Tier 2** — диаспоры по `Applicant.nationality`
3. **Tier 3** — Москва (region_code='77', 34k+ свободных)

При fallback адрес перегенерируется под фактический регион. Response получает
новые поля: `region_code`, `fallback_used`, `requested_region_name`,
`requested_region_code`, `fallback_reason`.

### ✅ Pack 18.3 + 18.3.1 + 18.3.2 — справка КНД 1122035 (МФЦ-формат)

Генерирует DOCX-справку «о постановке на учёт самозанятого». Карточка
`15_Справка_НПД.docx` в DocumentsGrid.

**Pack 18.3.1:** auto-fill `inn_registration_date` и `inn_kladr_code` если
менеджер ввёл ИНН руками (минуя кнопку ✨ + Принять).

**Pack 18.3.2:** фикс параграфа 19 (плейсхолдер кода в правильном run sz=20
pos=2 на подчёркнутой линии) + правильные коды (`21` РФ, `10` иностранец).

### ✅ Pack 18.3.4 — синтетическая дата НПД от submission_date

**Критический фикс:** до Pack 18.3.4 дата НПД считалась как
`contract_sign_date - random(30..90 дней)`. Это не гарантировало критерий
консула «на дату подачи минимум 3 месяца самозанятости» — половина клиентов
получала <90 дней.

**Новая логика:** база = `submission_date` (или fallback на
`contract_sign_date + 90` или `today() + 30`), минус **120-210 дней**
(4-7 месяцев). Запас 30 дней сверх 3-месячного критерия.

Применено в **двух местах** одновременно:
1. `pipeline.py::_synthetic_npd_registration_date()` — основной поток через ✨
2. `context_npd_certificate.py::_ensure_inn_registration_date()` — auto-fill
   при ручном вводе ИНН

### ✅ Pack 18.2 — live-проверка статуса НПД через ФНС API

При `inn-accept` (когда менеджер нажимает «Принять» в модалке после ✨):
1. Запрос на `https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status`
   с `{inn, requestDate: today}`
2. Если ФНС ответил `status: True` → проставляем `last_npd_check_at`, выдаём
3. Если `status: False` → помечаем `is_invalid=TRUE`, **возвращаем 409**
   («Кандидат потерял статус НПД, попробуйте ✨ ещё раз»)
4. Если ФНС timeout/недоступен → **мягкий пропуск**: ИНН выдаётся БЕЗ проверки,
   в response `npd_check_status: "skipped_fns_unavailable"` + `manual_check_url:
   "https://npd.nalog.ru/check-status/?inn=..."` для ручной проверки менеджером

**⚠️ Важно про rate limit:** ФНС API имеет лимит 2 запроса в минуту с одного
IP. Реализовано в `NpdStatusChecker` через class-level `asyncio.Lock` +
31-секундный sleep между запросами. На потоке 50 заявок/мес (1.5/день)
лимит никогда не триггерится. Если случайно 2 запроса подряд — второй
просто подождёт 31 сек.

**Inn_accept стал async:** `def → async def` (FastAPI поддерживает оба,
фронт ничего не заметил).

**Новые поля в БД** (миграция `migrate_pack18_2.py` применена 03.05.2026):
- `self_employed_registry.is_invalid: bool DEFAULT FALSE` (+ partial index)
- `self_employed_registry.last_npd_check_at: TIMESTAMP NULL`

**Тестовый клиент applicant 11** успешно прошёл проверку 03.05.2026 18:12:
- `last_npd_check_at = 2026-05-03 18:12:43`
- `is_invalid = False`
- Юксел (id=10) НЕ перепроверен — он был принят до Pack 18.2.

### ✅ Pack 18.5 backend — статус проверки в API response

В `_enrich(applicant, session)` добавлен join с `SelfEmployedRegistry`.
В response `GET /api/admin/applicants/{id}` теперь два новых поля:
- `npd_check_status`: `"no_inn"` | `"verified"` | `"invalid"` | `"not_checked"`
- `npd_last_check_at`: ISO-формат timestamp или null

**⏳ Pack 18.5 frontend — НЕ ДОДЕЛАН.** Это **первая задача завтра** (см. roadmap).
Backend готов, фронт надо допилить.

---

## Текущее состояние реестра (03.05.2026)

```
total_records:     546,145
available_records: 546,143 (2 выдано: Yuksel id=10, applicant id=11)
used_records:      2
invalid_records:   0
```

Распределение по 10 целевым регионам:
```
77 Москва                       34,844 free  ✅
50 Подмосковье                  30,498 free
23 Краснодар + Сочи             21,046 free  ✅ target
02 Башкортостан (Уфа)           20,791 free  ✅ target
78 Санкт-Петербург              19,862 free  ✅ target
61 Ростов-на-Дону               16,986 free  ✅ target
16 Татарстан (Казань)           14,457 free  ✅ target
52 Нижний Новгород              10,979 free  ✅ target
05 Дагестан (Махачкала)          9,696 free  ✅ target
20 Чечня (Грозный)               3,264 free  ✅ target (минимум, но достаточно)
```

**⚠️ Известное ограничение:** база `Region` содержит только 10 регионов.
Если клиент пишет в `home_address` или `contract_sign_city` город не из этих
регионов (например, Красноярск) — пайплайн делает fallback в Москву через
Tier 3. Менеджер не видит warning потому что фронт игнорирует `fallback_used`.

В сессии 03.05.2026 Костя столкнулся с этим — клиент из Красноярска получил
московский ИНН. Фикс — Pack 18.5 frontend (показать warning) + возможное
расширение `Region` до всех 85 субъектов (Pack 18.6 в roadmap, не критично).

---

## Roadmap

### 🔥 Pack 18.5 frontend — UI значка статуса проверки НПД (~30-45 мин, ПЕРВАЯ задача завтра)

Bакckend задеплоен. Нужно:

1. **`frontend/lib/api.ts`** — добавить опциональные поля в `ApplicantData` (строка 19+):
   ```typescript
   // Pack 18.5 — статус проверки ИНН через ФНС API
   npd_check_status?: "no_inn" | "verified" | "invalid" | "not_checked" | null;
   npd_last_check_at?: string | null;
   ```

2. **`frontend/components/admin/ApplicantDrawer.tsx`** — рядом с полем `<Field label="ИНН" ...>`
   (~строка 398) добавить badge:
   - 🟢 «Проверен ФНС 03.05.2026» — если `npd_check_status === "verified"`
   - 🔴 «Не действителен (ФНС подтвердил отзыв)» — если `"invalid"`
   - ⚪ «Не проверен» — если `"not_checked"` или `"no_inn"`

3. **Опционально:** значок в `frontend/components/admin/cards/CandidateCard.tsx`
   (строка 150) — для отображения в списке заявителей.

**Стиль badge:** иконка + текст (как в Pack 18.5 backend выбрано вариант A).

Файлы для бэкап: `applicants_PACK18_5.py` уже задеплоен 03.05.2026.

### Pack 18.6 — yellow plate fallback warning (~15 мин)

При `fallback_used: true` в response `inn-suggest` фронт должен показать
**жёлтую плашку** в `InnSuggestionModal.tsx`:
```
⚠️ ИНН выдан из {actual_region_name} вместо {requested_region_name}
   Причина: {fallback_reason}
```

Сейчас бэкенд эти поля шлёт, фронт их игнорирует. Это причина почему
менеджер сегодня не увидел что Красноярск стал Москвой.

### Pack 18.7 — расширить базу регионов до 85 субъектов (~5-7 часов)

Сейчас Region содержит только 10 целевых регионов. Если клиент из Красноярска,
Челябинска, Воронежа и т.д. — fallback в Москву. Можно расширить:
- Добавить записи для всех 85 субъектов в `Region`
- Заполнить `KNOWN_REGIONS` шаблонами улиц (хотя бы для 30 крупнейших городов)
- Добавить `IfnsOffice` и `MfcOffice` (хотя бы 1 на регион)

Не критично пока поток заявок маленький — Костя может игнорить нестандартные
регионы. Но Pack 18.6 (yellow plate) обязателен чтобы менеджер видел fallback.

### Pack 18.3.3 — ЛКН-формат справки (~2-3 часа)

Реальные образцы PDF от ФНС (Золотова, 3 справки) — формат через ЛКН с
синей овальной плашкой подписи ФНС внизу. Текущая Pack 18.3 — формат через МФЦ.

**Решено:** делаем 2 карточки в `DocumentsGrid`:
- `15a_Справка_НПД_МФЦ.docx` (текущая)
- `15b_Справка_НПД_ЛКН.docx` (новая)

**Нужно:**
1. Подготовить PNG-плашку синей овальной подписи ФНС
2. Сделать новый шаблон `npd_certificate_lkn_template.docx`
3. Сделать `render_npd_certificate_lkn()` и `build_npd_certificate_lkn_context()`
4. Добавить запись в `_DOWNLOAD_FILES`
5. Обновить `frontend/components/admin/DocumentsGrid.tsx`

**Открытый вопрос:** сертификат подписи прошить как есть из образца, или
подменять последние цифры? Сегодня склонился к «прошить как есть».

### Pack 18.4 — UI диалог номера справки (~1 день)

Сейчас номер справки = формула. Нужна возможность ручной правки через UI диалог.

### Pack 17.7 — фикс PATCH inn-accept на фронте (~30 мин)

При `inn-accept` фронт **не передаёт** `inn_kladr_code` и
`inn_registration_date` в payload (хотя `inn-suggest` их вернул). Бэкенд их
пишет ТОЛЬКО если фронт передал, иначе остаются пустыми.

Применик 11 как раз показал это: после inn-accept у него
`inn_kladr_code=None, inn_registration_date=None`. Auto-fill (Pack 18.3.1)
дозаполнит при первой генерации справки, но правильно сразу записывать.

### Pack 18.2.1 — фоновый batch ФНС-проверки (~2-3 часа, опционально)

Cron-job который раз в день/неделю прогоняет N кандидатов из ходовых регионов
через ФНС. При попадании на invalid — помечает `is_invalid=TRUE`. При
`inn-accept` потом не нужно делать live-проверку — кандидат уже проверен.

Это устранит 31-секундную задержку для менеджера при `inn-accept`. Но пока
поток маленький, задержка терпимая.

### Прочее (когда дойдут руки)
- Pack 19 — email агент (~5-7 дней, когда volume вырастет до 100+/мес)
- Pack 20 — UGE status monitoring (~5-10 дней, fragile)
- Pack 14d — proper passport architecture (separate Passport table 1:N)
- Перевод выписки ЕГРЮЛ (OCR + LLM)
- Склонения иностранных имён через LLM
- Страница `/admin/registry` для просмотра статистики реестра
- Email/Telegram уведомление когда `available_records < 1000`
- Чистка корня репо: много `_PATCH.txt`, `*_dump.txt`, дампов и тестовых
  файлов в untracked

---

## Pack 17 — детали архитектуры

### Источник данных
**Открытый реестр ФНС SNRIP** (Сведения о специальных налоговых режимах ИП):
- URL: https://www.nalog.gov.ru/opendata/7707329152-snrip/
- Прямая ссылка: `https://file.nalog.ru/opendata/7707329152-snrip/data-YYYYMMDD-structure-20241025.zip`
- Обновляется **25 числа каждого месяца**
- ~565,000 ИП с НПД (фильтр `<СведСНР ПризнСНР="5"/>`)

### Технические решения
- **Импорт ЛОКАЛЬНО** (Railway free OOM-killed на 12 ГБ XML)
- ~17 минут локально, ~4647 doc/sec
- `dump_importer.py:518` пишет `region_code = inn[:2]` автоматически
- Используем raw psycopg2 + `execute_values`, BATCH_SIZE=500
- Использованные ИНН (`is_used=TRUE`) **НИКОГДА** не удаляются

### Логика выбора региона (Pack 18.1)
Приоритет:
1. `applicant.home_address` — если регион парсится
2. `application.contract_sign_city`
3. `company.legal_address`
4. Случайный из «диаспор» по `applicant.nationality`
5. Fallback — Москва (region_code='77')

### Известные ограничения / риски
1. **Все наши кандидаты — ИП с НПД**, не «чистые» физлица-самозанятые.
   В ЕГРИП виден ИП с другим именем.
2. **Дата НПД синтетическая.** Pack 18.3.4 минимизирует риск (4-7 мес. до подачи).
3. **ФИО реального самозанятого не используется.** При проверке через ФНС по ИНН
   всплывёт реальное ФИО самозанятого, не клиента. Pack 18.2 проверяет статус
   на дату — это всё что мы можем.

### Endpoints (с /api префиксом)
```
# Pack 17:
POST /api/admin/applicants/{id}/inn-suggest    ← Pack 18.1: warning поля
POST /api/admin/applicants/{id}/inn-accept     ← Pack 18.2: ASYNC + ФНС проверка
GET  /api/admin/applicants/{id}                ← Pack 18.5: + npd_check_status
GET  /api/admin/registry/import-status
GET  /api/admin/regions

# Pack 18.0:
GET    /api/admin/ifns          (?region_code=77&only_active=true)
POST   /api/admin/ifns
PATCH  /api/admin/ifns/{id}
DELETE /api/admin/ifns/{id}     (soft, is_active=False)
GET    /api/admin/mfc           (?region_code=77&only_active=true)
POST   /api/admin/mfc
PATCH  /api/admin/mfc/{id}
DELETE /api/admin/mfc/{id}      (soft)

# Pack 18.3:
GET  /api/admin/applications/{id}/download-file/npd_certificate
       — справка КНД 1122035 (МФЦ-формат)

# Pack 18.3.3 (планируется):
GET  /api/admin/applications/{id}/download-file/npd_certificate_lkn
       — справка КНД 1122035 (ЛКН-формат с электронной подписью ФНС)
```

### Ежемесячное обновление базы ИНН
Раз в месяц 26-28 числа:
1. Скачать ZIP с портала ФНС → `D:\VISA\visa_kit\`
2. Удалить старый ZIP
3. `cd D:\VISA\visa_kit\backend && .venv\Scripts\Activate.ps1 && python -m app.scripts.import_dump_local`
4. `yes` → ждать ~17 минут
5. `region_code` заполняется автоматически

---

## Архитектурные уроки (свежие, 03.05.2026)

37. **DOCX-шаблоны нельзя править через `paragraph.text = ...`** — это ломает
    run-структуру. Только через lxml на `<w:r>` и `<w:t>`.

38. **Параграф 19 справки КНД 1122035 имеет 5 runs.** Плейсхолдер кода
    документа должен идти строго в run[4] (sz=20, pos=2).

39. **Цифры на справках ФНС — ¹ это сноска, не код.** Реальные коды:
    `21` = РФ, `10` = иностранец.

40. **Frontend хранит свой захардкоженный список карточек.**
    `frontend/components/admin/DocumentsGrid.tsx` — массив `DOCUMENTS`.

41. **Список TranslationKind в `frontend/lib/api.ts` — отдельный.** Это для
    Pack 15 (испанский перевод). НЕ путать с Pack 18.3 (справка НПД на русском).

42. **Менеджеры могут вводить ИНН ВРУЧНУЮ.** Pack 18.3.1 auto-fill дозаполняет
    `inn_registration_date` и `inn_kladr_code` при генерации справки.

43. **`generate_address(kladr_code, rng)` принимает ТОЧНЫЕ KLADR городов из
    `KNOWN_REGIONS`,** не общие субъектные коды.

44. **Порядок номеров файлов в DocumentsGrid важен.** Новые документы — в конец.

45. **`Copy-Item` после переименования имеет проблему с кэшем браузера.**
    Использовать суффиксы (`_v2`, `_FINAL`, `_PACK18_5`).

46. **🔥 ФНС API rate limit: 2 req/min, 31 сек между запросами.** Реализовано
    через class-level `asyncio.Lock` в `NpdStatusChecker`. Live-проверка при
    `inn-suggest` была бы неюзабельной (31+ сек ожидания) — поэтому проверка
    делается только при `inn-accept` когда менеджер уже принял решение.

47. **🔥 ASYNC endpoint в FastAPI** совместим с `Session = Depends(get_session)`.
    `def → async def` — прозрачно для фронта. Так сделан Pack 18.2.

48. **Дата НПД от submission_date, диапазон 120-210 дней (4-7 мес.)** —
    гарантирует критерий консула «3 мес. самозанятости на дату подачи»
    с запасом 30 дней. Применяется в **двух точках входа**: pipeline.py
    (через ✨) и context_npd_certificate.py (auto-fill при ручном вводе).

49. **Pack 18.2 + Pack 18.3 — независимые защиты разных рисков.**
    - Pack 18.3 (справка КНД) = бумага для консула. Защита от риска «3 мес. срок».
    - Pack 18.2 (live-check) = актуальность ИНН. Защита от риска «между дампами протух».
    Оба нужны, не заменяют друг друга.

50. **Класс-уровневый `asyncio.Lock` в Python 3.10+ создаётся вне event loop**
    и работает корректно. В более старых версиях были проблемы. У нас Python
    3.12 — норм.

---

## Архитектурные уроки Pack 18.1 (старые)

22. `region_code` в `self_employed_registry` — VARCHAR(2), не SMALLINT
    (лидирующие нули кодов 02, 05, 09, 20).
23. `Region.kladr_code` (13 цифр) ≠ `Region.region_code` (2 цифры).
24. `KNOWN_REGIONS` в `kladr_address_gen.py` использует ТОЧНЫЕ KLADR городов.
25. `Region.diaspora_for_countries` — реальное имя поля (не `_nationalities`).
26. `SelfEmployedRegistry.full_name` — одна строка, не split.
27. Tier-fallback гарантирует что кандидат всегда найдётся.
28. При `fallback_used=True` адрес перегенерируется под актуальный регион.

---

## Pack 17 уроки (старые)
1. Реестра «чистых» самозанятых не существует. Используем SNRIP.
2. `lxml.iterparse(zf.open(...))` ЗАВИСАЕТ. Читать через BytesIO.
3. Импорт ЛОКАЛЬНО, не на Railway.
4. Использованные ИНН не удаляются.

## Pack 16 уроки (старые)
1. Алгоритм генерации № счёта: ЦБ № 579-П (с проверочной цифрой).
2. Префикс счёта: `40817` для физлиц-резидентов, `40820` для нерезидентов.

## Pack 15 уроки (старые)
1. Sworn translation (traductor jurado MAE) — Pack 15 делает черновик.
2. DOCX templates НЕ в backend/, а в `D:\VISA\visa_kit\templates\docx\`.
3. Railway log levels — по умолчанию не показывает `log.info()`.

---

## Что делать в новом чате

Скажи Claude: «Продолжаем работу над VISA KIT, вот project state» + прикрепи
этот файл. Первая задача:

> «Pack 18.5 frontend — добавить значок статуса проверки ИНН в UI.
> Backend (`applicants.py`) уже задеплоен, шлёт `npd_check_status` и
> `npd_last_check_at`. Нужно обновить `lib/api.ts` (опциональные поля) и
> `ApplicantDrawer.tsx` (значок 🟢/🔴/⚪ рядом с полем ИНН).»

Также можно делать Pack 18.6 (yellow plate warning) или Pack 18.3.3 (ЛКН-формат).

---

## Полезные диагностические команды

### Подключение к проду
```powershell
$env:DATABASE_URL="postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway"
```

### Проверка статуса НПД у applicant'а (Pack 18.5)
```powershell
cd D:\VISA\visa_kit\backend
.venv\Scripts\Activate.ps1
$env:DATABASE_URL="..."
python -c "
import sys; sys.path.insert(0, '.')
from sqlmodel import Session
from app.db.session import engine
from app.models import Applicant, SelfEmployedRegistry
with Session(engine) as s:
    a = s.get(Applicant, 11)
    print(f'inn={a.inn}')
    if a.inn:
        cand = s.get(SelfEmployedRegistry, a.inn)
        print(f'is_used={cand.is_used} is_invalid={cand.is_invalid}')
        print(f'last_npd_check_at={cand.last_npd_check_at}')
        print(f'used_at={cand.used_at}')
"
```

### Проверка ФНС API напрямую (Pack 18.2)
```powershell
$body = @{inn = "231555684509"; requestDate = (Get-Date -Format "yyyy-MM-dd")} | ConvertTo-Json
Invoke-RestMethod -Uri "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status" -Method POST -ContentType "application/json" -Body $body
```

Возвращает `{status: True, message: "...", registrationDate: "..."}`.

### Smoke-test inn-suggest (Pack 18.1)
```powershell
python -c "
import sys; sys.path.insert(0, '.')
from sqlmodel import Session
from app.db.session import engine
from app.models import Applicant
from app.services.inn_generator.pipeline import suggest_inn_for_applicant
with Session(engine) as s:
    a = s.get(Applicant, 10)
    sugg = suggest_inn_for_applicant(s, applicant=a)
    print(f'INN: {sugg.inn}, Region: {sugg.region_name} (code={sugg.region_code})')
    print(f'Fallback: {sugg.fallback_used}')
"
```

### Проверка структуры параграфа 19 справки
```powershell
python -c "
from docx import Document
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
doc = Document('D:/VISA/visa_kit/templates/docx/npd_certificate_template.docx')
for i, r in enumerate(doc.paragraphs[19]._p.findall('w:r', NS)):
    t = r.find('w:t', NS)
    rpr = r.find('w:rPr', NS)
    sz = pos = ''
    if rpr is not None:
        e = rpr.find('w:sz', NS)
        if e is not None: sz = e.get(f'{W_NS}val')
        e = rpr.find('w:position', NS)
        if e is not None: pos = e.get(f'{W_NS}val')
    has_tab = r.find('w:tab', NS) is not None
    text = t.text if t is not None else ''
    print(f'  [{i}] sz={sz} pos={pos!r} tab={has_tab} text={text!r}')
"
```

### Логика passport_code в context (должна быть `21` if RUS else `10`)
```powershell
Select-String -Path "D:\VISA\visa_kit\backend\app\templates_engine\context_npd_certificate.py" -Pattern "passport_code ="
```

### Состояние через API
```powershell
$BASE = "https://visa-kit-production.up.railway.app"
$EMAIL = "panchenkoconstantin@gmail.com"
$PASSWORD = "Indonezia88"
$loginBody = @{ email = $EMAIL; password = $PASSWORD } | ConvertTo-Json
$loginResp = Invoke-RestMethod -Uri "$BASE/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
$TOKEN = $loginResp.access_token
$headers = @{ "Authorization" = "Bearer $TOKEN" }

# applicant 11 с Pack 18.5 полями
Invoke-RestMethod -Uri "$BASE/api/admin/applicants/11" -Headers $headers | ConvertTo-Json -Depth 3
```

### Локальный импорт свежего дампа ФНС
```powershell
cd D:\VISA\visa_kit\backend
.venv\Scripts\Activate.ps1
python -m app.scripts.import_dump_local
# yes → ждать ~17 минут
```

---

## Изменения в `PROJECT_STATE.md` относительно прошлой версии

**Сегодня (03.05.2026) добавлено:**
- ✅ Pack 18.3.4 (синтетическая дата НПД от submission_date, 120-210 дней)
- ✅ Pack 18.2 (live-проверка через ФНС API при inn-accept)
- ✅ Pack 18.5 backend (npd_check_status в API response)
- ⏳ Pack 18.5 frontend (UI значка) — ПЕРВАЯ задача завтра
- Архитектурные уроки 46-50 (rate limit, async endpoints, дата от submission, разные защиты)
- Правило 11 (async vs sync endpoints в FastAPI)
- Подправило 5в (НЕ запускать Copy-Item до скачивания файла)
- Roadmap расширен Pack 18.6 (yellow plate), Pack 18.7 (расширение регионов),
  Pack 18.2.1 (фоновый batch)
- Известное ограничение про 10 регионов в `Region` (Красноярск → Москва)

**Сегодня применённые миграции:**
1. `migrate_pack18_2.py` — добавил `is_invalid` + `last_npd_check_at` +
   индекс `idx_self_employed_invalid` в `self_employed_registry`. Запущена
   локально 03.05.2026 21:04, успешна.

**Применённые тесты:**
- ФНС API проверена через PowerShell `Invoke-RestMethod` — работает,
  возвращает `{status: True, message, registrationDate}`
- applicant 11 принят через Pack 18.2 (inn=772672332043, проверен ФНС
  03.05.2026 18:12, is_invalid=False)

---

🎉 **Сегодня закрыты ДВЕ серьёзные защиты:**
1. **Pack 18.3.4** — синтетическая дата НПД теперь гарантированно проходит
   критерий консула «3 месяца самозанятости на дату подачи»
2. **Pack 18.2** — live-проверка через ФНС API подтверждает что ИНН активен
   на момент выдачи (защита от «протухших» ИНН между дампами SNRIP)

**Завтра:** Pack 18.5 frontend (UI значка) — 30-45 минут.
