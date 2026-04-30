"""Templates engine package."""

from .context import build_context
from .docx_renderer import (
    render_contract,
    render_act,
    render_invoice,
    render_employer_letter,
    render_cv,
    render_bank_statement,
)

__all__ = [
    "build_context",
    "render_contract",
    "render_act",
    "render_invoice",
    "render_employer_letter",
    "render_cv",
    "render_bank_statement",
]
