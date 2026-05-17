import sys

path = r"D:\VISA\visa_kit\backend\app\api\applications.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

anchor = '''# Pack 34.2'''

insert = '''# Pack 36.0 — флаг «Подан» (toggle)

@router.post("/{app_id}/toggle-filed")
def toggle_filed(
    app_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.is_filed = not bool(app.is_filed)
    db.commit()
    db.refresh(app)
    return _app_to_dict(app, db)


'''

if anchor not in src:
    print("[1] ❌ якорь не найден")
    sys.exit(1)

new_src = src.replace(anchor, insert + anchor, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(new_src)
print("[1] OK — toggle-filed добавлен")