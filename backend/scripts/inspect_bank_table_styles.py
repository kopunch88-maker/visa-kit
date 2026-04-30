"""
Извлекает форматирование таблицы транзакций из _bank_statement_original.docx.

Сохраняет XML стилей в файл, чтобы потом использовать их при программной
сборке таблицы.

Запуск:
    python scripts/inspect_bank_table_styles.py
"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT_ROOT / "templates" / "docx" / "_bank_statement_original.docx"
OUT_DIR = Path(__file__).resolve().parents[1] / "scripts" / "_dumps"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = Document(str(SOURCE))

    # Найти таблицу транзакций
    tx_table = None
    for table in doc.tables:
        if not table.rows:
            continue
        first_row_text = " ".join(cell.text for cell in table.rows[0].cells)
        if "Дата проводки" in first_row_text and "Код операции" in first_row_text:
            tx_table = table
            break

    if not tx_table:
        print("[ERROR] Transactions table not found")
        return 1

    print(f"Found table: {len(tx_table.rows)} rows x {len(tx_table.columns)} cols")

    # 1. tblPr (свойства всей таблицы)
    tbl = tx_table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is not None:
        xml_str = etree.tostring(tblPr, pretty_print=True).decode("utf-8")
        (OUT_DIR / "bank_table_tblPr.xml").write_text(xml_str, encoding="utf-8")
        print(f"  Saved tblPr to bank_table_tblPr.xml")

    # 2. tblGrid (ширины колонок)
    tblGrid = tbl.find(qn("w:tblGrid"))
    if tblGrid is not None:
        xml_str = etree.tostring(tblGrid, pretty_print=True).decode("utf-8")
        (OUT_DIR / "bank_table_tblGrid.xml").write_text(xml_str, encoding="utf-8")
        print(f"  Saved tblGrid to bank_table_tblGrid.xml")

    # 3. Первая строка (заголовок)
    if tx_table.rows:
        header_row = tx_table.rows[0]
        xml_str = etree.tostring(header_row._tr, pretty_print=True).decode("utf-8")
        (OUT_DIR / "bank_table_header_row.xml").write_text(xml_str, encoding="utf-8")
        print(f"  Saved header row to bank_table_header_row.xml")

    # 4. Первая строка с транзакцией (если есть) — это образец строки данных
    if len(tx_table.rows) >= 2:
        data_row = tx_table.rows[1]
        xml_str = etree.tostring(data_row._tr, pretty_print=True).decode("utf-8")
        (OUT_DIR / "bank_table_data_row.xml").write_text(xml_str, encoding="utf-8")
        print(f"  Saved data row to bank_table_data_row.xml")

    print()
    print("==== РЕЗУЛЬТАТ ====")
    print(f"4 файла сохранены в {OUT_DIR}")
    print("Пришлите их Claude для анализа.")
    return 0


if __name__ == "__main__":
    sys.exit(main())