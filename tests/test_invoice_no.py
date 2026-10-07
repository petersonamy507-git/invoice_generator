import sys
from datetime import date
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from docx import Document

from backend.app.models import InvoiceTask, WordInvoiceData
from backend.app.services.history_tracker import (
    build_updated_history_excel,
    current_month_invoice_no_column_name,
)
from backend.app.services.invoice_no_utils import increment_invoice_no
from backend.app.services.word_field_updater import update_invoice_fields
from backend.app.services.word_templates import ensure_template_exists


def test_increment_invoice_no():
    assert increment_invoice_no("HH-007") == "HH-008"
    assert increment_invoice_no("AA-001") == "AA-002"
    assert increment_invoice_no("STS-001") == "STS-002"


def test_invoice_no_written_to_template():
    data = WordInvoiceData(
        person_name="Test",
        company_name="Test",
        email="t@t.com",
        total_amount=5000,
        invoice_number=1,
        tasks=[InvoiceTask(main_task="M", sub_task="A", amount=1000)] * 3,
        document_invoice_no="HH-008",
    )
    doc = Document(str(ensure_template_exists(1)))
    update_invoice_fields(doc, data)
    full = "\n".join(p.text for p in doc.paragraphs)
    assert "HH-008" in full


def test_history_excel_includes_invoice_no_column():
    history = pd.DataFrame([{"Name": "Alice", "May,26": "Item A"}])
    invoices = [
        WordInvoiceData(
            person_name="Alice",
            company_name="Alice",
            email="t@t.com",
            total_amount=1000,
            invoice_number=1,
            tasks=[InvoiceTask(main_task="M", sub_task="X", amount=1000)] * 3,
            sheet_invoice_no="HH-007",
            document_invoice_no="HH-008",
        )
    ]
    col = current_month_invoice_no_column_name(date(2026, 6, 1))
    xlsx = build_updated_history_excel(history, invoices, date(2026, 6, 1))
    out = pd.read_excel(BytesIO(xlsx))
    assert col in out.columns
    assert out.loc[out["Name"] == "Alice", col].iloc[0] == "HH-008"


if __name__ == "__main__":
    test_increment_invoice_no()
    test_invoice_no_written_to_template()
    test_history_excel_includes_invoice_no_column()
    print("Invoice No. tests passed.")
