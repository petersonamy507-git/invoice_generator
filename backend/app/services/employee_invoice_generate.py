from __future__ import annotations

from datetime import date
from typing import Any

import pymysql

from backend.app.db.connection import db_transaction
from backend.app.db.employees_repo import get_employee, update_last_invoice
from backend.app.db.invoice_backup_repo import insert_invoice_backup
from backend.app.models import InvoiceTask, WordInvoiceData
from backend.app.services.amount_distribution import distribute_amounts
from backend.app.services.club_assignment import assign_club_for_employee, assert_club_insert_ok
from backend.app.services.invoice_no_utils import increment_invoice_no, validate_invoice_no_text
from backend.app.services.validation import ValidationError, validate_total_amount
from backend.app.services.word_templates import validate_invoice_number
from backend.app.services.zip_export import build_zip


def _tasks_from_club_items(line_items: list[str], total_amount: int) -> list[InvoiceTask]:
    amounts = distribute_amounts(total_amount)
    return [
        InvoiceTask(main_task="Services", sub_task=item, amount=amt)
        for item, amt in zip(line_items, amounts)
    ]


def generate_invoices_for_employees(
    selections: list[dict[str, Any]],
    *,
    invoice_date: date | None = None,
) -> bytes:
    """
    selections item:
      employee_id, amount, invoice_no (sheet value), invoice_template (1-5)

    Club assignment:
      - pick unique club_id from clubing for employee department
      - respect invoice_backup history (3-month employee + same-month global)
      - fill invoice line items from clubing.clubs split by ' | '
    """
    if not selections:
        raise ValidationError("Select at least one employee.")

    today = invoice_date or date.today()
    prepared: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(selections, start=1):
        ctx = f"Selection {i}: "
        eid = str(raw.get("employee_id") or "").strip()
        if not eid:
            raise ValidationError(f"{ctx}employee_id is required.")
        if eid in seen_ids:
            raise ValidationError(f"{ctx}duplicate employee_id {eid!r}.")
        seen_ids.add(eid)
        employee = get_employee(eid, active_only=True)
        amount = validate_total_amount(raw.get("amount"), f"{ctx}Amount")
        sheet_invoice_no = validate_invoice_no_text(
            str(raw.get("invoice_no") or "").strip(),
            f"{ctx}Invoice No.",
        )
        document_invoice_no = increment_invoice_no(sheet_invoice_no)
        template = validate_invoice_number(raw.get("invoice_template"), ctx)
        prepared.append(
            {
                "employee": employee,
                "amount": amount,
                "sheet_invoice_no": sheet_invoice_no,
                "document_invoice_no": document_invoice_no,
                "invoice_template": template,
            }
        )

    word_invoices: list[WordInvoiceData] = []
    batch_used_clubs: set[str] = set()

    try:
        with db_transaction() as (_conn, cur):
            for item in prepared:
                emp = item["employee"]
                department = emp["department"]
                club = assign_club_for_employee(
                    employee_id=emp["employee_id"],
                    department=department,
                    as_of=today,
                    cur=cur,
                    extra_excluded_club_ids=batch_used_clubs,
                )
                invoice_tasks = _tasks_from_club_items(
                    club["line_items"], item["amount"]
                )
                record = {
                    "employee_id": emp["employee_id"],
                    "department": department,
                    "club_id": club["club_id"],
                    "club_name": club["clubs"],
                    "invoice_template": item["invoice_template"],
                    "sheet_invoice_no": item["sheet_invoice_no"],
                    "document_invoice_no": item["document_invoice_no"],
                    "amount": item["amount"],
                    "invoice_date": today,
                    "invoice_year": today.year,
                    "invoice_month": today.month,
                    "line_items": [
                        {
                            "main_task": t.main_task,
                            "sub_task": t.sub_task,
                            "amount": t.amount,
                        }
                        for t in invoice_tasks
                    ],
                }
                try:
                    insert_invoice_backup(record, cur)
                except Exception as e:
                    assert_club_insert_ok(e, club["club_id"])
                update_last_invoice(
                    emp["employee_id"], item["document_invoice_no"], cur=cur
                )
                batch_used_clubs.add(str(club["club_id"]))

                word_invoices.append(
                    WordInvoiceData(
                        person_name=emp["name"],
                        company_name=emp["name"],
                        email="invoice@local.invalid",
                        total_amount=item["amount"],
                        invoice_number=item["invoice_template"],
                        tasks=invoice_tasks,
                        bank=emp["bank_name"],
                        iban=emp["iban"],
                        branch_code=emp.get("branch_code") or "",
                        sheet_invoice_no=item["sheet_invoice_no"],
                        document_invoice_no=item["document_invoice_no"],
                    )
                )
    except ValidationError:
        raise
    except pymysql.Error as e:
        raise ValidationError(f"Database error while saving invoice history: {e}") from e

    return build_zip(word_invoices)
