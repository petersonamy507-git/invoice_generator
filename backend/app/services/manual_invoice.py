import json
from datetime import date
from pathlib import Path

import pandas as pd

from backend.app.models import InvoiceData
from backend.app.services.task_assignment import build_invoices_from_dataframe
from backend.app.services.validation import (
    ValidationError,
    validate_email_address,
    validate_non_empty_text,
    validate_structure_number,
    validate_total_amount,
)

DEFAULT_TASKS_PATH = Path(__file__).resolve().parents[2] / "data" / "default_tasks.json"


def load_default_tasks_df() -> pd.DataFrame:
    if not DEFAULT_TASKS_PATH.exists():
        raise ValidationError("Default task catalog is missing on the server.")
    with open(DEFAULT_TASKS_PATH, encoding="utf-8") as f:
        tasks = json.load(f)
    return pd.DataFrame(tasks)


def create_manual_invoice(
    person_name: str,
    company_name: str,
    email: str,
    total_amount: float,
    structure_number: int,
) -> InvoiceData:
    person_name = validate_non_empty_text(person_name, "Person name")
    company_name = validate_non_empty_text(company_name, "Company name")
    email = validate_email_address(email)
    structure_number = validate_structure_number(structure_number)
    total_amount = validate_total_amount(total_amount)

    row = {
        "person_name": person_name,
        "company_name": company_name,
        "email": email,
        "invoice_structure_number": structure_number,
        "total_amount": total_amount,
    }
    current_df = pd.DataFrame([row])
    history_df = pd.DataFrame(columns=["person_name", "task_name", "invoice_month"])
    tasks_df = load_default_tasks_df()

    invoices = build_invoices_from_dataframe(
        current_df,
        history_df,
        tasks_df,
        invoice_date=date.today(),
        row_validators=lambda r, ctx: {
            "person_name": validate_non_empty_text(r["person_name"], "Person name"),
            "company_name": validate_non_empty_text(r["company_name"], "Company name"),
            "email": validate_email_address(r["email"]),
            "structure_number": validate_structure_number(
                r["invoice_structure_number"], ctx
            ),
            "total_amount": validate_total_amount(r["total_amount"], ctx),
        },
    )
    return invoices[0]
