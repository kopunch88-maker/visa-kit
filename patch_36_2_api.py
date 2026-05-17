import sys

path = r"D:\VISA\visa_kit\frontend\lib\api.ts"
with open(path, encoding="utf-8") as f:
    src = f.read()

# Добавить is_filed в тип
anchor1 = "  is_urgent?: boolean;"
if anchor1 not in src:
    print("[1] ❌ якорь is_urgent не найден"); sys.exit(1)
src = src.replace(anchor1, anchor1 + "\n  is_filed?: boolean;  // Pack 36.0", 1)
print("[1] OK — is_filed в тип")

# Добавить toggleFiled функцию
anchor2 = "export async function unarchiveApplication"
if anchor2 not in src:
    print("[2] ❌ якорь unarchiveApplication не найден"); sys.exit(1)

insert = """export async function toggleFiled(appId: number): Promise<ApplicationResponse> {
  const res = await fetch(`${API_BASE_URL}/api/admin/applications/${appId}/toggle-filed`, {
    method: "POST", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`toggle-filed: ${res.status} ${await res.text()}`);
  return res.json();
}
// Pack 36.0 end

"""
src = src.replace(anchor2, insert + anchor2, 1)
print("[2] OK — toggleFiled добавлен")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("Готово")