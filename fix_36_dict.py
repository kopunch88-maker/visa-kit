path = r"backend/app/api/applications.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

old = '    data["is_urgent"] = bool(getattr(app, "is_urgent", False))'
new = '    data["is_urgent"] = bool(getattr(app, "is_urgent", False))\n    data["is_filed"] = bool(getattr(app, "is_filed", False))'

if old not in src:
    print("ERROR: anchor not found"); exit(1)

src = src.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("OK")
