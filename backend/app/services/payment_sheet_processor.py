from io import BytesIO

from backend.app.services.excel_parser import (
    _alias_current_month_columns,
    generate_bulk_word_invoices,
    read_excel,
)
from backend.app.services.validation import (
    CURRENT_MONTH_COLUMNS,
    ValidationError,
    normalize_columns,
    require_columns,
)
from backend.app.services.word_invoice_generator import generate_word_invoice


def parse_payment_sheet(content: bytes):
    df = read_excel(content)
    normalize_columns(df)
    _alias_current_month_columns(df)
    require_columns(df, CURRENT_MONTH_COLUMNS, "Payment sheet")
    if df.empty:
        raise ValidationError("Payment sheet has no data rows.")
    return df


def build_word_invoices_from_payment_sheet(content: bytes, category: str = "account"):
    """Single-sheet upload: current month only, using selected/default category items."""
    return generate_bulk_word_invoices(content, category)


def build_payment_sheet_zip(content: bytes) -> tuple[bytes, list[str]]:
    from backend.app.services.zip_export import build_zip

    result = build_word_invoices_from_payment_sheet(content)
    names = [generate_word_invoice(inv)[1] for inv in result.invoices]
    zip_bytes = build_zip(
        result.invoices,
        updated_history_bytes=result.updated_history_bytes,
        updated_history_filename=result.updated_history_filename,
        last_three_months_history_bytes=result.last_three_months_history_bytes,
        last_three_months_history_filename=result.last_three_months_history_filename,
    )
    return zip_bytes, names
