path = r"frontend/components/admin/ApplicationDetail.tsx"
with open(path, encoding="utf-8") as f:
    src = f.read()

old = "                  try { await toggleFiled(application.id); await loadAll(); onUpdated(); }"
new = """                  try {
                    await toggleFiled(application.id);
                    // Pack 36.2 — синхронизируем статус с флагом
                    if (!application.is_filed && application.status !== "submitted") {
                      await updateStatus(applicationId, "submitted");
                    } else if (application.is_filed && application.status === "submitted") {
                      await updateStatus(applicationId, "drafts_generated");
                    }
                    await loadAll(); onUpdated();
                  }"""

if old not in src:
    print("ERROR: anchor not found"); exit(1)
src = src.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("OK")
