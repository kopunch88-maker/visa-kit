path = r"backend/app/api/applications.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

old = "    return _app_to_dict(app, db)"
new = "    db.refresh(app)\n    return _enrich(app, db)"

if old not in src:
    print("ERROR: not found"); exit(1)

src = src.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("OK")
