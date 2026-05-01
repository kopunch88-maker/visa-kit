"""
Pack 15 — translation services.

Public API:
    from app.services.translation import translate_docx, run_translate_package, ALL_KINDS, KIND_CONFIG
"""

from .docx_translator import translate_docx
from .orchestrator import (
    run_translate_package,
    translate_package,
    ALL_KINDS,
    KIND_CONFIG,
)

__all__ = [
    "translate_docx",
    "run_translate_package",
    "translate_package",
    "ALL_KINDS",
    "KIND_CONFIG",
]
