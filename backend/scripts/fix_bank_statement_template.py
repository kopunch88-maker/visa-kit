"""
Фиксит bank_statement_template.docx после ручной правки в Word.

Word любит капитализировать первые буквы переменных. Этот скрипт
проходит по XML внутри DOCX и приводит все Jinja-имена к строчному виду.

Запуск:
    python scripts/fix_bank_statement_template.py
"""
import sys
import io
import re
import zipfile
import shutil
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "docx" / "bank_statement_template.docx"
BACKUP_PATH = PROJECT_ROOT / "templates" / "docx" / "bank_statement_template.before_fix.docx"


KNOWN_NAMES = {
    "applicant", "company", "position", "contract", "representative",
    "spain_address", "letter", "eur", "act", "invoice", "monthly_documents",
    "bank", "transaction", "transactions",
    "fmt_date_ru", "fmt_date_long_ru", "fmt_date_human_ru",
    "fmt_money", "fmt_money_kop", "fmt_amount_signed",
    "upper", "lower", "capitalize", "title", "join", "length",
    "for", "endfor", "if", "endif", "else", "elif", "in", "not",
    "and", "or", "is", "set", "endset",
    # Поля внутри bank
    "period_start", "period_end", "opening_balance", "closing_balance",
    "total_income", "total_expense",
    "period_start_formatted", "period_end_formatted",
    "opening_balance_formatted", "closing_balance_formatted",
    "total_income_formatted", "total_expense_formatted",
    "transaction_date", "code", "description", "amount", "currency",
    "amount_formatted", "date_formatted",
}


def fix_jinja_block(text: str) -> str:
    def fix_word(match):
        word = match.group(0)
        if word.lower() in KNOWN_NAMES:
            return word.lower()
        return word

    return re.sub(r"[A-Za-zА-Яа-я_]+", fix_word, text)


def fix_xml(xml: str) -> tuple[str, int]:
    count = 0

    def fix_expr(match):
        nonlocal count
        original = match.group(0)
        opener = match.group(1)
        body = match.group(2)
        closer = match.group(3)
        fixed_body = fix_jinja_block(body)
        result = f"{opener}{fixed_body}{closer}"
        if result != original:
            count += 1
        return result

    pattern = r"(\{\{|\{%)(.*?)(\}\}|%\})"
    new_xml = re.sub(pattern, fix_expr, xml, flags=re.DOTALL)
    return new_xml, count


def main():
    if not TEMPLATE_PATH.exists():
        print(f"[ERROR] Template not found: {TEMPLATE_PATH}")
        return 1

    shutil.copy(TEMPLATE_PATH, BACKUP_PATH)
    print(f"[OK] Backup: {BACKUP_PATH.name}")

    tmp_dir = TEMPLATE_PATH.parent / "_bank_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    with zipfile.ZipFile(TEMPLATE_PATH, "r") as z:
        z.extractall(tmp_dir)

    total_replacements = 0
    for xml_path in tmp_dir.rglob("*.xml"):
        if "word" not in xml_path.parts:
            continue
        original = xml_path.read_text(encoding="utf-8")
        fixed, count = fix_xml(original)
        if count > 0:
            xml_path.write_text(fixed, encoding="utf-8")
            print(f"  [{count} fixes] {xml_path.relative_to(tmp_dir)}")
            total_replacements += count

    new_docx = TEMPLATE_PATH.parent / "_bank_new.docx"
    with zipfile.ZipFile(new_docx, "w", zipfile.ZIP_DEFLATED) as z:
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(tmp_dir).as_posix()
                z.write(f, arcname)

    shutil.rmtree(tmp_dir)
    TEMPLATE_PATH.unlink()
    new_docx.rename(TEMPLATE_PATH)

    print(f"[OK] Total fixes: {total_replacements}")
    print(f"[OK] Saved: {TEMPLATE_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
