from pathlib import Path

from backend.app.services.validation import ValidationError

HTML_DIR = Path(__file__).resolve().parents[3] / "all_templates"

INVOICE_HTML_MAP = {
    1: "Invoice1-MAXIS.html",
    2: "Invoice02-ForestTechInc1.html",
    3: "Invoice03-RadnorInnovationsInc.html",
    4: "Invoice04-APPFOUNDERSINC.html",
    5: "Invoice05-DynamoCreativesInc.html",
}


def html_template_path(invoice_number: int) -> Path:
    filename = INVOICE_HTML_MAP.get(invoice_number)
    if not filename:
        raise ValidationError(f"No HTML template mapped for invoice {invoice_number}.")
    return HTML_DIR / filename


def pdf_template_path(invoice_number: int) -> Path:
    """Companion PDF used for generation (same stem as the HTML file)."""
    return html_template_path(invoice_number).with_suffix(".pdf")


def html_template_filename(invoice_number: int) -> str:
    return html_template_path(invoice_number).name


def ensure_html_template_exists(invoice_number: int) -> Path:
    path = html_template_path(invoice_number)
    if not path.is_file():
        raise ValidationError(
            f"HTML template not found for Invoice {invoice_number} "
            f"(expected {path.name} in {HTML_DIR})."
        )
    return path


def ensure_pdf_template_exists(invoice_number: int) -> Path:
    ensure_html_template_exists(invoice_number)
    path = pdf_template_path(invoice_number)
    if not path.is_file():
        raise ValidationError(
            f"PDF template not found for Invoice {invoice_number} "
            f"(expected {path.name} in {HTML_DIR}). "
            "Run scripts/pdf_to_html_templates.py after exporting Word?PDF."
        )
    return path
