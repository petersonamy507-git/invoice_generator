import shutil
from datetime import date
from io import BytesIO
from pathlib import Path

from backend.app.models import InvoiceData, WordInvoiceData
from backend.app.services.manual_invoice import create_manual_invoice
from backend.app.services.validation import (
    ValidationError,
    sanitize_filename_part,
)
from backend.app.services.word_doc_converter import open_template_document
from backend.app.services.word_field_updater import update_invoice_fields
from backend.app.services.word_templates import (
    INVOICE_WORD_MAP,
    ensure_template_exists,
    validate_invoice_number,
)


def word_invoice_from_invoice_data(invoice: InvoiceData) -> WordInvoiceData:
    if invoice.structure_number not in INVOICE_WORD_MAP:
        raise ValidationError(
            f"Word template {invoice.structure_number} is not available."
        )
    return WordInvoiceData(
        person_name=invoice.person_name,
        company_name=invoice.company_name,
        email=invoice.email,
        total_amount=invoice.total_amount,
        invoice_number=invoice.structure_number,
        tasks=list(invoice.tasks),
    )


def parse_manual_word_invoice(
    person_name: str,
    company_name: str,
    email: str,
    total_amount: float,
    invoice_number: int,
) -> WordInvoiceData:
    validate_invoice_number(invoice_number)
    invoice = create_manual_invoice(
        person_name=person_name,
        company_name=company_name,
        email=email,
        total_amount=total_amount,
        structure_number=invoice_number,
    )
    return word_invoice_from_invoice_data(invoice)


def output_filename(data: WordInvoiceData) -> str:
    person = sanitize_filename_part(data.person_name)
    company = sanitize_filename_part(data.company_name)
    day = date.today().strftime("%Y-%m-%d")
    base = INVOICE_WORD_MAP[data.invoice_number]
    return f"invoice_{person}_{company}_{base}_{day}.docx"


def generate_word_invoice(data: WordInvoiceData) -> tuple[bytes, str]:
    """
    Fill the original Word invoice template (Data/word/) so PDF export
    matches your Word→PDF format (shapes, header bars, fonts, tables).

    On Windows, Microsoft Word COM is used so DrawingML headers (e.g. Beecodify
    blue/gray bars) are preserved. python-docx save strips those shapes.
    """
    if not data.tasks or len(data.tasks) < 3:
        raise ValidationError(
            "Invoice must have 3 assigned tasks before generating."
        )
    ensure_template_exists(data.invoice_number)
    filename = output_filename(data)

    # Word COM on Windows preserves DrawingML (Beecodify header bars, etc.).
    # python-docx save strips those shapes — do not use it as a silent fallback.
    import sys

    if sys.platform.startswith("win"):
        from backend.app.services.word_com_fill import generate_docx_bytes_via_word_com

        return generate_docx_bytes_via_word_com(data), filename

    source = ensure_template_exists(data.invoice_number)
    doc, temp_path = open_template_document(source)
    try:
        update_invoice_fields(doc, data)
        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue(), filename
    finally:
        if temp_path and temp_path.exists():
            shutil.rmtree(temp_path.parent, ignore_errors=True)
