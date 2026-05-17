path = r"backend/app/api/applications.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

old_block = (
    "# Pack 36.0 \u2014 \u0444\u043b\u0430\u0433 \u00ab\u041f\u043e\u0434\u0430\u043d\u00bb (toggle)\n\n"
    "@router.post(\"/{app_id}/toggle-filed\")\n"
    "def toggle_filed(\n"
    "    app_id: int,\n"
    "    db: Session = Depends(get_db),\n"
    "    _: str = Depends(require_admin),\n"
    "):\n"
    "    app = db.query(Application).filter(Application.id == app_id).first()\n"
    "    if not app:\n"
    "        raise HTTPException(status_code=404, detail=\"Application not found\")\n"
    "    app.is_filed = not bool(app.is_filed)\n"
    "    db.commit()\n"
    "    db.refresh(app)\n"
    "    return _app_to_dict(app, db)\n\n\n"
)

if old_block not in src:
    print("ERROR: block not found")
    exit(1)

src = src.replace(old_block, "", 1)
anchor = "# Pack 34.2"
if anchor not in src:
    print("ERROR: anchor not found")
    exit(1)

src = src.replace(anchor, old_block + anchor, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("OK")
