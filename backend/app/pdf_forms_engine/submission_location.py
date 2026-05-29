"""
Pack 50.38-A2 — определение города и провинции ПОДАЧИ.

Город подачи (Barcelona / Madrid) хранится в application.submission_city,
отдельно от адреса проживания (SpainAddress.city). Провинция подачи —
application.submission_province; если не задана, подставляется автоматически
для известных городов.

Используется во всех PDF-формах для МЕСТА ПОДПИСИ и Brigada de Extranjería.
Адрес проживания заявителя (Localidad/Provincia в блоке адреса) НЕ затрагивается.
"""
from typing import Optional, Tuple


# Известные города подачи → провинция (для автоподстановки)
_CITY_TO_PROVINCE = {
    "barcelona": "Barcelona",
    "madrid": "Madrid",
}


def submission_city_province(app, addr) -> Tuple[str, str]:
    """Возвращает (город_подачи, провинция_подачи).

    Логика:
      1. Если app.submission_city задан → город = он; провинция =
         app.submission_province или авто по городу (Barcelona/Madrid).
      2. Иначе fallback на адрес проживания (addr.city / addr.province) —
         чтобы старые заявки без submission_city не ломались.
    """
    city = (getattr(app, "submission_city", None) or "").strip()
    if city:
        prov = (getattr(app, "submission_province", None) or "").strip()
        if not prov:
            prov = _CITY_TO_PROVINCE.get(city.lower(), "")
        return city, prov

    # Fallback — адрес проживания
    if addr is not None:
        return (getattr(addr, "city", None) or ""), (getattr(addr, "province", None) or "")
    return "", ""


def submission_city(app, addr) -> str:
    """Только город подачи (с fallback). Удобный шорткат."""
    return submission_city_province(app, addr)[0]
