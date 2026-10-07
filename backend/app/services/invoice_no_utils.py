import re
from datetime import date

from backend.app.services.validation import ValidationError

INVOICE_NO_IN_TEXT = re.compile(r"(?i)(Invoice No\.?\s*:)\s*[^\n\r]*")


def validate_invoice_no_text(value, field_name: str = "Invoice No.") -> str:
    if value is None:
        text = ""
    else:
        text = str(value).strip()
    if not text or text.lower() == "nan":
        raise ValidationError(f"{field_name} is required.")
    if not re.search(r"\d", text):
        raise ValidationError(
            f"{field_name} must contain a number to increment (e.g. HH-007)."
        )
    return text


def increment_invoice_no(value: str) -> str:
    """
    Increment the last numeric segment, keeping zero padding.
    HH-007 -> HH-008, AA-001 -> AA-002
    """
    text = validate_invoice_no_text(value)
    matches = list(re.finditer(r"\d+", text))
    if not matches:
        raise ValidationError(
            f"Invoice No. must contain a number to increment (got {text!r})."
        )
    match = matches[-1]
    width = len(match.group())
    next_num = int(match.group()) + 1
    replacement = str(next_num).zfill(width)
    return text[: match.start()] + replacement + text[match.end() :]


def current_month_invoice_no_column_name(invoice_date: date | None = None) -> str:
    month = (invoice_date or date.today()).strftime("%b")
    return f"{month} Invoice No."


def is_invoice_no_tracking_column(column: str) -> bool:
    return str(column).strip().lower().endswith("invoice no.")
