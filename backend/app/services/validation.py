import re
from typing import Any

from email_validator import EmailNotValidError, validate_email

CURRENT_MONTH_COLUMNS = [
    "name",
    "bank",
    "iban_no",
    "branch_code",
    "invoice",
    "invoice_no",
    "total_amount",
]
HISTORY_NAME_COLUMN = "name"
# Legacy long-format history (still supported if detected).
HISTORY_LONG_COLUMNS = ["person_name", "task_name", "invoice_month"]
TASKS_COLUMNS = ["main_task", "sub_task"]


class ValidationError(Exception):
    pass


def normalize_columns(df) -> None:
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]


def require_columns(df, required: list[str], sheet_name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValidationError(
            f"{sheet_name} is missing required column(s): {', '.join(missing)}"
        )


def validate_email_address(email: str) -> str:
    if not email or not str(email).strip():
        raise ValidationError("Email is required.")
    try:
        result = validate_email(str(email).strip(), check_deliverability=False)
        return result.normalized
    except EmailNotValidError as e:
        raise ValidationError(f"Invalid email address: {email}") from e


def validate_structure_number(value: Any, context: str = "") -> int:
    from backend.app.services.word_templates import (
        INVOICE_WORD_MAP,
        MAX_INVOICE_TEMPLATE,
    )

    try:
        num = int(float(value))
    except (TypeError, ValueError) as e:
        raise ValidationError(
            f"{context}Invoice structure number must be an integer between "
            f"1 and {MAX_INVOICE_TEMPLATE}."
        ) from e
    if num not in INVOICE_WORD_MAP:
        raise ValidationError(
            f"{context}Invoice structure number must be between "
            f"1 and {MAX_INVOICE_TEMPLATE} (got {num})."
        )
    return num


def validate_total_amount(value: Any, context: str = "") -> int:
    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError) as e:
        raise ValidationError(
            f"{context}Total amount must be a valid positive number."
        ) from e
    if amount <= 0:
        raise ValidationError(f"{context}Total amount must be greater than zero.")
    return amount


def validate_non_empty_text(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValidationError(f"{field_name} is required.")
    return text


def sanitize_filename_part(value: str) -> str:
    text = re.sub(r"[^\w\s-]", "", str(value).strip())
    return re.sub(r"\s+", "_", text) or "unknown"
