"""
Глубокий фикс bank_statement_template.docx после ручной правки в Word.

Word наделал нескольких типов автозамен:
1. Обратные кавычки `...` вокруг Jinja-выражений → удаляем
2. Гиперссылки на доменах "bank.total..." → разворачиваем обратно в текст
3. Не хватает закрывающего {%tr endfor %} → добавляем
4. Замена не нашла "Расходы 1 171 778,54 RUR" → добавляем

Запуск:
    python scripts/fix_bank_statement_thoroughly.py
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
BACKUP_PATH = PROJECT_ROOT / "templates" / "docx" / "bank_statement_template.before_thorough_fix.docx"


def fix_xml(xml: str) -> tuple[str, list[str]]:
    """Возвращает (исправленный xml, лог изменений)."""
    log = []

    # === 1. Удаляем гиперссылки которые Word создал на bank.total и подобное ===
    # Word превращает "bank.total_income_formatted" в <w:hyperlink>...</w:hyperlink>
    # Нам нужно вытащить из них чистый текст и убрать обёртку
    hyperlink_pattern = r'<w:hyperlink[^>]*>(.*?)</w:hyperlink>'
    hyperlinks = re.findall(hyperlink_pattern, xml, flags=re.DOTALL)
    if hyperlinks:
        for hl in hyperlinks:
            # Проверяем содержит ли гиперссылка bank/applicant/etc — только такие убираем
            if any(name in hl for name in ["bank.", "applicant.", "company.", "transaction."]):
                xml = xml.replace(f'<w:hyperlink>{hl}</w:hyperlink>', hl, 1)
        # Универсально убираем оставшиеся <w:hyperlink ...>...</w:hyperlink>, оставляя содержимое
        new_xml = re.sub(
            r'<w:hyperlink[^>]*>(.*?)</w:hyperlink>',
            r'\1',
            xml,
            flags=re.DOTALL,
        )
        if new_xml != xml:
            log.append(f"Removed hyperlink wrappers")
            xml = new_xml

    # === 2. Убираем обратные кавычки вокруг Jinja-выражений ===
    # Word превращает {{ X }} в `{{ X }}` (форматирование "Code")
    # В XML это видно как run с текстом "`" + run с {{ X }} + run с "`"
    # Простейший вариант — удалить все одиночные ` (backtick) символы из XML
    # Это безопасно потому что в нормальном тексте бэктики редкость
    backtick_count = xml.count("`")
    if backtick_count > 0:
        xml = xml.replace("`", "")
        log.append(f"Removed {backtick_count} backtick characters")

    # === 3. Добавляем закрывающий {%tr endfor %} ===
    # Если в шаблоне есть {%tr for transaction но нет {%tr endfor — добавляем
    has_for = "{%tr for transaction" in xml or "{% tr for transaction" in xml or "{%tr for  transaction" in xml
    has_endfor = "{%tr endfor" in xml or "{% tr endfor" in xml

    if has_for and not has_endfor:
        # Ищем последнее вхождение {{ transaction.amount_formatted }} 
        # (это последняя ячейка строки с циклом) и добавляем после него endfor
        marker = "{{ transaction.amount_formatted }}"
        # Возможно Word разорвал переменную на runs — надёжнее найти amount_formatted
        if "amount_formatted" in xml:
            # Находим последнее вхождение закрывающей скобки }} после amount_formatted
            last_amount_pos = xml.rfind("amount_formatted")
            closing_pos = xml.find("}}", last_amount_pos)
            if closing_pos != -1:
                insert_pos = closing_pos + 2
                xml = xml[:insert_pos] + "{%tr endfor %}" + xml[insert_pos:]
                log.append("Added closing {%tr endfor %} after last amount_formatted")
            else:
                log.append("WARNING: could not find }} to insert endfor after")
        else:
            log.append("WARNING: no 'amount_formatted' found in template")

    # === 4. Замена "Расходы" если осталась ===
    # Текст "1 171 778,54 RUR" может быть разбит Word на несколько runs
    # Попробуем простой случай — текст в одном run
    if "1 171 778,54 RUR" in xml:
        xml = xml.replace("1 171 778,54 RUR", "{{ bank.total_expense_formatted }}")
        log.append("Replaced 'Расходы 1 171 778,54 RUR'")
    elif "1 171 778,54" in xml:
        # Просто замена цифр (если "RUR" в другом run)
        xml = xml.replace("1 171 778,54", "{{ bank.total_expense_formatted }}")
        log.append("Replaced '1 171 778,54' (without RUR)")

    return xml, log


def main():
    if not TEMPLATE_PATH.exists():
        print(f"[ERROR] Template not found: {TEMPLATE_PATH}")
        return 1

    shutil.copy(TEMPLATE_PATH, BACKUP_PATH)
    print(f"[OK] Backup: {BACKUP_PATH.name}")

    tmp_dir = TEMPLATE_PATH.parent / "_bank_thorough_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    with zipfile.ZipFile(TEMPLATE_PATH, "r") as z:
        z.extractall(tmp_dir)

    total_log = []
    for xml_path in tmp_dir.rglob("*.xml"):
        if "word" not in xml_path.parts:
            continue
        original = xml_path.read_text(encoding="utf-8")
        fixed, log = fix_xml(original)
        if log:
            xml_path.write_text(fixed, encoding="utf-8")
            print(f"  In {xml_path.relative_to(tmp_dir)}:")
            for entry in log:
                print(f"    - {entry}")
            total_log.extend(log)

    new_docx = TEMPLATE_PATH.parent / "_bank_thorough_new.docx"
    with zipfile.ZipFile(new_docx, "w", zipfile.ZIP_DEFLATED) as z:
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(tmp_dir).as_posix()
                z.write(f, arcname)

    shutil.rmtree(tmp_dir)
    TEMPLATE_PATH.unlink()
    new_docx.rename(TEMPLATE_PATH)

    print()
    print(f"[OK] Total changes: {len(total_log)}")
    print(f"[OK] Saved: {TEMPLATE_PATH.name}")
    print(f"     Backup: {BACKUP_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())