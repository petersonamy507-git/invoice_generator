import sys
from datetime import date
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend.app.models import InvoiceTask, WordInvoiceData
from backend.app.services.history_tracker import (
    build_last_three_months_history_excel,
    build_updated_history_excel,
    current_month_column_name,
    last_three_months_history_filename,
    updated_history_filename,
)
from backend.app.services.invoice_no_utils import current_month_invoice_no_column_name


def _invoice(person: str, subtasks: list[str]) -> WordInvoiceData:
    return WordInvoiceData(
        person_name=person,
        company_name=person,
        email="test@local",
        total_amount=1000,
        invoice_number=1,
        tasks=[
            InvoiceTask(main_task="Main", sub_task=st, amount=300)
            for st in subtasks
        ],
    )


def test_appends_current_month_column_to_wide_history():
    history = pd.DataFrame(
        [
            {"Name": "Alice", "May": "Logo Design", "April": "Social Post"},
            {"Name": "Bob", "May": "Banner", "April": ""},
        ]
    )
    invoices = [
        _invoice("Alice", ["Item A", "Item B", "Item C"]),
        _invoice("Bob", ["Item X", "Item Y", "Item Z"]),
    ]
    month = current_month_column_name(date(2026, 6, 1))
    assert month == "Jun,26"

    xlsx = build_updated_history_excel(history, invoices, date(2026, 6, 1))
    out = pd.read_excel(BytesIO(xlsx))

    invoice_no_col = current_month_invoice_no_column_name(date(2026, 6, 1))
    assert month in out.columns
    assert invoice_no_col in out.columns
    alice = out[out["Name"] == "Alice"].iloc[0]
    bob = out[out["Name"] == "Bob"].iloc[0]
    assert alice[month] == "Item A, Item B, Item C"
    assert bob[month] == "Item X, Item Y, Item Z"
    assert alice["May"] == "Logo Design"


def test_adds_new_person_not_in_history():
    history = pd.DataFrame([{"Name": "Alice", "May": "Logo Design"}])
    invoices = [_invoice("Charlie", ["New Task 1", "New Task 2", "New Task 3"])]
    month = current_month_column_name(date(2026, 6, 1))

    xlsx = build_updated_history_excel(history, invoices, date(2026, 6, 1))
    out = pd.read_excel(BytesIO(xlsx))

    charlie = out[out["Name"] == "Charlie"].iloc[0]
    assert charlie[month] == "New Task 1, New Task 2, New Task 3"


def test_trimmed_history_keeps_only_last_three_months():
    history = pd.DataFrame(
        [
            {
                "Name": "Alice",
                "January,26": "A1",
                "February,26": "A2",
                "March,26": "A3",
                "April,26": "A4",
                "May,26": "A5",
            }
        ]
    )
    invoices = [_invoice("Alice", ["June Item 1", "June Item 2", "June Item 3"])]
    xlsx = build_last_three_months_history_excel(history, invoices, date(2026, 6, 1))
    out = pd.read_excel(BytesIO(xlsx))

    assert list(out.columns) == [
        "Name",
        "April,26",
        "May,26",
        "Jun,26",
        "Jun Invoice No.",
    ]
    assert out.iloc[0]["Jun,26"] == "June Item 1, June Item 2, June Item 3"


def test_updated_history_filename():
    assert updated_history_filename(date(2026, 6, 1)) == "invoice_history_full_Jun_2026.xlsx"
    assert (
        last_three_months_history_filename(date(2026, 6, 1))
        == "invoice_history_last_3_months_Jun_2026.xlsx"
    )


if __name__ == "__main__":
    test_appends_current_month_column_to_wide_history()
    test_adds_new_person_not_in_history()
    test_trimmed_history_keeps_only_last_three_months()
    test_updated_history_filename()
    print("History tracker tests passed.")
