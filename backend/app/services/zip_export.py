import zipfile
from io import BytesIO

from backend.app.models import InvoiceData, WordInvoiceData
from backend.app.services.pdf_generator import generate_invoice_pdf
from backend.app.services.validation import sanitize_filename_part
from backend.app.services.word_invoice_generator import (
    generate_word_invoice,
    word_invoice_from_invoice_data,
)
from backend.app.services.word_to_pdf import convert_docx_batch_to_pdf


def invoice_filename(invoice: InvoiceData) -> str:
    person = sanitize_filename_part(invoice.person_name)
    company = sanitize_filename_part(invoice.company_name)
    day = invoice.invoice_date.strftime("%Y-%m-%d")
    return f"invoice_{person}_{company}_{day}.pdf"


def build_pdf_zip(invoices: list[InvoiceData]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for invoice in invoices:
            pdf_bytes = generate_invoice_pdf(invoice)
            zf.writestr(invoice_filename(invoice), pdf_bytes)
    buffer.seek(0)
    return buffer.getvalue()


def build_word_zip(invoices: list[WordInvoiceData]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for invoice in invoices:
            docx_bytes, filename = generate_word_invoice(invoice)
            zf.writestr(filename, docx_bytes)
    buffer.seek(0)
    return buffer.getvalue()


def build_word_zip_from_invoice_data(invoices: list[InvoiceData]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for invoice in invoices:
            word_data = word_invoice_from_invoice_data(invoice)
            docx_bytes, filename = generate_word_invoice(word_data)
            zf.writestr(filename, docx_bytes)
    buffer.seek(0)
    return buffer.getvalue()


def build_zip(
    invoices: list[WordInvoiceData],
    updated_history_bytes: bytes | None = None,
    updated_history_filename: str | None = None,
    last_three_months_history_bytes: bytes | None = None,
    last_three_months_history_filename: str | None = None,
) -> bytes:
    """Fill Word templates then export PDF via Word — same look as your PDF samples."""
    docx_items = [generate_word_invoice(invoice) for invoice in invoices]
    pdf_items = convert_docx_batch_to_pdf(docx_items)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf_bytes, filename in pdf_items:
            zf.writestr(filename, pdf_bytes)
        if updated_history_bytes:
            zf.writestr(
                updated_history_filename or "invoice_history_full.xlsx",
                updated_history_bytes,
            )
        if last_three_months_history_bytes:
            zf.writestr(
                last_three_months_history_filename
                or "invoice_history_last_3_months.xlsx",
                last_three_months_history_bytes,
            )
    buffer.seek(0)
    return buffer.getvalue()
