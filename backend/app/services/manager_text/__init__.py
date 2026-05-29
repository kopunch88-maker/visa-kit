from .parser import parse_manager_text, ManagerTextParseError

__all__ = [
    "parse_manager_text", "ManagerTextParseError",
    "resolve_company", "resolve_position",
    "resolve_representative", "resolve_spain_address",
]
from .reference_resolver import (
    resolve_company, resolve_position,
    resolve_representative, resolve_spain_address,
)
from .apply_parsed import apply_parsed_to_application, determine_application_type
