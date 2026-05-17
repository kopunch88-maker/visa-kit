path = r"frontend/app/admin/page.tsx"
with open(path, encoding="utf-8") as f:
    src = f.read()

# Убираем старый блок вкладок сверху И заголовок, вставляем вкладки внутрь flex-строки
old = """      {/* Pack 36.0 \u2014 \u0433\u043b\u0430\u0432\u043d\u044b\u0435 \u0432\u043a\u043b\u0430\u0434\u043a\u0438 */}
      <div className="flex gap-1 mb-3">
        {([["applications", "\u0417\u0430\u044f\u0432\u043a\u0438"], ["filed", "\u041f\u043e\u0434\u0430\u043d\u044b"]] as const).map(([id, label]) => (
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
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h1 className="text-xl font-semibold text-primary">
          \u0417\u0430\u044f\u0432\u043a\u0438 <span className="text-tertiary text-sm font-normal">({applications.length})</span>
        </h1>"""

new = """      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex gap-1">
          {([["applications", "\u0417\u0430\u044f\u0432\u043a\u0438"], ["filed", "\u041f\u043e\u0434\u0430\u043d\u044b"]] as const).map(([id, label]) => (
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
        </div>"""

if old not in src:
    print("ERROR: not found"); exit(1)
src = src.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("OK")
