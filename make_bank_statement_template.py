"""
Pack 16.5 — генератор шаблона выписки.

Стратегия:
- НЕ заменяет параграфы балансов целиком (это убивает структуру runs).
- Делает «хирургические» замены: только runs с числом+RUR, оставляя
  «Входящий остаток» и пробелы как есть. Так Word сможет естественно
  переносить число по словам.

Шаги:
1. В шапке (textbox) — заменяет параграфы целиком (там простая структура).
2. В блоке балансов — заменяет ТОЛЬКО runs с числами, оставляя структуру.
3. В таблице операций — оставляет одну строку-образец с маркерами __TX_*__,
   удаляет фиксированную высоту строки чтобы Word адаптировал по содержимому.
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

# Замены параграфов в textbox шапке
HEADER_REPLACEMENTS = {
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
}

# Замены чисел в балансах (4 параграфа)
BALANCE_REPLACEMENTS = [
    {"marker": "Входящий остаток",   "jinja": "{{ bank.opening_balance_formatted }}"},
    {"marker": "Поступления",         "jinja": "{{ bank.total_income_formatted }}"},
    {"marker": "Расходы",             "jinja": "{{ bank.total_expense_formatted }}"},
    {"marker": "Исходящий остаток",   "jinja": "{{ bank.closing_balance_formatted }}"},
]


def get_paragraph_visible_text(p_element):
    """Видимый текст параграфа: <w:t> + табы внутри <w:r>."""
    parts = []
    for r in p_element.findall('.//w:r', NS):
        for elem in r:
            if elem.tag == W_NS + 't':
                parts.append(elem.text or "")
            elif elem.tag == W_NS + 'tab':
                parts.append('\t')
    return "".join(parts)


def replace_paragraph_text(p_element, new_text):
    """Полная замена текста параграфа (для шапки textbox)."""
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

    parts = new_text.split('\t')
    for i, part in enumerate(parts):
        if i > 0:
            etree.SubElement(r, f'{W_NS}tab')
        if part:
            t = etree.SubElement(r, f'{W_NS}t')
            t.text = part
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

    for elem in p_element.findall('.//w:proofErr', NS):
        elem.getparent().remove(elem)


def replace_balance_in_paragraph(p_element, balance):
    """
    Заменяет «число + RUR» в параграфе на «Jinja + RUR».

    Алгоритм:
    - Найти последний run с "RUR".
    - Идти назад от него собирая runs.
    - Числовой run = содержит цифры/запятые/точки/NBSP (возможно с пробелами
      внутри как разделители разрядов).
    - Пробельный run длиной 1 = разделитель тысяч ВНУТРИ числа, продолжаем.
    - Пробельный run длиной >1 = выравнивание ПЕРЕД числом, СТОП.
    - Любой другой текст = СТОП.
    """
    runs = p_element.findall('.//w:r', NS)
    if not runs:
        return False

    rur_idx = None
    for i in range(len(runs) - 1, -1, -1):
        ts = runs[i].findall('.//w:t', NS)
        if any(t.text and "RUR" in t.text for t in ts):
            rur_idx = i
            break

    if rur_idx is None:
        return False

    NUMBER_CHARS = set("0123456789,.\xa0")

    start_idx = rur_idx
    for i in range(rur_idx - 1, -1, -1):
        text_parts = []
        for elem in runs[i]:
            if elem.tag == W_NS + 't':
                text_parts.append(elem.text or "")
            elif elem.tag == W_NS + 'tab':
                text_parts.append('\t')
        text = "".join(text_parts)

        if not text:
            # Пустой run — пропускаем
            start_idx = i
            continue

        # Чисто-пробельный run
        if all(c == ' ' for c in text):
            # Если 1 пробел — это разделитель тысяч (продолжаем)
            # Если 2+ — это выравнивание (стоп)
            if len(text) == 1:
                start_idx = i
                continue
            else:
                break

        # Содержит числовые символы (с возможными пробелами как разделителями)
        if any(c in NUMBER_CHARS for c in text) and all(c in NUMBER_CHARS or c == ' ' for c in text):
            start_idx = i
            continue

        # Что-то другое — стоп
        break

    # Берём rPr от RUR-run для одинакового форматирования
    rur_run = runs[rur_idx]
    rur_rpr = rur_run.find('.//w:rPr', NS)

    # Создаём новый run с «Jinja + RUR»
    new_r = etree.Element(f'{W_NS}r')
    if rur_rpr is not None:
        new_r.append(etree.fromstring(etree.tostring(rur_rpr)))
    new_t = etree.SubElement(new_r, f'{W_NS}t')
    # NBSP перед RUR — чтобы число не отрывалось от валюты при переносе
    new_t.text = balance["jinja"] + "\xa0RUR"
    new_t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

    # Вставляем новый run на место первого числового
    parent = runs[start_idx].getparent()
    insert_pos = list(parent).index(runs[start_idx])
    parent.insert(insert_pos, new_r)

    # Удаляем старые runs (start_idx..rur_idx)
    for i in range(start_idx, rur_idx + 1):
        old_r = runs[i]
        old_r.getparent().remove(old_r)

    return True


def clean_transactions_table(doc):
    """
    - Оставляет row 0 (заголовок) и row 1 как образец с маркерами __TX_*__
    - Удаляет остальные строки
    - Убирает фиксированную <w:trHeight/> чтобы Word адаптировал высоту
    """
    deleted_total = 0

    for table_idx, table in enumerate(doc.tables):
        if len(table.rows) < 2:
            continue
        header_text = table.rows[0].cells[0].text.strip()
        if "Дата проводки" not in header_text:
            continue

        print(f"  Found transactions table #{table_idx} with {len(table.rows)} rows")

        template_row = table.rows[1]
        cells = template_row.cells

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
                p = etree.SubElement(cell._tc, f'{W_NS}p')
                paragraphs = [p]

            replace_paragraph_text(paragraphs[0], marker)
            for extra_p in paragraphs[1:]:
                extra_p.getparent().remove(extra_p)
            print(f"    [row 1, col {ci}] -> {marker}")

        # Убираем фиксированную высоту
        trPr = template_row._tr.find('w:trPr', NS)
        if trPr is not None:
            tr_height = trPr.find('w:trHeight', NS)
            if tr_height is not None:
                trPr.remove(tr_height)
                print(f"    Removed fixed trHeight (Word will auto-size by content)")

        # Удаляем остальные строки
        rows_to_delete = list(table.rows[2:])
        tbl = template_row._tr.getparent()
        for row in rows_to_delete:
            tbl.remove(row._tr)
            deleted_total += 1

        print(f"  Deleted {len(rows_to_delete)} rows")

    return deleted_total


def process(source: Path, target: Path):
    if not source.exists():
        print(f"ERROR: source not found: {source}")
        sys.exit(1)

    print(f"Reading: {source.name}")
    doc = Document(str(source))

    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak_pre_pack16_5")
        if not backup.exists():
            shutil.copy2(target, backup)
            print(f"Backup: {backup.name}")

    all_paragraphs = doc.element.findall('.//w:p', NS)
    print(f"\nTotal paragraphs: {len(all_paragraphs)}")

    # 1. Header (textbox)
    header_count = 0
    for p in all_paragraphs:
        current_text = get_paragraph_visible_text(p)
        if current_text in HEADER_REPLACEMENTS:
            new_text = HEADER_REPLACEMENTS[current_text]
            replace_paragraph_text(p, new_text)
            header_count += 1
            preview = (new_text[:50] + "...") if len(new_text) > 50 else new_text
            print(f"  Header: {current_text[:40]!r} -> {preview!r}")
    print(f"  Header replacements: {header_count}")

    # 2. Balances (surgical)
    print(f"\nReplacing balance numbers...")
    balance_count = 0
    for p in all_paragraphs:
        current_text = get_paragraph_visible_text(p)
        for balance in BALANCE_REPLACEMENTS:
            if balance["marker"] in current_text and "RUR" in current_text:
                if replace_balance_in_paragraph(p, balance):
                    balance_count += 1
                    print(f"  Balance: {balance['marker']!r} -> {balance['jinja']!r}")
                    break
    print(f"  Balance replacements: {balance_count}")

    # 3. Transactions table
    print(f"\nCleaning transactions table...")
    deleted = clean_transactions_table(doc)

    doc.save(str(target))
    print(f"\n✓ Saved: {target}")
    print(f"   - {header_count} header, {balance_count} balance replacements")
    print(f"   - {deleted} transaction rows removed")


if __name__ == "__main__":
    process(SOURCE, TARGET)
