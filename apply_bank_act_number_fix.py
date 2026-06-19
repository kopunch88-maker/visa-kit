"""
apply_bank_act_number_fix.py

Фикс: в банковской выписке САМОЗАНЯТОГО номер акта в назначении платежа
подставлялся по порядковому индексу цикла (idx+1 → 1/26, 2/26, 3/26),
а акт-ДОКУМЕНТ (context.py, Pack 25.6 v2) нумеруется по КАЛЕНДАРНОМУ месяцу
(period_start.month → 03/26, 04/26, 05/26). Из-за этого номера актов в
собранных документах не совпадали с номерами в выписке у любого клиента,
чей договор начинается не в январе (кейс: Усмонжонов А.Б.У.).

Правка: bank_statement_generator.py, строка income_desc —
    f"Акт №{idx + 1}/{year % 100:02d} ..."   →   f"Акт №{month:02d}/{year % 100:02d} ..."
Теперь номер акта в выписке = той же формуле MM/YY, что и display_number в документах.

Миграция БД НЕ требуется. Это правка только текста назначения платежа.

ВАЖНО после деплоя: у клиентов с уже сохранённой выпиской
(application.bank_transactions_override) рендер берёт текст из БД — код-фикс
сам её не перепишет. Нужно нажать «Перегенерировать выписку» в дровере
(перезапустит generate_default_transactions), и при наличии ES-версии —
заново «Перевести выписку» (Pack 53, отдельный PDF).

Запуск (из backend/ или из корня репо — путь резолвится автоматически):
    python apply_bank_act_number_fix.py
"""

import datetime
import shutil
import sys
from pathlib import Path

REL = Path("app/services/bank_statement_generator.py")

# Якорь уникален в файле (единственное место, где формируется номер акта).
OLD = "Акт №{idx + 1}/"
NEW = "Акт №{month:02d}/"


def _resolve_target() -> Path:
    """Находит bank_statement_generator.py независимо от того, откуда запущен скрипт."""
    here = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / REL,            # запуск из backend/
        Path.cwd() / "backend" / REL,  # запуск из корня репо
        here / REL,                  # скрипт лежит в backend/
        here / "backend" / REL,      # скрипт лежит в корне репо
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    print("[FAIL] Не нашёл app/services/bank_statement_generator.py.")
    print("       Запускай из backend/ или из корня репо, рядом с папкой backend.")
    sys.exit(1)


def main() -> None:
    target = _resolve_target()
    text = target.read_text(encoding="utf-8")

    if NEW in text:
        print("[SKIP] Уже применено (нашёл 'Акт №{month:02d}/').")
        return

    n = text.count(OLD)
    if n != 1:
        print(f"[FAIL] Якорь '{OLD}' встречается {n} раз (ожидал ровно 1). "
              f"Проверь файл вручную — правку не делаю.")
        sys.exit(1)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target.with_name(target.name + f".bak_{stamp}")
    shutil.copy2(target, backup)

    target.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")

    # Verify после записи (Инцидент 38 / Правило 64-66).
    chk = target.read_text(encoding="utf-8")
    if NEW not in chk or OLD in chk:
        shutil.copy2(backup, target)  # откат
        print("[FAIL] Verify не прошёл — откатил из backup. Ничего не изменено.")
        sys.exit(1)

    print(f"[OK] Заменено в {target}")
    print(f"     backup -> {backup.name}")
    print("     Не забудь: перегенерировать выписку у затронутых клиентов "
          "(override в БД хранит старый текст) + при наличии ES — перевести заново.")


if __name__ == "__main__":
    main()
