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
# Pack 18.3: справка о постановке на учёт самозанятого (КНД 1122035)
from .context_npd_certificate import build_npd_certificate_context
from .npd_certificate_renderer import render_npd_certificate

__all__ = [
    "build_context",
    "render_contract",
    "render_act",
    "render_invoice",
    "render_employer_letter",
    "render_cv",
    "render_bank_statement",
    # Pack 18.3
    "build_npd_certificate_context",
    "render_npd_certificate",
]