"""
Фиксит CV-шаблон после ручной правки в Word.

Word любит автокапитализировать первые буквы — превращает
{{ applicant.full_name_native|upper }} → {{ APPLICANT.full_name_native|UPPER }}.
Jinja чувствителен к регистру и падает с UndefinedError.

Этот скрипт открывает cv_template.docx, проходится по всем Jinja-выражениям
и приводит их к строчному виду. После запуска шаблон будет рендериться.

Запуск:
    python scripts/fix_cv_template.py
"""
import sys
import io
import re
import zipfile
import shutil
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "docx" / "cv_template.docx"
BACKUP_PATH = PROJECT_ROOT / "templates" / "docx" / "cv_template.before_fix.docx"


# Известные имена переменных, фильтров и хелперов в нашем контексте.
# Любые их написания (APPLICANT, Applicant, applicant) приведём к строчному виду.
KNOWN_NAMES = {
    # Переменные верхнего уровня
    "applicant", "company", "position", "contract", "representative",
    "spain_address", "letter", "eur", "act", "invoice", "monthly_documents",
    # Хелперы (функции в шаблоне)
    "fmt_date_ru", "fmt_date_long_ru", "fmt_date_human_ru",
    "fmt_money", "fmt_money_kop",
    # Jinja-фильтры
    "upper", "lower", "capitalize", "title", "join", "length",
    # Jinja-ключевые слова
    "for", "endfor", "if", "endif", "else", "elif", "in", "not",
    "and", "or", "is", "set", "endset",
}


def fix_jinja_block(text: str) -> str:
    """
    Внутри блока {{ ... }} или {% ... %} приводим имена и фильтры
    к строчному виду — но только те, которые есть в KNOWN_NAMES.
    """
    def fix_word(match):
        word = match.group(0)
        # Сравниваем регистронезависимо, но возвращаем строчную версию
        if word.lower() in KNOWN_NAMES:
            return word.lower()
        return word  # неизвестные слова не трогаем (это могут быть значения ключей)

    # Ищем "слова" — последовательности букв и подчёркиваний
    return re.sub(r"[A-Za-zА-Яа-я_]+", fix_word, text)


def fix_xml(xml: str) -> tuple[str, int]:
    """Находит все {{ ... }} и {% ... %} и фиксит их. Возвращает (новый xml, число замен)."""
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

    # {{ выражение }} или {% инструкция %}
    pattern = r"(\{\{|\{%)(.*?)(\}\}|%\})"
    new_xml = re.sub(pattern, fix_expr, xml, flags=re.DOTALL)
    return new_xml, count


def main():
    if not TEMPLATE_PATH.exists():
        print(f"[ERROR] Template not found: {TEMPLATE_PATH}")
        return 1

    # Бэкап
    shutil.copy(TEMPLATE_PATH, BACKUP_PATH)
    print(f"[OK] Backup: {BACKUP_PATH.name}")

    # Распаковываем DOCX (это ZIP), правим word/document.xml, упаковываем обратно
    tmp_dir = TEMPLATE_PATH.parent / "_cv_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    with zipfile.ZipFile(TEMPLATE_PATH, "r") as z:
        z.extractall(tmp_dir)

    # Правим основной XML и хедеры/футеры
    total_replacements = 0
    for xml_path in tmp_dir.rglob("*.xml"):
        # Только в word/ — там содержимое документа
        if "word" not in xml_path.parts:
            continue
        original = xml_path.read_text(encoding="utf-8")
        fixed, count = fix_xml(original)
        if count > 0:
            xml_path.write_text(fixed, encoding="utf-8")
            print(f"  [{count} fixes] {xml_path.relative_to(tmp_dir)}")
            total_replacements += count

    # Упаковываем обратно
    new_docx = TEMPLATE_PATH.parent / "_cv_new.docx"
    with zipfile.ZipFile(new_docx, "w", zipfile.ZIP_DEFLATED) as z:
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(tmp_dir).as_posix()
                z.write(f, arcname)

    # Заменяем оригинал
    shutil.rmtree(tmp_dir)
    TEMPLATE_PATH.unlink()
    new_docx.rename(TEMPLATE_PATH)

    print(f"[OK] Total fixes: {total_replacements}")
    print(f"[OK] Saved: {TEMPLATE_PATH.name}")
    print(f"     Backup at {BACKUP_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())