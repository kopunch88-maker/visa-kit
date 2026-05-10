# -*- coding: utf-8 -*-
"""
SNRIP Recon v2 — разведка структуры дампа ФНС напрямую из ZIP.

Отвечает на три вопроса:
  1) Есть ли в дампе чистые физики-самозанятые (без ОГРНИП), или там одни ИП?
  2) Какие в записях есть атрибуты с датами? Конкретно — дата начала НПД-режима?
  3) Как выглядит реальная запись с ПризнСНР="5"?

ZIP не распаковывается на диск — читаем XML через zipfile в потоке.

Использование (PowerShell):
    cd D:\\VISA\\visa_kit
    $env:PYTHONIOENCODING = "utf-8"

    python snrip_recon.py data-20260425-structure-20241025.zip

    # Если нужно больше образцов или просканировать весь архив:
    python snrip_recon.py data-20260425-structure-20241025.zip --samples 10 --max-files 0

Stdlib-only, в БД не лезет, ничего не меняет.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


def _indent(elem: ET.Element, level: int = 0) -> None:
    pad = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = pad
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():  # type: ignore[possibly-undefined]
            child.tail = pad  # type: ignore[possibly-undefined]
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = pad


def _record_dump(elem: ET.Element) -> str:
    clone = ET.fromstring(ET.tostring(elem, encoding="unicode"))
    _indent(clone)
    return ET.tostring(clone, encoding="unicode")


def _collect_attrs_recursively(elem: ET.Element, prefix: str = "") -> dict[str, str]:
    """Возвращает {full_path/attr: value} для всех атрибутов всех вложенных тегов."""
    out: dict[str, str] = {}
    path = f"{prefix}/{elem.tag}" if prefix else elem.tag
    for k, v in elem.attrib.items():
        out[f"{path}@{k}"] = v
    for child in elem:
        out.update(_collect_attrs_recursively(child, path))
    return out


def _has_ognrip(elem: ET.Element) -> bool:
    """Проверяет есть ли где-то в записи ОГРНИП — признак того что это ИП, а не физик."""
    for descendant in elem.iter():
        if "ОГРНИП" in descendant.attrib:
            return True
        if descendant.tag.endswith("ОГРНИП"):
            return True
    return False


def _has_npd_flag(elem: ET.Element) -> bool:
    """Проверяет есть ли у записи флаг НПД (СведСНР ПризнСНР="5")."""
    for descendant in elem.iter():
        if descendant.tag.endswith("СведСНР") and descendant.attrib.get("ПризнСНР") == "5":
            return True
    return False


def _date_attrs(record_attrs: dict[str, str]) -> dict[str, str]:
    """Фильтрует только атрибуты, у которых имя содержит 'Дата'."""
    return {k: v for k, v in record_attrs.items() if "Дата" in k}


def main() -> int:
    parser = argparse.ArgumentParser(description="SNRIP ZIP recon")
    parser.add_argument("zip_path", help="Путь к ZIP-архиву SNRIP")
    parser.add_argument(
        "--samples", type=int, default=5,
        help="Сколько примеров записей с ПризнСНР=5 показать целиком (default 5)",
    )
    parser.add_argument(
        "--max-files", type=int, default=20,
        help="Максимум XML-файлов внутри ZIP сканировать (default 20). 0 = все.",
    )
    args = parser.parse_args()

    zip_path = Path(args.zip_path)
    if not zip_path.is_file():
        print(f"❌ ZIP не найден: {zip_path}", file=sys.stderr)
        return 1

    print(f"📦 Открываю {zip_path}\n")

    with zipfile.ZipFile(zip_path, "r") as zf:
        all_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not all_names:
            print("❌ Внутри ZIP нет .xml файлов", file=sys.stderr)
            return 1

        if args.max_files > 0:
            xml_names = all_names[: args.max_files]
        else:
            xml_names = all_names

        print(f"🔍 В архиве {len(all_names):,} XML-файлов, сканирую {len(xml_names):,}\n")

        total_records = 0
        npd_records = 0
        npd_with_ognrip = 0
        npd_without_ognrip = 0

        attr_path_counter: Counter[str] = Counter()
        date_examples: dict[str, set[str]] = {}

        samples_npd_no_ip: list[ET.Element] = []
        samples_npd_with_ip: list[ET.Element] = []

        for idx, xml_name in enumerate(xml_names, 1):
            if idx % 500 == 0:
                print(f"  ...прогресс: {idx:,}/{len(xml_names):,} файлов")
            try:
                with zf.open(xml_name) as f:
                    tree = ET.parse(f)
            except (ET.ParseError, zipfile.BadZipFile) as e:
                print(f"  ⚠️  parse error в {xml_name}: {e}")
                continue

            root = tree.getroot()
            records = list(root)
            for rec in records:
                total_records += 1

                if not _has_npd_flag(rec):
                    continue
                npd_records += 1

                attrs = _collect_attrs_recursively(rec)
                for path in attrs.keys():
                    attr_path_counter[path] += 1
                for k, v in _date_attrs(attrs).items():
                    date_examples.setdefault(k, set())
                    if len(date_examples[k]) < 3:
                        date_examples[k].add(v)

                if _has_ognrip(rec):
                    npd_with_ognrip += 1
                    if len(samples_npd_with_ip) < args.samples:
                        samples_npd_with_ip.append(rec)
                else:
                    npd_without_ognrip += 1
                    if len(samples_npd_no_ip) < args.samples:
                        samples_npd_no_ip.append(rec)

    print("\n" + "=" * 70)
    print("📊 ИТОГИ")
    print("=" * 70)
    print(f"Всего записей просканировано:      {total_records:,}")
    print(f"Из них с ПризнСНР=5 (НПД):         {npd_records:,}")
    print(f"  ├─ ИП на НПД (есть ОГРНИП):      {npd_with_ognrip:,}  ← СВЕТЯТСЯ при гуглении")
    print(f"  └─ «чистые» физики (нет ОГРНИП): {npd_without_ognrip:,}  ← наша цель")
    print()

    if npd_records == 0:
        print("⚠️  В выборке нет записей с НПД-флагом. Увеличь --max-files или проверь архив.")
        return 0

    print("=" * 70)
    print("❓ Q1: Есть ли в дампе чистые физики-самозанятые?")
    print("=" * 70)
    if npd_without_ognrip == 0:
        print("❌ НЕТ. Все НПД-записи в выборке — ИП.")
        print("   → Все 546k ИНН в self_employed_registry потенциально светятся в реестре ИП.")
        print("   → Это серьёзная проблема для легенды клиента.")
    elif npd_without_ognrip < npd_records * 0.05:
        pct = 100 * npd_without_ognrip / npd_records
        print(f"⚠️  Очень мало: {npd_without_ognrip}/{npd_records} ({pct:.1f}%)")
        print("   → В этой выборке почти все — ИП. Стоит просканировать весь архив (--max-files 0).")
    else:
        pct = 100 * npd_without_ognrip / npd_records
        print(f"✅ ДА, {npd_without_ognrip}/{npd_records} ({pct:.1f}%) — без ОГРНИП.")
        print("   → Можно фильтровать по отсутствию ОГРНИП при импорте.")
    print()

    print("=" * 70)
    print("❓ Q2: Какие в записях есть атрибуты с датами?")
    print("=" * 70)
    if not date_examples:
        print("❌ Атрибутов с 'Дата' в имени не найдено вообще.")
    else:
        sorted_paths = sorted(date_examples.keys(), key=lambda k: -attr_path_counter[k])
        for path in sorted_paths:
            count = attr_path_counter[path]
            examples = ", ".join(sorted(date_examples[path]))
            print(f"  {path}")
            print(f"     встречается: {count:,} раз")
            print(f"     примеры:     {examples}")
            print()
    print()

    print("=" * 70)
    print("❓ Q3: Как выглядит запись с ПризнСНР=5? (образцы)")
    print("=" * 70)

    if samples_npd_no_ip:
        print(f"\n--- Образцы «чистых физиков» (НПД без ОГРНИП), показано {len(samples_npd_no_ip)} ---\n")
        for i, rec in enumerate(samples_npd_no_ip, 1):
            print(f"### Образец #{i} (физик)")
            print(_record_dump(rec))
            print()

    if samples_npd_with_ip:
        print(f"\n--- Образцы ИП на НПД (с ОГРНИП), показано {len(samples_npd_with_ip)} ---\n")
        for i, rec in enumerate(samples_npd_with_ip, 1):
            print(f"### Образец #{i} (ИП на НПД)")
            print(_record_dump(rec))
            print()

    print("=" * 70)
    print("📋 Топ-20 атрибутов в НПД-записях (для понимания структуры)")
    print("=" * 70)
    for path, count in attr_path_counter.most_common(20):
        print(f"  {count:>8,}  {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
