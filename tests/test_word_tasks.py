import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from docx import Document

from backend.app.models import WordInvoiceData, InvoiceTask
from backend.app.services.word_invoice_generator import (
    generate_word_invoice,
    parse_manual_word_invoice,
)
from backend.app.services.word_field_updater import update_invoice_fields
from backend.app.services.word_templates import ensure_template_exists
from backend.app.services.excel_parser import generate_bulk_invoices
import zipfile

from backend.app.services.zip_export import build_zip
from docx import Document as DocxDocument


def test_manual_invoice_assigns_tasks_to_line_items():
    data = parse_manual_word_invoice(
        person_name="John Doe",
        company_name="Acme Corp",
        email="john@example.com",
        total_amount=1000,
        invoice_number=4,
    )
    assert len(data.tasks) == 3
    assert sum(t.amount for t in data.tasks) == 1000
    subtasks = {t.sub_task for t in data.tasks}
    assert len(subtasks) == 3

    doc = DocxDocument(str(ensure_template_exists(4)))
    update_invoice_fields(doc, data)
    table = doc.tables[2]
    for i, row_idx in enumerate([1, 2, 3]):
        desc = table.rows[row_idx].cells[1].text.strip()
        amount = table.rows[row_idx].cells[3].text.strip()
        assert desc == data.tasks[i].sub_task
        assert amount == f"${data.tasks[i].amount:,}"


def test_bulk_word_zip_contains_assigned_tasks():
    current = pd.DataFrame(
        [
            {
                "Name": "Alice",
                "Bank": "United Bank",
                "IBAN NO.": "PK11ALICE123",
                "Branch Code": "0213",
                "Invoice": 3,
                "Invoice No.": "STS-001",
                "Amount": 2000,
            }
        ]
    )
    buf = BytesIO()
    current.to_excel(buf, index=False)
    current_bytes = buf.getvalue()

    result = generate_bulk_invoices(current_bytes, "account")
    assert len(result.invoices) == 1
    assert len(result.invoices[0].tasks) == 3

    zip_bytes = build_zip(result.invoices)
    assert len(zip_bytes) > 1000
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        pdf_names = [n for n in names if n.lower().endswith(".pdf")]
        assert pdf_names, f"Expected PDF invoices in ZIP, got: {names}"


if __name__ == "__main__":
    test_manual_invoice_assigns_tasks_to_line_items()
    test_bulk_word_zip_contains_assigned_tasks()
    print("All word task tests passed.")
