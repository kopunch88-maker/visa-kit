path = "backend/app/api/applications.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

old = """def toggle_filed(
    app_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):"""

new = """def toggle_filed(
    app_id: int,
    db: Session = Depends(get_session),
    _: str = Depends(require_manager),
):"""

if old not in src:
    print("ERROR: block not found"); exit(1)

src = src.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("OK")
