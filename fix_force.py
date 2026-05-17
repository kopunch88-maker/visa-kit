path = "backend/app/api/applications.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

# Проверим где стоит toggle-filed относительно get_db import
idx_filed = src.find("def toggle_filed")
idx_getdb_import = src.find("from app.db")
print(f"toggle_filed at: {idx_filed}")
print(f"from app.db at: {idx_getdb_import}")
print(f"OK" if idx_filed > idx_getdb_import else "BAD - filed before imports")
