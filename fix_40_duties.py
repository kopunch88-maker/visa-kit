path = r"frontend/components/admin/ApplicantDrawer.tsx"
with open(path, encoding="utf-8") as f:
    src = f.read()

old = """                {/* Pack 19.1a: duties \u043e\u0442\u043e\u0431\u0440\u0430\u0436\u0430\u044e\u0442\u0441\u044f read-only \u0435\u0441\u043b\u0438 \u0435\u0441\u0442\u044c, \u0432 19.1b \u0431\u0443\u0434\u0435\u0442 \u0440\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u0443\u0435\u043c\u043e */}
                {wh.duties && wh.duties.length > 0 && (
                  <div>
                    <label
                      className="text-xs block mb-1"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      \u041e\u0431\u044f\u0437\u0430\u043d\u043d\u043e\u0441\u0442\u0438 ({wh.duties.length})
                    </label>
                    <div
                      className="text-xs px-2 py-1 rounded"
                      style={{
                        background: "var(--color-bg-primary)",
                        border: "1px solid var(--color-border-tertiary)",
                        color: "var(--color-text-secondary)",
                      }}
                    >
                      {wh.duties.join(" \u2022 ")}
                    </div>
                  </div>
                )}"""

new = """                {/* Pack 19.1b: duties \u0440\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u0443\u0435\u043c\u044b */}
                <div>
                  <label
                    className="text-xs block mb-1"
                    style={{ color: "var(--color-text-tertiary)" }}
                  >
                    \u041e\u0431\u044f\u0437\u0430\u043d\u043d\u043e\u0441\u0442\u0438 ({(wh.duties || []).length})
                  </label>
                  {(wh.duties || []).map((duty, di) => (
                    <div key={di} className="flex gap-1 mb-1">
                      <textarea
                        value={duty}
                        onChange={(e) => {
                          const next = [...workHistory];
                          const duties = [...(next[i].duties || [])];
                          duties[di] = e.target.value;
                          next[i] = { ...next[i], duties };
                          setWorkHistory(next);
                        }}
                        rows={2}
                        className="w-full px-2 py-1 rounded text-xs"
                        style={{
                          background: "var(--color-bg-primary)",
                          border: "1px solid var(--color-border-tertiary)",
                          color: "var(--color-text-primary)",
                          resize: "vertical",
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const next = [...workHistory];
                          const duties = (next[i].duties || []).filter((_, idx) => idx !== di);
                          next[i] = { ...next[i], duties };
                          setWorkHistory(next);
                        }}
                        className="p-1 rounded hover:bg-red-50 self-start mt-0.5"
                        title="\u0423\u0434\u0430\u043b\u0438\u0442\u044c"
                      >
                        <Trash2 size={12} style={{ color: "#dc2626" }} />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      const next = [...workHistory];
                      next[i] = { ...next[i], duties: [...(next[i].duties || []), ""] };
                      setWorkHistory(next);
                    }}
                    className="text-xs px-2 py-1 rounded mt-1"
                    style={{
                      background: "var(--color-bg-secondary)",
                      border: "1px solid var(--color-border-tertiary)",
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    + \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043e\u0431\u044f\u0437\u0430\u043d\u043d\u043e\u0441\u0442\u044c
                  </button>
                </div>"""

if old not in src:
    print("ERROR: not found"); exit(1)
src = src.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("OK")
