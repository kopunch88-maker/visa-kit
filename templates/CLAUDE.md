# templates/ — DOCX и PDF шаблоны документов

Здесь живут все шаблоны, из которых система собирает финальные документы.

## Принцип

Шаблоны — это **обычные DOCX/PDF файлы**, которые редактируются командой в Word
или Acrobat без программистов. Переменные обозначаются Jinja2-синтаксисом:

```
Договор № {{ contract.number }} от {{ fmt_date_long_ru(contract.sign_date) }}
```

Когда нужно изменить формулировку в договоре — открываешь `docx/contract.docx`,
правишь как обычный текст, сохраняешь. Готово.

## Список шаблонов

### DOCX (рендер через docxtpl)
- `docx/contract.docx` — договор оказания услуг (рус)
- `docx/act.docx` — акт оказанных услуг (рус)
- `docx/invoice.docx` — счёт на оплату (рус)
- `docx/employer_letter.docx` — письмо от компании (рус, для перевода)
- `docx/cv.docx` — резюме на русском
- `docx/bank_statement.docx` — выписка по счёту (стилизованная под Альфа-банк)

### PDF (рендер через pypdf — заполнение AcroForm + наложение текста)
- `pdf/mit_form.pdf` — MI-T для главного заявителя
- `pdf/mif_form.pdf` — MI-F для члена семьи
- `pdf/designacion.pdf` — назначение представителя
- `pdf/declaracion_penales.pdf` — декларация об отсутствии судимости
- `pdf/compromiso_reta.pdf` — обязательство встать в RETA
- `pdf/declaracion_mantenimiento.pdf` — декларация о содержании семьи

## Доступные переменные в шаблонах

Все шаблоны получают на вход контекст из `app/templates_engine/context.py`.

Главные:

```jinja
{{ applicant.full_name_native }}        # Алиев Джафар Надирович
{{ applicant.initials_native }}         # Алиев Д.Н.
{{ applicant.passport_number }}         # C01366076
{{ applicant.nationality_display_ru }}  # Азербайджан

{{ company.short_name }}                # СК10
{{ company.full_name_ru }}              # ООО "СК10"
{{ company.director_full_name_genitive_ru }}  # Тараскина Юрия Александровича

{{ position.title_ru }}                 # инженер-геодезист (камеральщик)
{{ position.duties }}                   # список — используется в {% for %}

{{ contract.number }}
{{ contract.sign_date }}
{{ fmt_date_long_ru(contract.sign_date) }}  # «05» сентября 2025г.
{{ contract.salary_rub }}                    # 300000 (число)
{{ fmt_money(contract.salary_rub) }}         # "300 000"

{{ representative.full_name }}          # Анастасия Коренева
{{ representative.nie }}                # Z3751311Q

{{ spain_address.street }}              # CARRER DEL BALMES
{{ spain_address.number }}              # 128
```

И производные из computed-слоя:

```jinja
{% for doc in monthly_docs %}
   Акт №{{ doc.sequence_number }}/{{ doc.year_suffix }} от {{ doc.document_date }}
{% endfor %}

{{ bank.opening_balance }}              # 301018.66
{{ bank.transactions }}                 # список транзакций для {% for %}
```

Полный список — в `app/templates_engine/context.py`.

## Как редактировать DOCX-шаблон

1. Открыть в Microsoft Word или LibreOffice
2. Найти переменную типа `{{ contract.number }}` — это просто текст в документе
3. Правишь окружающий текст как обычно (формулировки, формат)
4. Сохранить. Готово.

⚠️ **Важно:** не разбивай переменную `{{ ... }}` форматированием. Если выделил
курсивом ровно слово `contract` внутри `{{ contract.number }}` — Jinja сломается,
потому что в XML это превратится в две разделённые xml-тега. Если такое случилось —
Word показывает переменную целиком как один шрифт, всё ок. Если разделена —
Word показывает разные шрифты внутри `{{ }}`. В этом случае удали и впиши
переменную заново.

## Как создать новый DOCX-шаблон

1. Возьми реальный документ-эталон (как клиенту приходит сейчас)
2. Скопируй в `templates/docx/<new_template>.docx`
3. Открой в Word, замени конкретные имена/числа на переменные `{{ ... }}`
4. Зарегистрируй в `app/templates_engine/registry.py` (тип документа +
   путь к шаблону + функция формирования контекста, если нужна особая)
5. Прогон через `pytest tests/test_rendering.py` — проверит что рендерится
   без ошибок
6. Открой результат в Word глазами — проверь визуально

## Как редактировать PDF-форму

PDF-формы — сложнее. Если у формы есть **AcroForm-поля** (формочки, в которые
можно кликнуть и вписать текст), используем их по имени. Если PDF плоский —
накладываем текст по координатам через ReportLab.

См. `app/templates_engine/pdf_renderer.py` для деталей. Или спроси Claude
"как добавить новое поле в PDF-форму типа MI-T", он подскажет.

## Версионирование шаблонов

В будущем формулировки UGE могут поменяться. Чтобы старые заявки могли
рендериться по старым шаблонам:

- Текущие шаблоны лежат в `templates/v1/`
- Когда меняем существенно — копируем в `templates/v2/`, в коде указываем
  `template_version="v2"` для новых заявок
- Старые `Application.template_version="v1"` продолжают рендериться по старому

Пока в системе одна версия — `v1` нет смысла создавать. Создадим, когда
понадобится первая обратная несовместимость.
