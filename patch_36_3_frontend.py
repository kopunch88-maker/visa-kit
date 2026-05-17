import sys

# ===== 1. ApplicationDetail.tsx — импорт toggleFiled =====
path = r"D:\VISA\visa_kit\frontend\components\admin\ApplicationDetail.tsx"
with open(path, encoding="utf-8") as f:
    src = f.read()

anchor = "import { UrgentToggleButton } from \"./UrgentToggleButton\";"
if anchor not in src:
    print("[1] ❌ якорь UrgentToggleButton не найден"); sys.exit(1)
src = src.replace(anchor, "import { toggleFiled } from \"@/lib/api\";\n" + anchor, 1)
print("[1] OK — импорт toggleFiled")

# ===== 2. ApplicationDetail.tsx — кнопка «Подан» рядом с именем =====
anchor2 = "              <h2 className=\"text-2xl font-bold text-primary leading-tight\">"
if anchor2 not in src:
    print("[2] ❌ якорь h2 не найден"); sys.exit(1)

btn = """              <button
                onClick={async () => {
                  try { await toggleFiled(application.id); await loadAll(); onUpdated(); }
                  catch (e) { alert(`Ошибка: ${(e as Error).message}`); }
                }}
                className="px-2.5 py-1 rounded-md text-xs font-semibold transition-colors"
                style={application.is_filed
                  ? { background: "#eab308", color: "#fff" }
                  : { background: "var(--color-bg-secondary)", color: "var(--color-text-secondary)", border: "0.5px solid var(--color-border-tertiary)" }
                }
                title={application.is_filed ? "Снять отметку «Подан»" : "Отметить как поданную"}
              >
                {application.is_filed ? "✓ Подан" : "Подан"}
              </button>
"""
src = src.replace(anchor2, btn + anchor2, 1)
print("[2] OK — кнопка Подан")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("[ApplicationDetail] готово")

# ===== 3. page.tsx — две вкладки «Заявки» / «Поданы» =====
path2 = r"D:\VISA\visa_kit\frontend\app\admin\page.tsx"
with open(path2, encoding="utf-8") as f:
    src2 = f.read()

# Добавить состояние mainTab
anchor3 = "  const [showImportDialog, setShowImportDialog] = useState(false);"
if anchor3 not in src2:
    print("[3] ❌ якорь showImportDialog не найден"); sys.exit(1)
src2 = src2.replace(anchor3, "  const [mainTab, setMainTab] = useState<\"applications\" | \"filed\">(\"applications\");\n  " + anchor3, 1)
print("[3] OK — состояние mainTab")

# Фильтрация по mainTab — заменить filteredApplications
anchor4 = "  const filteredApplications = useMemo(() => {\n    let filtered = applications;"
if anchor4 not in src2:
    print("[4] ❌ якорь filteredApplications не найден"); sys.exit(1)
src2 = src2.replace(
    anchor4,
    "  const filteredApplications = useMemo(() => {\n    let filtered = mainTab === \"filed\"\n      ? applications.filter((a) => a.is_filed)\n      : applications.filter((a) => !a.is_filed);",
    1
)
print("[4] OK — фильтрация по mainTab")

# Добавить зависимость mainTab в filteredApplications useMemo
anchor5 = "  }, [applications, activeTab, searchQuery]);"
if anchor5 not in src2:
    print("[5] ❌ якорь useMemo deps не найден"); sys.exit(1)
src2 = src2.replace(anchor5, "  }, [applications, activeTab, searchQuery, mainTab]);", 1)
print("[5] OK — deps mainTab")

# Добавить вкладки перед заголовком «Заявки»
anchor6 = "      <div className=\"flex items-center justify-between mb-4 flex-wrap gap-2\">"
if anchor6 not in src2:
    print("[6] ❌ якорь header не найден"); sys.exit(1)

tabs_ui = """      {/* Pack 36.0 — главные вкладки */}
      <div className="flex gap-1 mb-3">
        {([["applications", "Заявки"], ["filed", "Поданы"]] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setMainTab(id)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              mainTab === id ? "text-primary" : "text-secondary hover:bg-secondary"
            }`}
            style={mainTab === id ? { background: "var(--color-bg-secondary)" } : {}}
          >
            {label}
            <span className="ml-1.5 text-xs text-tertiary">
              {id === "filed"
                ? applications.filter((a) => a.is_filed).length
                : applications.filter((a) => !a.is_filed).length}
            </span>
          </button>
        ))}
      </div>
"""
src2 = src2.replace(anchor6, tabs_ui + anchor6, 1)
print("[6] OK — вкладки добавлены")

with open(path2, "w", encoding="utf-8") as f:
    f.write(src2)
print("[page.tsx] готово")
print("\n✅ Все патчи применены")