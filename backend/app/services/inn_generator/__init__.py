"""
Pack 17 — Сервис автогенерации ИНН самозанятого.

Модули:
- rmsp_client: HTTP клиент к rmsp-pp.nalog.ru для получения списка самозанятых
- npd_status: проверка статуса НПД через npd.nalog.ru/api
- kladr_address_gen: генератор реалистичных адресов (10 регионов)
- region_picker: выбор региона по логике (Pack 17.2)
- pipeline: orchestrator (Pack 17.2)
"""

from .rmsp_client import RmspClient, RmspCandidate, RmspError
from .npd_status import NpdStatusChecker, NpdStatusResult, NpdStatusError
from .kladr_address_gen import generate_address, KNOWN_REGIONS, GeneratedAddress, is_known_region
from .region_picker import pick_region, RegionPickResult
from .pipeline import suggest_inn_for_applicant, InnSuggestion, InnPipelineError

__all__ = [
    # rmsp_client
    "RmspClient", "RmspCandidate", "RmspError",
    # npd_status
    "NpdStatusChecker", "NpdStatusResult", "NpdStatusError",
    # kladr_address_gen
    "generate_address", "KNOWN_REGIONS", "GeneratedAddress", "is_known_region",
    # region_picker
    "pick_region", "RegionPickResult",
    # pipeline
    "suggest_inn_for_applicant", "InnSuggestion", "InnPipelineError",
]
