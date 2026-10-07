import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend.app.services.category_tasks import (
    CATEGORIES,
    SERVICES_EXCEL_PATH,
    categories_status,
    load_category_tasks_df,
)
from backend.app.services.excel_parser import generate_bulk_invoices
from backend.app.services.validation import ValidationError


def test_services_file_exists():
    assert SERVICES_EXCEL_PATH.is_file(), f"Missing {SERVICES_EXCEL_PATH}"
    assert SERVICES_EXCEL_PATH.name == "ListOFservicesforInvoices_v.1.2.xlsx"


def test_each_category_has_enough_items():
    for key in CATEGORIES:
        df = load_category_tasks_df(key)
        assert "main_task" in df.columns
        assert "sub_task" in df.columns
        assert len(df) >= 3


def test_categories_use_different_sheets():
    qa = set(load_category_tasks_df("qa")["sub_task"])
    devops = set(load_category_tasks_df("devops")["sub_task"])
    call_centre = set(load_category_tasks_df("call_centre")["sub_task"])
    assert qa != devops
    assert not qa.intersection(devops)
    assert call_centre


def _current_month_bytes(people=None):
    if people is None:
        people = ["Alice"]
    current = pd.DataFrame(
        [
            {
                "Name": name,
                "Bank": "United Bank",
                "IBAN NO.": f"PK11{name.upper()}123",
                "Branch Code": "0213",
                "Invoice": 3,
                "Invoice No.": f"STS-{i:03d}",
                "Amount": 2000,
            }
            for i, name in enumerate(people, start=1)
        ]
    )
    buf = BytesIO()
    current.to_excel(buf, index=False)
    return buf.getvalue()


def test_bulk_uses_category_task_sheet():
    result = generate_bulk_invoices(_current_month_bytes(["Alice"]), "account")
    assert len(result.invoices) == 1
    assert len(result.invoices[0].tasks) == 3
    for task in result.invoices[0].tasks:
        assert task.sub_task


def test_invalid_category_rejected():
    try:
        generate_bulk_invoices(_current_month_bytes(["X"]), "marketing")
        assert False, "expected ValidationError"
    except ValidationError as e:
        assert "Invalid category" in str(e)


def test_categories_status():
    status = categories_status()
    assert status["exists"]
    assert status["categories"]["qa"]["label"] == "QA"
    assert status["categories"]["devops"]["label"] == "Devops"
    assert status["categories"]["call_centre"]["label"] == "Call centre"
    assert status["categories"]["account"]["label"] == "Account"
    assert status["categories"]["account"]["sheet"] == "Accounts"
    assert status["categories"]["hr"]["ready"]


def test_bulk_assigns_unique_items_per_person():
    people = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
    result = generate_bulk_invoices(_current_month_bytes(people), "account")
    assert len(result.invoices) == 5

    seen: set[str] = set()
    for invoice in result.invoices:
        subs = [task.sub_task.lower() for task in invoice.tasks]
        assert len(subs) == 3
        assert len(set(subs)) == 3
        for sub in subs:
            assert sub not in seen
            seen.add(sub)
    assert len(seen) == 15


def test_bulk_does_not_require_history_upload():
    result = generate_bulk_invoices(_current_month_bytes(["Alice", "Bob"]), "qa")
    assert len(result.invoices) == 2
    assert result.updated_history_bytes
    assert result.last_three_months_history_bytes


if __name__ == "__main__":
    test_services_file_exists()
    test_each_category_has_enough_items()
    test_categories_use_different_sheets()
    test_bulk_uses_category_task_sheet()
    test_bulk_assigns_unique_items_per_person()
    test_bulk_does_not_require_history_upload()
    test_invalid_category_rejected()
    test_categories_status()
    print("Category bulk tests passed.")
