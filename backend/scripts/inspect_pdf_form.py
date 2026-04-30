"""
PDF AcroForm Inspector — печатает все имена полей в PDF-форме.

Запускается перед началом работы с новой PDF-формой, чтобы узнать
точные имена полей которые потом будем заполнять программно.

Использование:
    cd D:\\VISA\\visa_kit\\backend
    python scripts\\inspect_pdf_form.py путь\\к\\форме.pdf

Например:
    python scripts\\inspect_pdf_form.py D:\\VISA\\PDF_Forms\\MI_T.pdf
    python scripts\\inspect_pdf_form.py D:\\VISA\\PDF_Forms\\DESIGNACION.pdf
"""

import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

if len(sys.argv) < 2:
    print("Usage: python inspect_pdf_form.py <path_to_pdf>")
    sys.exit(1)

pdf_path = Path(sys.argv[1])
if not pdf_path.exists():
    print(f"[ERROR] File not found: {pdf_path}")
    sys.exit(1)

# Установка pypdf если нет
try:
    from pypdf import PdfReader
except ImportError:
    print("[INFO] Installing pypdf...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pypdf"])
    from pypdf import PdfReader

reader = PdfReader(str(pdf_path))

# Получаем все поля формы
fields = reader.get_fields()

if not fields:
    print(f"[WARN] No AcroForm fields found in {pdf_path.name}")
    print("       This PDF might be a scan or have flattened fields.")
    sys.exit(1)

print(f"=== AcroForm fields in {pdf_path.name} ===")
print(f"Total fields: {len(fields)}\n")

# Печатаем по одному на строку: имя поля, тип, текущее значение
for i, (name, field) in enumerate(fields.items(), 1):
    field_type = field.get("/FT", "?")
    # Расшифровка типов:
    type_map = {
        "/Tx": "Text",
        "/Btn": "Button/Checkbox",
        "/Ch": "Choice",
        "/Sig": "Signature",
    }
    type_str = type_map.get(str(field_type), str(field_type))
    
    current_value = field.get("/V", "")
    if current_value:
        current_value = str(current_value)[:40]
    
    print(f"{i:3d}. {name!r:50s}  type={type_str:20s}  value={current_value!r}")

print()
print("Скопируйте этот вывод и пришлите Claude — он использует эти имена в коде.")