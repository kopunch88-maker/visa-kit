# 1. Убрать "Поданы" из STATUS_TABS в api.ts
path = r"frontend/lib/api.ts"
with open(path, encoding="utf-8") as f:
    src = f.read()

old = '  { id: "submitted", label: "\u041f\u043e\u0434\u0430\u043d\u044b", statuses: ["submitted"] },\n'
if old not in src:
    print("ERROR [1]: submitted tab not found"); exit(1)
src = src.replace(old, "", 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("[1] OK - Поданы убраны из STATUS_TABS")

# 2. handleStatusChange — если submitted, автоматом toggleFiled
path2 = r"frontend/components/admin/ApplicationDetail.tsx"
with open(path2, encoding="utf-8") as f:
    src2 = f.read()

old2 = """  async function handleStatusChange(newStatus: string) {
    try {
      await updateStatus(applicationId, newStatus);
      await loadAll();
      onUpdated();
    } catch (e) {
      alert(`\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0441\u0442\u0430\u0442\u0443\u0441: ${(e as Error).message}`);
    }
  }"""

new2 = """  async function handleStatusChange(newStatus: string) {
    try {
      await updateStatus(applicationId, newStatus);
      // Pack 36.1 — статус "Подана" автоматически ставит флаг is_filed
      if (newStatus === "submitted" && !application.is_filed) {
        await toggleFiled(application.id);
      } else if (newStatus !== "submitted" && application.is_filed) {
        await toggleFiled(application.id);
      }
      await loadAll();
      onUpdated();
    } catch (e) {
      alert(`\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0441\u0442\u0430\u0442\u0443\u0441: ${(e as Error).message}`);
    }
  }"""

if old2 not in src2:
    print("ERROR [2]: handleStatusChange not found"); exit(1)
src2 = src2.replace(old2, new2, 1)
with open(path2, "w", encoding="utf-8") as f:
    f.write(src2)
print("[2] OK - handleStatusChange обновлён")
print("Готово")
