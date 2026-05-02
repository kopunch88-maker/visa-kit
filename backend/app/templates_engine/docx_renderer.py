"""
Рендер DOCX-шаблонов через docxtpl.

Bank statement рендерится особым способом: после стандартного docxtpl-рендера
(подставляет шапку с балансами и периодом), мы открываем результат через
python-docx, находим строку-образец с маркерами __TX_*__ и клонируем её
для каждой транзакции, заменяя маркеры на реальные данные.

Pack 16.4 changes:
- _replace_markers_in_tr теперь поддерживает многострочные значения —
  если описание содержит '\\n' (например зарплата от компании), для
  каждой строки создаётся отдельный <w:p> в ячейке.
- Добавлена _remove_empty_paragraph_between_tables — убирает пустой
  параграф между таблицей операций и таблицей подписи, чтобы подпись
  поместилась сразу после операций (без перевода на 2-ю страницу
  если на 1-й есть место).
"""

import io
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docxtpl import DocxTemplate
from sqlmodel import Session
import lxml.etree as etree

from app.models import Application
from .context import build_context


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "docx"

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def _render(template_name: str, context: dict) -> bytes:
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    template = DocxTemplate(str(template_path))
    template.render(context)

    buffer = io.BytesIO()
    template.save(buffer)
    return buffer.getvalue()


def render_contract(application: Application, session: Session) -> bytes:
    context = build_context(application, session)
    return _render("contract_template.docx", context)


def render_act(application: Application, session: Session, sequence_number: int) -> bytes:
    context = build_context(application, session)
    months = context.get("monthly_documents", [])
    target = next((m for m in months if m["sequence_number"] == sequence_number), None)
    if not target:
        raise ValueError(f"No monthly document with sequence {sequence_number}")
    context["act"] = target
    return _render("act_template.docx", context)


def render_invoice(application: Application, session: Session, sequence_number: int) -> bytes:
    context = build_context(application, session)
    months = context.get("monthly_documents", [])
    target = next((m for m in months if m["sequence_number"] == sequence_number), None)
    if not target:
        raise ValueError(f"No monthly document with sequence {sequence_number}")
    context["invoice"] = target
    return _render("invoice_template.docx", context)


def render_employer_letter(application: Application, session: Session) -> bytes:
    context = build_context(application, session)
    return _render("employer_letter_template.docx", context)


def render_cv(application: Application, session: Session) -> bytes:
    context = build_context(application, session)
    return _render("cv_template.docx", context)


def render_bank_statement(application: Application, session: Session) -> bytes:
    """
    Двухфазный рендер:
    1. docxtpl подставляет шапку (период, балансы) через Jinja
    2. python-docx клонирует строку-образец таблицы для каждой транзакции
    """
    template_path = TEMPLATES_DIR / "bank_statement_template.docx"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    context = build_context(application, session)
    bank_data = context.get("bank", {})
    transactions = bank_data.get("transactions", [])

    # === ФАЗА 1: рендер шапки через docxtpl ===
    template = DocxTemplate(str(template_path))
    template.render(context)
    buffer = io.BytesIO()
    template.save(buffer)
    buffer.seek(0)

    # === ФАЗА 2: клонирование строк через python-docx ===
    doc = Document(buffer)

    # Находим таблицу транзакций (по маркеру в первой ячейке второй строки)
    tx_table = None
    template_row = None
    for table in doc.tables:
        if len(table.rows) < 2:
            continue
        second_row = table.rows[1]
        if second_row.cells and "__TX_DATE__" in second_row.cells[0].text:
            tx_table = table
            template_row = second_row
            break

    if tx_table is None or template_row is None:
        result_buffer = io.BytesIO()
        doc.save(result_buffer)
        return result_buffer.getvalue()

    # Клонируем образцовую строку для каждой транзакции
    template_tr_xml = template_row._tr
    parent = template_tr_xml.getparent()
    insert_position = list(parent).index(template_tr_xml)

    last_row = None
    for idx, tx in enumerate(transactions):
        new_tr = deepcopy(template_tr_xml)
        _replace_markers_in_tr(new_tr, tx)

        # Pack 16.5: серый фон у строк дохода (зарплата от компании).
        amount = tx.get("amount")
        if amount is not None:
            try:
                amount_val = float(amount)
            except (TypeError, ValueError):
                amount_val = 0
            if amount_val > 0:
                _apply_gray_shading_to_row(new_tr)

        # Pack 16.5b: <w:cantSplit/> — запрет разрыва строки между страницами.
        _set_cant_split(new_tr)

        parent.insert(insert_position + idx, new_tr)
        last_row = new_tr

    # Удаляем оригинальную строку-образец
    parent.remove(template_tr_xml)

    # Pack 16.5c: keepNext на последнюю операцию + параграф между таблицами,
    # чтобы подпись не оставалась одна на странице. Если последняя операция
    # не помещается с подписью на 1-й странице — обе уйдут на 2-ю вместе.
    if last_row is not None:
        _set_keep_next_on_row(last_row)
    _set_keep_next_on_paragraph_between_tables(doc)

    result_buffer = io.BytesIO()
    doc.save(result_buffer)
    return result_buffer.getvalue()


def _replace_markers_in_tr(tr_element, tx: dict):
    """
    Заменяет маркеры __TX_*__ на значения транзакции в строке таблицы.

    Pack 16.4: если значение содержит '\\n' (как в описании зарплаты —
    Плательщик / ИНН / Счёт / Назначение платежа), разбивает его на
    отдельные параграфы в ячейке. Word игнорирует '\\n' в <w:t> тегах —
    для реального переноса нужны отдельные <w:p>.
    """
    marker_to_value = {
        "__TX_DATE__": tx.get("date_formatted", ""),
        "__TX_CODE__": tx.get("code", ""),
        "__TX_DESCRIPTION__": tx.get("description", "") or "",
        "__TX_AMOUNT__": tx.get("amount_formatted", ""),
    }

    cells = tr_element.findall('.//w:tc', NS)

    for cell in cells:
        paragraphs = cell.findall('.//w:p', NS)

        for p in paragraphs:
            ts = p.findall('.//w:t', NS)
            full_text = "".join(t.text or "" for t in ts)

            for marker, value in marker_to_value.items():
                if marker in full_text:
                    if '\n' in value:
                        _replace_marker_with_multiline(cell, p, marker, value)
                    else:
                        _replace_marker_inline(p, marker, value)
                    break


def _replace_marker_inline(p_element, marker: str, value: str):
    """Простая замена маркера в текстах параграфа."""
    for t in p_element.findall('.//w:t', NS):
        if t.text and marker in t.text:
            t.text = t.text.replace(marker, value)


def _replace_marker_with_multiline(cell_element, p_element, marker: str, multiline_value: str):
    """
    Заменяет маркер на многострочное значение, разбивая на отдельные параграфы.

    Стратегия:
    - Первая строка значения подставляется в существующий <w:p>
    - Для остальных строк создаются deepcopy этого <w:p>, текст заменяется
    - Новые параграфы вставляются после оригинального в ячейке

    Это сохраняет форматирование (отступы, стиль, размер шрифта).
    """
    lines = multiline_value.split('\n')
    if not lines:
        _replace_marker_inline(p_element, marker, "")
        return

    # Заменяем маркер в первом параграфе на первую строку
    _replace_marker_inline(p_element, marker, lines[0])

    # Для остальных строк создаём копии параграфа
    parent_of_p = p_element.getparent()
    p_index = list(parent_of_p).index(p_element)
    insert_position = p_index + 1

    for line in lines[1:]:
        new_p = deepcopy(p_element)
        # В копии текст содержит lines[0] — заменим на текущую line
        ts_in_new = new_p.findall('.//w:t', NS)
        for t in ts_in_new:
            if t.text and lines[0] in t.text:
                t.text = t.text.replace(lines[0], line, 1)
                break
        parent_of_p.insert(insert_position, new_p)
        insert_position += 1


def _remove_empty_paragraph_between_tables(doc):
    """
    Pack 16.4: убирает пустой параграф между таблицей операций и таблицей подписи,
    чтобы подпись могла поместиться сразу после операций.
    """
    body = doc.element.body
    children = list(body)

    for i in range(len(children) - 2):
        if etree.QName(children[i]).localname != 'tbl':
            continue
        if etree.QName(children[i + 1]).localname != 'p':
            continue
        if etree.QName(children[i + 2]).localname != 'tbl':
            continue

        ts = children[i + 1].findall('.//w:t', NS)
        full_text = "".join(t.text or "" for t in ts).strip()

        if not full_text:
            body.remove(children[i + 1])
            break


def _apply_gray_shading_to_row(tr_element):
    """
    Pack 16.5: добавляет серый фон (E8E8E8) каждой ячейке строки таблицы.

    В оригинальной выписке Алиева строки с доходом (зарплата от компании) имеют
    серую заливку. Мы применяем тот же стиль к строкам с положительной суммой.

    Если в ячейке уже есть <w:shd>, она заменяется. Иначе создаётся новый.
    """
    cells = tr_element.findall('.//w:tc', NS)
    for cell in cells:
        tcPr = cell.find('w:tcPr', NS)
        if tcPr is None:
            tcPr = etree.SubElement(cell, f'{W_NS}tcPr')
            # tcPr должен идти первым в tc — переместим его
            cell.remove(tcPr)
            cell.insert(0, tcPr)

        # Удаляем старый shd если есть
        old_shd = tcPr.find('w:shd', NS)
        if old_shd is not None:
            tcPr.remove(old_shd)

        # Создаём новый
        shd = etree.SubElement(tcPr, f'{W_NS}shd')
        shd.set(f'{W_NS}val', 'clear')
        shd.set(f'{W_NS}color', 'auto')
        shd.set(f'{W_NS}fill', 'E8E8E8')


def _set_cant_split(tr_element):
    """
    Pack 16.5b: добавляет <w:cantSplit/> в <w:trPr> строки таблицы.

    Это запрещает Word разрывать строку между страницами — если строка
    не помещается на текущей странице, она ЦЕЛИКОМ переносится на
    следующую (стандарт банковских выписок).
    """
    trPr = tr_element.find('w:trPr', NS)
    if trPr is None:
        # Создаём trPr и кладём его первым (после положения tblPrEx)
        trPr = etree.Element(f'{W_NS}trPr')
        # Найдём куда вставить — trPr должен быть до <w:tc>
        tc_idx = None
        for i, child in enumerate(tr_element):
            if etree.QName(child).localname == 'tc':
                tc_idx = i
                break
        if tc_idx is not None:
            tr_element.insert(tc_idx, trPr)
        else:
            tr_element.append(trPr)

    # Проверим — может уже есть cantSplit
    existing = trPr.find('w:cantSplit', NS)
    if existing is None:
        cant_split = etree.SubElement(trPr, f'{W_NS}cantSplit')


def _set_keep_next_on_row(tr_element):
    """
    Pack 16.5c: добавляет <w:cantSplit/> и устанавливает на параграфы внутри ячеек
    атрибут keepNext через pPr — чтобы строка «прилипла» к следующему контенту.

    На уровне строки таблицы Word не понимает <w:keepNext/>. Чтобы строка
    держалась с подписью, ставим keepNext на ВСЕ параграфы в ячейках строки —
    это эквивалентный приём.
    """
    # На каждой ячейке строки — на каждом параграфе — добавляем <w:keepNext/>
    cells = tr_element.findall('.//w:tc', NS)
    for cell in cells:
        for p in cell.findall('.//w:p', NS):
            ppr = p.find('w:pPr', NS)
            if ppr is None:
                ppr = etree.Element(f'{W_NS}pPr')
                p.insert(0, ppr)

            if ppr.find('w:keepNext', NS) is None:
                # keepNext должен идти в начале pPr (после pStyle)
                keep_next = etree.SubElement(ppr, f'{W_NS}keepNext')


def _set_keep_next_on_paragraph_between_tables(doc):
    """
    Pack 16.5c: ставит keepNext на все параграфы между Table 0 (операции)
    и Table 1 (подпись), чтобы они не отрывались от подписи.
    """
    body = doc.element.body
    children = list(body)

    table_indexes = [i for i, c in enumerate(children) if etree.QName(c).localname == 'tbl']
    if len(table_indexes) < 2:
        return

    for i in range(table_indexes[0] + 1, table_indexes[1]):
        p = children[i]
        if etree.QName(p).localname != 'p':
            continue
        ppr = p.find('w:pPr', NS)
        if ppr is None:
            ppr = etree.Element(f'{W_NS}pPr')
            p.insert(0, ppr)
        if ppr.find('w:keepNext', NS) is None:
            etree.SubElement(ppr, f'{W_NS}keepNext')
