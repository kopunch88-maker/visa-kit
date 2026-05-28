"""Templates engine package."""

from .context import build_context
from .docx_renderer import (
    render_contract,
    render_act,
    render_invoice,
    render_employer_letter,
    render_employer_letter_naim,  # Pack 50.11-B
    render_cv,
    render_bank_statement,
    render_tech_opinion,  # Pack 40.0-G
    render_business_trip_order,  # Pack 50.7-C
    render_employment_contract,  # Pack 50.1-C
    render_ndfl_2,  # Pack 50.8-B
    render_stdr,  # Pack 50.9-B
    render_soo,  # Pack 50.12-B
    render_payslip,  # Pack 50.10-B
)
# Pack 18.3: справка о постановке на учёт самозанятого (КНД 1122035)
from .context_npd_certificate import build_npd_certificate_context
from .npd_certificate_renderer import render_npd_certificate
# Pack 18.3.3: тот же контекст, второй шаблон в формате ЛКН (электронная подпись ФНС)
from .npd_certificate_lkn_renderer import render_npd_certificate_lkn
# Pack 18.9: апостиль к справке НПД
from .context_apostille import build_apostille_context
from .apostille_renderer import render_apostille

__all__ = [
    "build_context",
    "render_contract",
    "render_act",
    "render_invoice",
    "render_employer_letter",
    "render_employer_letter_naim",  # Pack 50.11-B
    "render_cv",
    "render_bank_statement",
    "render_tech_opinion",  # Pack 40.0-G
    "render_business_trip_order",  # Pack 50.7-C
    "render_employment_contract",  # Pack 50.1-C
    "render_ndfl_2",  # Pack 50.8-B
    "render_stdr",  # Pack 50.9-B
    "render_soo",  # Pack 50.12-B
    "render_payslip",  # Pack 50.10-B
    # Pack 18.3
    "build_npd_certificate_context",
    "render_npd_certificate",
    # Pack 18.3.3
    "render_npd_certificate_lkn",
    # Pack 18.9
    "build_apostille_context",
    "render_apostille",
]