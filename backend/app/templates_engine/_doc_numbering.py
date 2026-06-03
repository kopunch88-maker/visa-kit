# -*- coding: utf-8 -*-
"""
Pack 50.40 — единый детерминированный генератор «реестровых» номеров документов.

Номер растёт примерно на `step` за каждый РАБОЧИЙ день относительно фиксированной
эпохи и СТРОГО монотонен по дате (позже дата -> выше номер), но «не ровно» —
с детерминированным джиттером, чтобы соседние документы не шли подряд.

Используется:
  - КНД 1122035 (справка НПД)        -> step=500, base=106_800_000 (9-значный номер)
  - апостиль 77-NNNNN/26 (НПД и СФР)  -> step=350, base=3000        (5-значный NNNNN)

Свойства:
  * монотонность: ref_date2 позже ref_date1 хотя бы на 1 раб. день =>
    номер(ref_date2) > номер(ref_date1). Джиттер < step/2 < step, поэтому
    прирост между соседними раб. днями всегда в диапазоне (step/2 .. 3*step/2).
  * детерминизм: один и тот же (ref_date, seed) -> один и тот же номер
    (стабильно при перегенерации документа).
  * «не ровно»: джиттер из SHA1(seed); реальный дневной шаг ~step/2..3*step/2.
"""
from __future__ import annotations

import hashlib
from datetime import date

# Эпоха отсчёта. Совпадает с годом в суффиксе апостиля (/26): за 2026 год
# ~250 раб.дней * 350 + base ~= 90 500 < 99 999, NNNNN остаётся 5-значным.
NUM_EPOCH = date(2026, 1, 1)


def workdays_since(ref: date, epoch: date = NUM_EPOCH) -> int:
    """Рабочих дней (Пн-Пт) в интервале (epoch, ref]. 0, если ref <= epoch."""
    if ref <= epoch:
        return 0
    full, rem = divmod((ref - epoch).days, 7)
    count = full * 5
    base_wd = epoch.weekday()  # 0=Пн ... 6=Вс
    for i in range(1, rem + 1):
        if (base_wd + i) % 7 < 5:
            count += 1
    return count


def compute_doc_number(ref_date: date, *, step: int, base: int, seed: str) -> int:
    """Детерминированный, монотонный по дате номер, растущий ~step за раб. день.

    ref_date — дата, которая печатается на документе (именно по ней монотонность).
    step      — целевой прирост за рабочий день (КНД 500 / апостиль 350).
    base      — стартовое значение на эпоху.
    seed      — строка для джиттера, обычно f"{prefix}:{applicant_id}:{ref_date.isoformat()}".
    """
    wd = workdays_since(ref_date)
    span = max(1, step // 2)  # джиттер строго < step/2 -> монотонность сохраняется
    jitter = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % span
    return base + wd * step + jitter
