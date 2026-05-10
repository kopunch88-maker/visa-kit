"""
Pack 32.3 — лимит ≤2 страниц для банковской выписки.

Проблема:
  Генератор создаёт 35-50+ транзакций (зарплаты, НПД, KWIKPAY, комиссии, СБП,
  «Оплата услуг»). На 3 страницы и больше выписки растягиваются регулярно,
  особенно когда random выдаёт 8 СБП × multiline и 20 подписок.
  Менеджер требует: ≤2 страниц всегда.

Решение:
  В bank_statement_generator.generate_default_transactions, ПОСЛЕ hard-фильтра
  по периоду и ДО сортировки/подсчёта балансов, добавляется новый шаг
  «trim_to_page_budget» который:

  1. Считает «вес» каждой транзакции:
       weight = 1 + description.count('\\n')
     (single-line = 1.0, СБП multiline = 2.0, зарплата multiline = 5.0)

  2. Если суммарный вес > MAX_WEIGHT_BUDGET (38 — соответствует ~2 страницам
     с запасом, целевая «чуть меньше платежей»):
       a) Сначала удаляет случайные транзакции категории "Оплата услуг."
          (Boosty, Яндекс Плюс, Литрес и т.п.) — пока вес не уложится или
          они не закончатся.
       b) Если всё ещё перебор — удаляет лишние СБП-переводы, оставляя
          минимум MIN_SBP_KEEP=3 (для реалистичности).
       c) Зарплаты, НПД, KWIKPAY и комиссии не трогаем — это доказательная
          база для UGE/банка.

  3. Логирует сколько чего обрезали, общий вес до/после.

Безопасность:
  - Если даже все обязательные транзакции дают перебор (период >3 мес),
    просто warning в лог. Ничего не падает.
  - Бюджет настраиваемый через ENV var BANK_STATEMENT_MAX_WEIGHT (по умолчанию 38).
    Если у конкретного клиента 2 страниц получить не удаётся — менеджер
    может временно поднять бюджет.

Файлы:
  backend/app/services/bank_statement_generator.py — точечная вставка через str_replace

Запуск (PowerShell, из D:\\VISA\\visa_kit):
    python apply_pack32_3.py
    git add backend/app/services/bank_statement_generator.py
    git commit -m "Pack 32.3: bank statement page budget (max 2 pages)"
    git push
"""

from __future__ import annotations

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path


# =============================================================================
# Anchor & insertion
# =============================================================================
# Якорь — конец секции «онлайн-подписки», начало hard-фильтра.
# Используем уникальное место «Pack 25.8: hard-фильтр + sanity check»,
# которое стабильно присутствует в обоих версиях файла.

OLD_ANCHOR = '''    # === Pack 25.8: hard-фильтр + sanity check ===
    before = len(transactions)
    transactions = [
        t for t in transactions
        if period_start <= t["transaction_date"] <= period_end
    ]
    dropped = before - len(transactions)
    if dropped > 0:
        log.warning(
            "[Pack 25.8] dropped %d tx outside period %s..%s",
            dropped, period_start, period_end,
        )
    # Жёсткая проверка
    for t in transactions:
        assert period_start <= t["transaction_date"] <= period_end, (
            f"[Pack 25.8] tx {t['transaction_date']} outside period "
            f"{period_start}..{period_end} — generator bug"
        )

    # Сортируем от новой к старой (как в реальной выписке Альфы — последняя сверху)
    transactions.sort(key=lambda t: t["transaction_date"], reverse=True)'''

NEW_BLOCK = '''    # === Pack 25.8: hard-фильтр + sanity check ===
    before = len(transactions)
    transactions = [
        t for t in transactions
        if period_start <= t["transaction_date"] <= period_end
    ]
    dropped = before - len(transactions)
    if dropped > 0:
        log.warning(
            "[Pack 25.8] dropped %d tx outside period %s..%s",
            dropped, period_start, period_end,
        )
    # Жёсткая проверка
    for t in transactions:
        assert period_start <= t["transaction_date"] <= period_end, (
            f"[Pack 25.8] tx {t['transaction_date']} outside period "
            f"{period_start}..{period_end} — generator bug"
        )

    # === Pack 32.3: лимит ≤2 страниц через бюджет «веса строк» ===
    # Вес транзакции = 1 + count('\\n') в описании.
    # - single-line (KWIKPAY, НПД, комиссия, подписка) = 1.0
    # - СБП multiline (Получатель + банк/телефон) = 2.0
    # - Зарплата multiline (Плательщик + ИНН + Счёт + Назначение) = 5.0
    #
    # Эмпирически 1 страница A4 ~= 22 единицы веса (Word, Times New Roman 10,
    # шапка выписки + таблица). 2 страницы = 44, целевой бюджет 38 даёт запас
    # на orphan-control, разные размеры подписи, разрывы.
    #
    # Бюджет настраиваемый через ENV var BANK_STATEMENT_MAX_WEIGHT.
    import os as _os
    try:
        _max_weight = int(_os.environ.get("BANK_STATEMENT_MAX_WEIGHT", "38"))
    except (ValueError, TypeError):
        _max_weight = 38

    def _tx_weight(t: dict) -> float:
        desc = t.get("description") or ""
        return 1.0 + desc.count("\\n")

    def _is_subscription(t: dict) -> bool:
        desc = t.get("description") or ""
        return desc.startswith("Оплата услуг.")

    def _is_sbp(t: dict) -> bool:
        desc = t.get("description") or ""
        return desc.startswith("Перевод по СБП.")

    total_weight = sum(_tx_weight(t) for t in transactions)
    log.info(
        "[Pack 32.3] page budget: %d transactions, total_weight=%.1f, max=%d",
        len(transactions), total_weight, _max_weight,
    )

    if total_weight > _max_weight:
        # Шаг 1 — удаляем подписки случайно по одной, пока не уложимся.
        sub_indices = [i for i, t in enumerate(transactions) if _is_subscription(t)]
        random.shuffle(sub_indices)
        removed_subs = 0
        for idx in sub_indices:
            if total_weight <= _max_weight:
                break
            total_weight -= _tx_weight(transactions[idx])
            transactions[idx] = None  # tombstone — удалим скопом ниже
            removed_subs += 1

        # Шаг 2 — если всё ещё перебор, удаляем лишние СБП, но не ниже MIN_SBP_KEEP.
        MIN_SBP_KEEP = 3
        removed_sbp = 0
        if total_weight > _max_weight:
            sbp_indices = [
                i for i, t in enumerate(transactions)
                if t is not None and _is_sbp(t)
            ]
            keep_count = MIN_SBP_KEEP
            removable = max(0, len(sbp_indices) - keep_count)
            random.shuffle(sbp_indices)
            for idx in sbp_indices[:removable]:
                if total_weight <= _max_weight:
                    break
                total_weight -= _tx_weight(transactions[idx])
                transactions[idx] = None
                removed_sbp += 1

        # Скопом удаляем tombstones
        transactions = [t for t in transactions if t is not None]

        if total_weight > _max_weight:
            log.warning(
                "[Pack 32.3] page budget exceeded after trimming: "
                "weight=%.1f > max=%d (removed %d subs + %d sbp). "
                "Likely period_months > 3 — выписка может занять >2 страниц.",
                total_weight, _max_weight, removed_subs, removed_sbp,
            )
        else:
            log.info(
                "[Pack 32.3] trimmed %d subscriptions + %d sbp, "
                "now %d transactions, weight=%.1f",
                removed_subs, removed_sbp, len(transactions), total_weight,
            )
    # === конец Pack 32.3 ===

    # Сортируем от новой к старой (как в реальной выписке Альфы — последняя сверху)
    transactions.sort(key=lambda t: t["transaction_date"], reverse=True)'''


# =============================================================================
# Helpers
# =============================================================================

def assert_python_syntax(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    try:
        ast.parse(src)
    except SyntaxError as e:
        raise SystemExit(f"[FATAL] Python syntax error in {path}: {e}")


def patch_generator(repo_root: Path) -> None:
    path = repo_root / "backend" / "app" / "services" / "bank_statement_generator.py"
    if not path.exists():
        raise SystemExit(f"[FATAL] not found: {path}")

    text = path.read_text(encoding="utf-8")

    marker = "# === Pack 32.3: лимит ≤2 страниц через бюджет «веса строк» ==="
    if marker in text:
        print("    [SKIP] bank_statement_generator.py: Pack 32.3 уже применён")
        return

    if OLD_ANCHOR not in text:
        raise SystemExit(
            "[FATAL] bank_statement_generator.py: якорь не найден.\n"
            "        Ожидался блок '# === Pack 25.8: hard-фильтр + sanity check ===' "
            "с последующим hard-фильтром и sort.\n"
            "        Проверь, не изменялся ли файл вручную."
        )

    # Бэкап
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.name + f".bak_pre_pack32_3_{ts}")
    shutil.copy2(path, backup)
    print(f"    [OK] backup: {backup.name}")

    # Замена
    new_text = text.replace(OLD_ANCHOR, NEW_BLOCK, 1)
    path.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"    [OK] bank_statement_generator.py: вставлен блок Pack 32.3")

    # Проверка синтаксиса
    assert_python_syntax(path)
    print(f"    [OK] синтаксис Python валиден")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    repo_root = Path.cwd()
    print(f"== Pack 32.3 ==")
    print(f"   repo: {repo_root}")
    print()

    print("[1/1] backend/app/services/bank_statement_generator.py — добавляем page budget")
    patch_generator(repo_root)
    print()

    print("== DONE ==")
    print()
    print("Дальше:")
    print("    git add backend/app/services/bank_statement_generator.py")
    print('    git commit -m "Pack 32.3: bank statement page budget (max 2 pages)"')
    print("    git push")
    print()
    print("Railway пересоберёт backend за ~1-2 мин.")
    print()
    print("Тест:")
    print("  1. Открой любую заявку с готовой компанией и зарплатой")
    print("  2. Сгенерируй пакет → 10_Выписка.docx")
    print("  3. Открой в Word — должно быть ≤2 страниц")
    print("  4. В логах Railway увидишь:")
    print("     [Pack 32.3] page budget: NN transactions, total_weight=XX.X, max=38")
    print("     [Pack 32.3] trimmed N subscriptions + 0 sbp, now NN transactions, weight=XX.X")
    print()
    print("Если у конкретного клиента надо пушнуть бюджет (например period_months=6):")
    print("  Railway → Variables → BANK_STATEMENT_MAX_WEIGHT=44")
    print("  (стандарт 38, дальше через каждые 22 = +1 страница)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
