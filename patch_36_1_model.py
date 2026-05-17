import sys

path = r"D:\VISA\visa_kit\backend\app\models\application.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

anchor = "    is_ready_for_pickup: bool = Field(default=False, index=True)"

if anchor not in src:
    print("[1] ❌ якорь не найден")
    sys.exit(1)

new_src = src.replace(anchor, anchor + "\n    is_filed: bool = Field(default=False, index=True)  # Pack 36.0", 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(new_src)
print("[1] OK — is_filed добавлен в модель")