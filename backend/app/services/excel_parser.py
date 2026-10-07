from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pandas as pd

from backend.app.models import InvoiceTask, WordInvoiceData
from backend.app.services.amount_distribution import distribute_amounts
from backend.app.services.history_tracker import (
    build_last_three_months_history_excel,
    build_updated_history_excel,
    last_three_months_history_filename,
    updated_history_filename,
)
from backend.app.services.invoice_no_utils import (
    increment_invoice_no,
    validate_invoice_no_text,
)
from backend.app.services.category_tasks import load_category_tasks_df, normalize_category
from backend.app.services.task_assignment import (
    _normalize_task,
    assign_tasks_for_person,
    build_person_history,
    load_available_tasks,
)
from backend.app.services.validation import (
    CURRENT_MONTH_COLUMNS,
    HISTORY_NAME_COLUMN,
    HISTORY_LONG_COLUMNS,
    TASKS_COLUMNS,
    ValidationError,
    normalize_columns,
    require_columns,
    validate_non_empty_text,
    validate_total_amount,
)
from backend.app.services.word_templates import validate_invoice_number

DEFAULT_EMAIL = "invoice@local.invalid"


@dataclass
class BulkGenerateResult:
    invoices: list[WordInvoiceData]
    updated_history_bytes: bytes
    updated_history_filename: str
    last_three_months_history_bytes: bytes
    last_three_months_history_filename: str


def read_excel(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(BytesIO(content), engine="openpyxl")
    except Exception as e:
        raise ValidationError(f"Could not read Excel file: {e}") from e


def _alias_current_month_columns(df: pd.DataFrame) -> None:
    aliases = {
        "iban_no": ["iban_no.", "iban_no", "iban", "iban_number"],
        "branch_code": ["branch_code", "branch"],
        "invoice": ["invoice", "invoice_structure_number"],
        "invoice_no": ["invoice_no.", "invoice_no", "invoice_number"],
        "total_amount": ["total_amount", "total", "amount"],
        "name": ["name", "person_name"],
    }
    for canonical, names in aliases.items():
        if canonical in df.columns:
            continue
        for alias in names:
            if alias in df.columns:
                df.rename(columns={alias: canonical}, inplace=True)
                break


def _alias_history_columns(df: pd.DataFrame) -> None:
    if "name" not in df.columns and "person_name" in df.columns:
        return
    if "name" not in df.columns:
        for alias in ("name", "person"):
            if alias in df.columns:
                break
        else:
            for col in df.columns:
                if col.strip().lower() in ("name", "person_name"):
                    df.rename(columns={col: "name"}, inplace=True)
                    break


def _prepare_history_sheet(df: pd.DataFrame) -> pd.DataFrame:
    normalize_columns(df)
    _alias_history_columns(df)

    if _is_long_history_format(df):
        require_columns(df, HISTORY_LONG_COLUMNS, "Last 3 months invoice history sheet")
        return df

    if HISTORY_NAME_COLUMN not in df.columns:
        raise ValidationError(
            "Last 3 months invoice history sheet must have a Name column."
        )
    month_cols = [c for c in df.columns if c != HISTORY_NAME_COLUMN]
    if not month_cols:
        raise ValidationError(
            "Last 3 months invoice history sheet must include month columns "
            "(e.g. May, April, March) with items sent to each person."
        )
    return df


def _is_long_history_format(df: pd.DataFrame) -> bool:
    from backend.app.services.task_assignment import _is_long_history_format as check

    return check(df)


def _prepare_tasks_sheet(df: pd.DataFrame) -> pd.DataFrame:
    if _is_long_tasks_format(df):
        normalize_columns(df)
        require_columns(df, TASKS_COLUMNS, "Task/items sheet")
        return df

    if df.empty or len(df.columns) < 1:
        raise ValidationError(
            "Task/items sheet must have main tasks in the first row "
            "with subtasks listed below each column."
        )
    load_available_tasks(df)
    return df


def _is_long_tasks_format(df: pd.DataFrame) -> bool:
    from backend.app.services.task_assignment import _is_long_tasks_format as check

    return check(df)


def _empty_history_frame() -> pd.DataFrame:
    """Placeholder history when generation uses current-month sheet only."""
    return pd.DataFrame(columns=["Name"])


def parse_and_prepare_sheets(
    current_content: bytes,
    category: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    current_df = read_excel(current_content)
    history_raw = _empty_history_frame()
    history_df = history_raw.copy()
    tasks_df = load_category_tasks_df(category)

    normalize_columns(current_df)
    _alias_current_month_columns(current_df)
    require_columns(current_df, CURRENT_MONTH_COLUMNS, "Current month invoice sheet")
    if current_df.empty:
        raise ValidationError("Current month invoice sheet has no data rows.")

    return current_df, history_df, tasks_df, history_raw


def _excel_text_value(value) -> str:
    """Copy cell value from Excel as text (numbers, strings, or mixed)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _row_total_amount(row, context: str) -> int:
    if "total_amount" not in row.index or pd.isna(row.get("total_amount")):
        raise ValidationError(f"{context}Amount is required.")
    return validate_total_amount(row["total_amount"], f"{context}Amount")


def validate_current_row(row, context: str) -> dict:
    name = validate_non_empty_text(row.get("name"), f"{context}Name")
    bank = validate_non_empty_text(row.get("bank"), f"{context}Bank")
    iban = validate_non_empty_text(row.get("iban_no"), f"{context}IBAN NO.")
    invoice_number = validate_invoice_number(row.get("invoice"), context)
    branch_code = _excel_text_value(row.get("branch_code"))
    sheet_invoice_no = validate_invoice_no_text(
        _excel_text_value(row.get("invoice_no")),
        f"{context}Invoice No.",
    )
    document_invoice_no = increment_invoice_no(sheet_invoice_no)
    return {
        "person_name": name,
        "company_name": name,
        "email": DEFAULT_EMAIL,
        "structure_number": invoice_number,
        "invoice_number": invoice_number,
        "total_amount": _row_total_amount(row, context),
        "bank": bank,
        "iban": iban,
        "branch_code": branch_code,
        "sheet_invoice_no": sheet_invoice_no,
        "document_invoice_no": document_invoice_no,
    }


def generate_bulk_word_invoices(
    current_content: bytes,
    category: str,
) -> BulkGenerateResult:
    normalize_category(category)
    current_df, history_df, tasks_df, history_raw = parse_and_prepare_sheets(
        current_content, category
    )
    # No last-3-months upload: history exclusion is empty; batch uniqueness still applies.
    person_history = build_person_history(history_df)
    available_tasks = load_available_tasks(tasks_df)

    batch_used_subtasks: set[str] = set()
    invoices: list[WordInvoiceData] = []
    today = date.today()

    for idx, row in current_df.iterrows():
        row_num = int(idx) + 2 if isinstance(idx, int) else idx
        ctx = f"Row {row_num}: "
        validated = validate_current_row(row, ctx)

        assigned = assign_tasks_for_person(
            validated["person_name"],
            available_tasks,
            person_history,
            batch_used_subtasks,
        )
        for _, sub_task in assigned:
            batch_used_subtasks.add(_normalize_task(sub_task))

        amounts = distribute_amounts(validated["total_amount"])
        invoice_tasks = [
            InvoiceTask(main_task=mt, sub_task=st, amount=amt)
            for (mt, st), amt in zip(assigned, amounts)
        ]

        invoices.append(
            WordInvoiceData(
                person_name=validated["person_name"],
                company_name=validated["company_name"],
                email=validated["email"],
                total_amount=validated["total_amount"],
                invoice_number=validated["invoice_number"],
                tasks=invoice_tasks,
                bank=validated["bank"],
                iban=validated["iban"],
                branch_code=validated["branch_code"],
                sheet_invoice_no=validated["sheet_invoice_no"],
                document_invoice_no=validated["document_invoice_no"],
            )
        )

    return BulkGenerateResult(
        invoices=invoices,
        updated_history_bytes=build_updated_history_excel(history_raw, invoices, today),
        updated_history_filename=updated_history_filename(today),
        last_three_months_history_bytes=build_last_three_months_history_excel(
            history_raw, invoices, today
        ),
        last_three_months_history_filename=last_three_months_history_filename(today),
    )


def generate_bulk_invoices(
    current_content: bytes,
    category: str,
) -> BulkGenerateResult:
    """Bulk generate invoices using category task sheet + current month sheet only."""
    return generate_bulk_word_invoices(current_content, category)
