# inspect_tech_opinion_template.py
import zipfile, re, html

z = zipfile.ZipFile(r"D:\VISA\visa_kit\templates\docx\tech_opinion_template.docx")
xml = z.read("word/document.xml").decode("utf-8")

# Соберём текст по <w:t> элементам (без форматирующих тегов)
text_parts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
plain = "".join(text_parts)

print("=" * 80)
print("Все плейсхолдеры {{ ... }} в шаблоне (с контекстом ±60 символов):")
print("=" * 80)

for m in re.finditer(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", plain):
    var = m.group(1)
    start = max(0, m.start() - 60)
    end = min(len(plain), m.end() + 60)
    ctx = plain[start:end].replace("\n", " ")
    print(f"\n[{var}]")
    print(f"  ...{ctx}...")