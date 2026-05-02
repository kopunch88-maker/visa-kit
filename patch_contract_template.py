"""
Pack 16.7 — патч contract_template.docx:

1. УБИРАЕТ ПУСТЫЕ СТРОКИ В РЕКВИЗИТАХ когда {{ ...line2 }} переменные пустые.

   Подход: вместо двух параграфов
       Юрид. адрес: {{ company.legal_address_line1 }}
       {{ company.legal_address_line2 }}
   делаем ОДИН параграф с полной переменной:
       Юрид. адрес: {{ company.legal_address }}

   Word при необходимости сам перенесёт длинный адрес на следующую строку
   внутри ячейки таблицы. Если адрес короткий — пустой строки не будет.

   Затрагивает 3 пары:
   - {{ company.legal_address_line1 }} + {{ company.legal_address_line2 }} → {{ company.legal_address }}
   - {{ company.postal_address_line1 }} + {{ company.postal_address_line2 }} → {{ company.postal_address }}
   - {{ applicant.home_address_line1 }} + {{ applicant.home_address_line2 }} → {{ applicant.home_address }}

2. KEEPNEXT для юридически правильного переноса блока реквизитов:
   по ГОСТ Р 7.0.97-2025 / методическим рекомендациям, реквизиты не должны
   быть оторваны от подписей, и на странице с подписями должно быть минимум
   2-4 строки текста выше.

   Применяю <w:keepNext/> на:
   - Параграф «8. Адреса и реквизиты Сторон»
   - Все параграфы внутри таблицы реквизитов
   - Параграф «Подписи Сторон»
   - Параграфы в таблице подписей (кроме последнего)
   - На последний параграф раздела 7 — чтобы хоть он переехал с разделом 8

Использование:
    cd D:\\VISA\\visa_kit
    python patch_contract_template.py

Делает .bak_pre_pack16_7 копию шаблона перед изменением.
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
TARGET = TEMPLATES_DIR / "contract_template.docx"

W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


# Пары (line1_var → full_var) для замены: первый параграф берёт full переменную,
# второй параграф (содержит только line2_var) удаляется.
ADDRESS_REPLACEMENTS = [
    {
        "line1_marker": "{{ company.legal_address_line1 }}",
        "line2_marker": "{{ company.legal_address_line2 }}",
        "full_marker": "{{ company.legal_address }}",
    },
    {
        "line1_marker": "{{ company.postal_address_line1 }}",
        "line2_marker": "{{ company.postal_address_line2 }}",
        "full_marker": "{{ company.postal_address }}",
    },
    {
        "line1_marker": "{{ applicant.home_address_line1 }}",
        "line2_marker": "{{ applicant.home_address_line2 }}",
        "full_marker": "{{ applicant.home_address }}",
    },
]


def replace_text_in_paragraph(p_element, old_text, new_text):
    """
    Замена текста в параграфе с учётом того что маркер `{{ ... }}` может быть
    разорван между несколькими <w:t>-элементами.

    Стратегия: собираем полный текст из всех runs, проверяем наличие old_text.
    Если есть — записываем новый текст в первый run, остальные runs очищаем.
    """
    runs = p_element.findall('w:r', NS)
    if not runs:
        return False

    # Собираем все <w:t> элементы в порядке появления
    all_t = []
    for r in runs:
        for t in r.findall('w:t', NS):
            all_t.append(t)

    if not all_t:
        return False

    full_text = "".join(t.text or "" for t in all_t)

    if old_text not in full_text:
        return False

    new_full_text = full_text.replace(old_text, new_text)

    # Кладём весь новый текст в первый <w:t>, остальные обнуляем
    all_t[0].text = new_full_text
    all_t[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    for t in all_t[1:]:
        t.text = ""

    return True


def merge_address_paragraphs(doc):
    """
    Для каждой пары (line1_marker, line2_marker, full_marker):
    - находит параграф с line1_marker
    - находит соседний параграф с line2_marker (обычно сразу следующий)
    - заменяет line1_marker на full_marker в первом параграфе
    - удаляет второй параграф

    Это убирает пустую строку когда line2 пустой и упрощает логику —
    Word сам переносит длинный адрес.
    """
    modified = 0

    for repl in ADDRESS_REPLACEMENTS:
        all_paragraphs = doc.element.findall('.//w:p', NS)

        line1_p = None
        line2_p = None

        for p in all_paragraphs:
            ts = p.findall('.//w:t', NS)
            text = "".join(t.text or "" for t in ts)

            if repl["line1_marker"] in text and line1_p is None:
                line1_p = p
                continue

            if line1_p is not None and repl["line2_marker"] in text and line2_p is None:
                line2_p = p
                break

        if line1_p is None:
            print(f"    line1 not found: {repl['line1_marker']}")
            continue

        # Заменяем line1_marker на full_marker
        if replace_text_in_paragraph(line1_p, repl["line1_marker"], repl["full_marker"]):
            print(f"    Replaced {repl['line1_marker']} → {repl['full_marker']}")
            modified += 1

        # Удаляем параграф с line2 (он теперь не нужен)
        if line2_p is not None:
            line2_parent = line2_p.getparent()
            line2_parent.remove(line2_p)
            print(f"    Removed paragraph with {repl['line2_marker']}")

    return modified


def add_keep_next(p_element):
    """Добавляет <w:keepNext/> в pPr параграфа если ещё нет."""
    ppr = p_element.find('w:pPr', NS)
    if ppr is None:
        ppr = etree.Element(f'{W_NS}pPr')
        p_element.insert(0, ppr)

    if ppr.find('w:keepNext', NS) is not None:
        return False

    etree.SubElement(ppr, f'{W_NS}keepNext')
    return True


def apply_keep_next_to_section_8(doc):
    """
    Применяет keepNext чтобы блок «8. Адреса и реквизиты Сторон» + подписи
    шёл единым целым.

    По ГОСТ Р 7.0.97-2025: реквизиты не отрываются от подписей, на странице
    с подписями должно быть минимум 2-4 строки текста выше.
    """
    body = doc.element.body
    children = list(body)

    section_8_idx = None
    section_7_5_idx = None
    requisites_table_idx = None
    signatures_table_idx = None

    for i, c in enumerate(children):
        tag = etree.QName(c).localname
        if tag == 'p':
            ts = c.findall('.//w:t', NS)
            text = "".join(t.text or "" for t in ts).strip()
            if '8. Адреса и реквизиты' in text:
                section_8_idx = i
            elif text.startswith('7.5.'):
                section_7_5_idx = i
        elif tag == 'tbl':
            if requisites_table_idx is None:
                requisites_table_idx = i
            else:
                signatures_table_idx = i

    if section_8_idx is None or requisites_table_idx is None or signatures_table_idx is None:
        print("  WARNING: не найдены якорные элементы")
        return 0

    print(f"  Anchors: section7.5={section_7_5_idx}, section8={section_8_idx}, "
          f"requisites_tbl={requisites_table_idx}, sig_tbl={signatures_table_idx}")

    paragraphs_modified = 0

    # 1. keepNext на «7.5. Настоящий Договор...»
    if section_7_5_idx is not None:
        if add_keep_next(children[section_7_5_idx]):
            paragraphs_modified += 1

    # 2. keepNext на параграфы между «8.» (включительно) и таблицей реквизитов
    for i in range(section_8_idx, requisites_table_idx):
        elem = children[i]
        if etree.QName(elem).localname != 'p':
            continue
        if add_keep_next(elem):
            paragraphs_modified += 1

    # 3. keepNext на ВСЕ параграфы в таблице реквизитов
    requisites_tbl = children[requisites_table_idx]
    for p in requisites_tbl.findall('.//w:p', NS):
        if add_keep_next(p):
            paragraphs_modified += 1

    # 4. keepNext на параграфы между таблицами (включая «Подписи Сторон»)
    for i in range(requisites_table_idx + 1, signatures_table_idx):
        elem = children[i]
        if etree.QName(elem).localname != 'p':
            continue
        if add_keep_next(elem):
            paragraphs_modified += 1

    # 5. keepNext на параграфы в таблице подписей кроме последнего
    signatures_tbl = children[signatures_table_idx]
    sig_paragraphs = signatures_tbl.findall('.//w:p', NS)
    if len(sig_paragraphs) > 1:
        for p in sig_paragraphs[:-1]:
            if add_keep_next(p):
                paragraphs_modified += 1

    return paragraphs_modified


def process(target: Path):
    if not target.exists():
        print(f"ERROR: target not found: {target}")
        sys.exit(1)

    backup = target.with_suffix(target.suffix + ".bak_pre_pack16_7")
    if not backup.exists():
        shutil.copy2(target, backup)
        print(f"Backup: {backup.name}")

    print(f"\nReading: {target.name}")
    doc = Document(str(target))

    print(f"\nStep 1: Merging address line1+line2 paragraphs into single full address...")
    merged = merge_address_paragraphs(doc)
    print(f"  Replacements: {merged}")

    print(f"\nStep 2: Applying keepNext to section 8 + signatures...")
    keep_next_count = apply_keep_next_to_section_8(doc)
    print(f"  Paragraphs modified: {keep_next_count}")

    doc.save(str(target))
    print(f"\n✓ Saved: {target}")
    print(f"   - {merged} address paragraphs merged (no empty lines)")
    print(f"   - {keep_next_count} keepNext applied (no orphan signatures)")


if __name__ == "__main__":
    process(TARGET)
