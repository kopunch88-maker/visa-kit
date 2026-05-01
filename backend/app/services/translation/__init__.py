"""
Pack 15 — translation services.

Public API:
    from app.services.translation import translate_docx, run_translate_package, ALL_KINDS, KIND_CONFIG
    from app.services.translation import build_substitution_dict, SubstitutionDict
"""

from .docx_translator import translate_docx
from .name_substitution import build_substitution_dict, SubstitutionDict
from .orchestrator import (
    run_translate_package,
    translate_package,
    ALL_KINDS,
    KIND_CONFIG,
)

__all__ = [
    "translate_docx",
    "build_substitution_dict",
    "SubstitutionDict",
    "run_translate_package",
    "translate_package",
    "ALL_KINDS",
    "KIND_CONFIG",
]
