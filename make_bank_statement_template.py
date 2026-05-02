"""
Pack 16.3 — генератор шаблона выписки.

Берёт «эталонную» выписку Алиева (Выписка_по_счету_Алиев.docx), которая лежит
в проекте как base, и делает из неё шаблон:

1. ЗАМЕНЯЕТ захардкоденные данные клиента в шапке (textbox) на Jinja-переменные:
   - "40803840441563809831 11.02.2024" → "{{ applicant.bank_account }} {{ bank.account_open_date_formatted }}"
   - "20.04.2026"                       → "{{ bank.statement_date_formatted }}"
   - "Алиев Джафар Надирович"           → "{{ applicant.full_name_native }}"
   - "Паспорт AZE C01366076"            → "Паспорт {{ applicant.nationality }} {{ applicant.passport_number }}"
   - "352919, Краснодарский край,"      → "{{ applicant.home_address_line1 }}"
   - "г. Армавир, ул. 11-я Линия, ..."  → "{{ applicant.home_address_line2 }}"

2. ЗАМЕНЯЕТ Расходы в шапке балансов:
   - "Расходы\\t1\\xa0171 778,54 RUR"   → "Расходы\\t{{ bank.total_expense_formatted }}"
   - С сохранением правого tab stop'а параграфа

3. ОЧИЩАЕТ таблицу операций — оставляет только заголовок и ОДНУ строку-образец
   с маркерами __TX_DATE__, __TX_CODE__, __TX_DESCRIPTION__, __TX_AMOUNT__.
   Эту строку Phase 2 в render_bank_statement клонирует для каждой транзакции.

Использование:
    python make_bank_statement_template.py

Входной:   D:\\VISA\\visa_kit\\templates\\docx\\Выписка_по_счету_Алиев.docx
Выходной:  D:\\VISA\\visa_kit\\templates\\docx\\bank_statement_template.docx
"""

import shutil
import sys
from pathlib import Path

try:
    from docx import Document
    import lxml.etree as etree
except ImportError:
    print("ERROR: python-docx not installed. Activate venv first.")
    sys.exit(1)

TEMPLATES_DIR = Path(r"D:\VISA\visa_kit\templates\docx")
SOURCE = TEMPLATES_DIR / "Выписка_по_счету_Алиев.docx"
TARGET = TEMPLATES_DIR / "bank_statement_template.docx"

W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

# Текстовые замены (точное совпадение видимого текста параграфа → новый текст)
# Видимый текст = w:t склеенные + табы
PARAGRAPH_REPLACEMENTS = {
    # Шапка (textbox)
    "40803840441563809831 11.02.2024":
        "{{ applicant.bank_account }} {{ bank.account_open_date_formatted }}",

    "20.04.2026":
        "{{ bank.statement_date_formatted }}",

    "Алиев Джафар Надирович":
        "{{ applicant.full_name_native }}",

    "Паспорт AZE C01366076":
        "Паспорт {{ applicant.nationality }} {{ applicant.passport_number }}",

    "352919, Краснодарский край,":
        "{{ applicant.home_address_line1 }}",

    "г. Армавир, ул. 11-я Линия, д. 31 кв. 2":
        "{{ applicant.home_address_line2 }}",

    # Расходы — захардкожено, нужно сохранить tab stop. Параграф в исходнике
    # начинается с tab перед "Расходы".
    "\tРасходы\t1\xa0171 778,54 RUR":
        "\tРасходы\t{{ bank.total_expense_formatted }}",
}


def get_paragraph_visible_text(p_element):
    """
    Собирает «видимый» текст параграфа из <w:t> + <w:tab/>.
    Эквивалент paragraph.text в python-docx.
    """
    parts = []
    for elem in p_element.iter():
        tag = elem.tag
        if tag == W_NS + 't':
            parts.append(elem.text or "")
        elif tag == W_NS + 'tab':
            parts.append('\t')
    return "".join(parts)


def replace_paragraph_text(p_element, new_text):
    """
    Заменяет содержимое параграфа на new_text, сохраняя форматирование первого run.

    - Удаляет все <w:r> кроме первого
    - Очищает <w:t>/<w:tab/>/<w:br/> в первом run (rPr остаётся — это формат)
    - Кладёт новый текст с правильной обработкой '\\t' → <w:tab/>
    """
    runs = p_element.findall('.//w:r', NS)

    if not runs:
        r = etree.SubElement(p_element, f'{W_NS}r')
    else:
        r = runs[0]
        for other_r in runs[1:]:
            other_r.getparent().remove(other_r)
        for child in list(r):
            tag = etree.QName(child).localname
            if tag in ('t', 'tab', 'br'):
                r.remove(child)

    # Разбиваем по \t и кладём чередующиеся <w:t> и <w:tab/>
    parts = new_text.split('\t')
    for i, part in enumerate(parts):
        if i > 0:
            etree.SubElement(r, f'{W_NS}tab')
        if part:
            t = etree.SubElement(r, f'{W_NS}t')
            t.text = part
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

    # Удаляем proofErr-маркеры (они мешают Jinja)
    for elem in p_element.findall('.//w:proofErr', NS):
        elem.getparent().remove(elem)


def clean_transactions_table(doc):
    """
    Превращает таблицу операций в шаблонную:
    - Оставляет row 0 (заголовок: Дата проводки / Код / Описание / Сумма)
    - Оставляет row 1 как «строку-образец» с маркерами __TX_*__
    - Удаляет все остальные строки (с данными Алиева)

    Возвращает количество удалённых строк (для логов).
    """
    deleted_total = 0

    for table_idx, table in enumerate(doc.tables):
        # Ищем таблицу операций — у неё в первой строке "Дата проводки"
        if len(table.rows) < 2:
            continue
        header_text = table.rows[0].cells[0].text.strip()
        if "Дата проводки" not in header_text:
            continue

        print(f"  Found transactions table #{table_idx} with {len(table.rows)} rows")

        # Row 0 — заголовок, оставляем
        # Row 1 — превращаем в строку-образец с маркерами
        # Row 2+ — удаляем

        template_row = table.rows[1]
        cells = template_row.cells

        # 5 колонок: Дата | Код | Описание | Сумма | Сумма (повтор)
        # Маркеры:  __TX_DATE__ | __TX_CODE__ | __TX_DESCRIPTION__ | __TX_AMOUNT__ | __TX_AMOUNT__
        markers = [
            "__TX_DATE__",
            "__TX_CODE__",
            "__TX_DESCRIPTION__",
            "__TX_AMOUNT__",
            "__TX_AMOUNT__",
        ]

        for ci, cell in enumerate(cells):
            if ci >= len(markers):
                break
            marker = markers[ci]
            paragraphs = cell._tc.findall('.//w:p', NS)

            if not paragraphs:
                # Ячейка пустая — добавим параграф
                p = etree.SubElement(cell._tc, f'{W_NS}p')
                paragraphs = [p]

            # Кладём маркер в первый параграф ячейки
            replace_paragraph_text(paragraphs[0], marker)
            # Удаляем остальные параграфы в ячейке (если в них были многострочные данные Алиева)
            for extra_p in paragraphs[1:]:
                extra_p.getparent().remove(extra_p)

            print(f"    [row 1, col {ci}] -> {marker}")

        # Удаляем все строки начиная с row 2
        rows_to_delete = list(table.rows[2:])
        tbl = template_row._tr.getparent()
        for row in rows_to_delete:
            tbl.remove(row._tr)
            deleted_total += 1

        print(f"  Deleted {len(rows_to_delete)} hardcoded transaction rows from table #{table_idx}")
        # Идём дальше — таблиц с транзакциями обычно одна, но на всякий случай не break

    return deleted_total


def process(source: Path, target: Path):
    if not source.exists():
        print(f"ERROR: source file not found: {source}")
        sys.exit(1)

    print(f"Reading source: {source.name}")
    doc = Document(str(source))

    # Backup target if exists
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak_pre_pack16_3")
        if not backup.exists():
            shutil.copy2(target, backup)
            print(f"Backup of existing template saved: {backup.name}")

    # === 1. Заменяем тексты параграфов на Jinja ===
    all_paragraphs = doc.element.findall('.//w:p', NS)
    print(f"\nTotal paragraphs (including textboxes): {len(all_paragraphs)}")

    paragraph_replacements = 0
    for p in all_paragraphs:
        current_text = get_paragraph_visible_text(p)
        if current_text in PARAGRAPH_REPLACEMENTS:
            new_text = PARAGRAPH_REPLACEMENTS[current_text]
            replace_paragraph_text(p, new_text)
            paragraph_replacements += 1
            preview = (new_text[:60] + "...") if len(new_text) > 60 else new_text
            print(f"  Replaced: {current_text[:50]!r} -> {preview!r}")

    print(f"  Total paragraph replacements: {paragraph_replacements}")

    # === 2. Чистим таблицу операций — оставляем только маркер-строку ===
    print(f"\nCleaning transactions table...")
    deleted = clean_transactions_table(doc)

    # Сохраняем
    doc.save(str(target))
    print(f"\n✓ Saved template: {target}")
    print(f"   - {paragraph_replacements} paragraph replacements (Jinja vars)")
    print(f"   - {deleted} hardcoded transaction rows removed")


if __name__ == "__main__":
    process(SOURCE, TARGET)
    print("\n✓ Done. The template is ready.")
    print("  Test by rendering for any client — operations table will be filled by render_bank_statement Phase 2.")
