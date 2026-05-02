"""
Pack 17 — Сервис автогенерации ИНН самозанятого.

Модули:
- rmsp_client: HTTP клиент к rmsp-pp.nalog.ru для получения списка самозанятых
- npd_status: проверка статуса НПД через npd.nalog.ru/api
- kladr_address_gen: генератор реалистичных адресов из захардкоженной базы улиц
- region_picker: (Pack 17.2) выбор региона по логике home/company/edu/диаспоры
- pipeline: (Pack 17.2) orchestrator всех шагов

Использование (после Pack 17.2):
    from app.services.inn_generator.pipeline import suggest_inn_for_applicant
    candidate = await suggest_inn_for_applicant(applicant)
    # candidate = {inn, name, registration_date, address, kladr_code, region_name}
"""

from .rmsp_client import RmspClient, RmspCandidate, RmspError
from .npd_status import NpdStatusChecker, NpdStatusResult, NpdStatusError
from .kladr_address_gen import generate_address, KNOWN_REGIONS

__all__ = [
    "RmspClient",
    "RmspCandidate",
    "RmspError",
    "NpdStatusChecker",
    "NpdStatusResult",
    "NpdStatusError",
    "generate_address",
    "KNOWN_REGIONS",
]
