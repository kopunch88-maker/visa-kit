"""
Рендер DOCX-шаблонов через docxtpl.

Bank statement рендерится особым способом: после стандартного docxtpl-рендера
(подставляет шапку с балансами и периодом), мы открываем результат через
python-docx, находим строку-образец с маркерами __TX_*__ и клонируем её
для каждой транзакции, заменяя маркеры на реальные данные.

Это даёт таблицу 1-в-1 с эталоном Альфа-банка, потому что мы клонируем
её собственную XML-структуру, не пытаясь её воссоздать.
"""

import io
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docxtpl import DocxTemplate
from sqlmodel import Session

from app.models import Application
from .context import build_context


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "docx"


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
        # Проверяем, есть ли маркер __TX_DATE__ в первой ячейке второй строки
        second_row = table.rows[1]
        if second_row.cells and "__TX_DATE__" in second_row.cells[0].text:
            tx_table = table
            template_row = second_row
            break

    if tx_table is None or template_row is None:
        # Шаблон не содержит маркер-строку — возвращаем как есть
        result_buffer = io.BytesIO()
        doc.save(result_buffer)
        return result_buffer.getvalue()

    # Клонируем образцовую строку для каждой транзакции
    template_tr_xml = template_row._tr
    parent = template_tr_xml.getparent()
    insert_position = list(parent).index(template_tr_xml)

    for idx, tx in enumerate(transactions):
        new_tr = deepcopy(template_tr_xml)
        # Заменяем маркеры на реальные значения через прямой XML
        _replace_markers_in_tr(new_tr, tx)
        # Вставляем перед строкой-образцом (потом её удалим)
        parent.insert(insert_position + idx, new_tr)

    # Удаляем оригинальную строку-образец
    parent.remove(template_tr_xml)

    # Сохраняем результат
    result_buffer = io.BytesIO()
    doc.save(result_buffer)
    return result_buffer.getvalue()


def _replace_markers_in_tr(tr_element, tx: dict):
    """
    Идёт по всем <w:t> элементам внутри строки таблицы и заменяет маркеры
    на значения из словаря транзакции.

    Так как мы обходим именно <w:t> элементы (а не текст ячеек целиком),
    стили (size, color, spacing) сохраняются.
    """
    marker_to_value = {
        "__TX_DATE__": tx.get("date_formatted", ""),
        "__TX_CODE__": tx.get("code", ""),
        "__TX_DESCRIPTION__": tx.get("description", "") or "",
        "__TX_AMOUNT__": tx.get("amount_formatted", ""),
    }

    # Находим все <w:t> элементы и заменяем тексты-маркеры
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for t in tr_element.iter(f"{namespace}t"):
        if t.text and t.text in marker_to_value:
            t.text = marker_to_value[t.text]
