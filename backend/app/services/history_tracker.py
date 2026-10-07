import re
from datetime import date, datetime
from io import BytesIO

import pandas as pd

from backend.app.models import WordInvoiceData
from backend.app.services.invoice_no_utils import (
    current_month_invoice_no_column_name,
    is_invoice_no_tracking_column,
)
from backend.app.services.task_assignment import _normalize_person


def current_month_column_name(invoice_date: date | None = None) -> str:
    d = invoice_date or date.today()
    return f"{d.strftime('%b')},{d.strftime('%y')}"


def _find_name_column(columns) -> str | None:
    for col in columns:
        if str(col).strip().lower() in ("name", "person_name"):
            return col
    return None


MONTH_YEAR_COLUMN = re.compile(
    r"^(?P<month>[A-Za-z]+)(?:,(?P<year>\d{2}|\d{4}))?$"
)


def _parse_month_column(column: str) -> date | None:
    col = str(column).strip()
    match = MONTH_YEAR_COLUMN.match(col)
    if not match:
        return None
    month_name = match.group("month")
    month_num = None
    for fmt in ("%b", "%B"):
        try:
            month_num = datetime.strptime(month_name, fmt).month
            break
        except ValueError:
            continue
    if month_num is None:
        try:
            month_num = datetime.strptime(month_name[:3], "%b").month
        except ValueError:
            return None
    year_str = match.group("year")
    if year_str:
        year = int(year_str)
        if year < 100:
            year += 2000
    else:
        year = date.today().year
    return date(year, month_num, 1)


def _sorted_month_columns(columns, name_col: str) -> list[str]:
    month_cols = [col for col in columns if col != name_col]
    dated = [(_parse_month_column(col) or date.min, col) for col in month_cols]
    dated.sort(key=lambda item: item[0])
    return [col for _, col in dated]


def trim_to_last_n_months(df: pd.DataFrame, name_col: str, n: int = 3) -> pd.DataFrame:
    """Keep Name, latest month item columns, and invoice-no tracking columns."""
    month_cols = _sorted_month_columns(df.columns, name_col)
    keep_months = month_cols[-n:] if len(month_cols) > n else month_cols
    invoice_no_cols = [
        col for col in df.columns if col != name_col and is_invoice_no_tracking_column(col)
    ]
    return df[[name_col, *keep_months, *invoice_no_cols]].copy()


def _dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return buffer.getvalue()


def _find_month_column(columns, month_name: str) -> str | None:
    target = month_name.strip().lower()
    for col in columns:
        if str(col).strip().lower() == target:
            return col
    return None


def _person_document_invoice_nos(
    invoices: list[WordInvoiceData],
) -> dict[str, tuple[str, str]]:
    """normalized person key -> (display name, incremented invoice no. for document)."""
    numbers: dict[str, tuple[str, str]] = {}
    for invoice in invoices:
        if not invoice.document_invoice_no:
            continue
        key = _normalize_person(invoice.person_name)
        numbers[key] = (invoice.person_name, invoice.document_invoice_no)
    return numbers


def _person_assigned_items(invoices: list[WordInvoiceData]) -> dict[str, tuple[str, str]]:
    """normalized person key -> (display name, comma-separated subtasks)."""
    items: dict[str, tuple[str, str]] = {}
    for invoice in invoices:
        key = _normalize_person(invoice.person_name)
        line = ", ".join(task.sub_task for task in invoice.tasks)
        if key in items:
            prev_name, prev_items = items[key]
            merged = f"{prev_items}, {line}" if prev_items else line
            items[key] = (prev_name, merged)
        else:
            items[key] = (invoice.person_name, line)
    return items


def _long_history_to_wide(history_raw: pd.DataFrame) -> pd.DataFrame:
    from backend.app.services.excel_parser import _is_long_history_format
    from backend.app.services.validation import normalize_columns

    df = history_raw.copy()
    normalize_columns(df)
    if not _is_long_history_format(df):
        return history_raw.copy()

    name_col = "person_name" if "person_name" in df.columns else "name"
    rows: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        person = str(row[name_col]).strip()
        if not person:
            continue
        month = str(row["invoice_month"]).strip()
        task = str(row["task_name"]).strip()
        if not month or not task:
            continue
        rows.setdefault(person, {})[month] = task

    if not rows:
        return pd.DataFrame(columns=["Name"])

    months = sorted({m for person in rows.values() for m in person})
    data = []
    for person, month_tasks in rows.items():
        record = {"Name": person}
        record.update(month_tasks)
        data.append(record)
    wide = pd.DataFrame(data)
    cols = ["Name"] + [m for m in months if m in wide.columns]
    return wide[cols] if cols else wide


def build_updated_history_dataframe(
    history_raw: pd.DataFrame,
    invoices: list[WordInvoiceData],
    invoice_date: date | None = None,
) -> pd.DataFrame:
    """
    Copy uploaded history, append a column for the current month,
    and fill each person's assigned invoice items.
    """
    month_name = current_month_column_name(invoice_date)
    invoice_no_col = current_month_invoice_no_column_name(invoice_date)
    df = _long_history_to_wide(history_raw)
    person_items = _person_assigned_items(invoices)
    person_invoice_nos = _person_document_invoice_nos(invoices)

    name_col = _find_name_column(df.columns)
    if name_col is None:
        name_col = "Name"
        if name_col not in df.columns:
            df.insert(0, name_col, "")

    month_col = _find_month_column(df.columns, month_name)
    if month_col is None:
        month_col = month_name
        df[month_col] = ""

    if invoice_no_col not in df.columns:
        df[invoice_no_col] = ""

    matched: set[str] = set()
    for idx, row in df.iterrows():
        person = row.get(name_col)
        if pd.isna(person) or not str(person).strip():
            continue
        key = _normalize_person(str(person))
        if key not in person_items:
            continue
        _, items = person_items[key]
        df.at[idx, month_col] = items
        if key in person_invoice_nos:
            _, invoice_no = person_invoice_nos[key]
            df.at[idx, invoice_no_col] = invoice_no
        matched.add(key)

    for key, (display_name, items) in person_items.items():
        if key in matched:
            continue
        new_row = {col: "" for col in df.columns}
        new_row[name_col] = display_name
        new_row[month_col] = items
        if key in person_invoice_nos:
            _, invoice_no = person_invoice_nos[key]
            new_row[invoice_no_col] = invoice_no
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    return df


def build_updated_history_excel(
    history_raw: pd.DataFrame,
    invoices: list[WordInvoiceData],
    invoice_date: date | None = None,
) -> bytes:
    df = build_updated_history_dataframe(history_raw, invoices, invoice_date)
    return _dataframe_to_excel_bytes(df)


def build_last_three_months_history_excel(
    history_raw: pd.DataFrame,
    invoices: list[WordInvoiceData],
    invoice_date: date | None = None,
) -> bytes:
    """Name + last 3 month columns only (upload this sheet next month)."""
    df = build_updated_history_dataframe(history_raw, invoices, invoice_date)
    name_col = _find_name_column(df.columns) or "Name"
    trimmed = trim_to_last_n_months(df, name_col, n=3)
    return _dataframe_to_excel_bytes(trimmed)


def updated_history_filename(invoice_date: date | None = None) -> str:
    d = invoice_date or date.today()
    return f"invoice_history_full_{d.strftime('%b')}_{d.year}.xlsx"


def last_three_months_history_filename(invoice_date: date | None = None) -> str:
    d = invoice_date or date.today()
    return f"invoice_history_last_3_months_{d.strftime('%b')}_{d.year}.xlsx"
