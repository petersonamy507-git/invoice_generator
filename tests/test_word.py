"""Tests for Word invoice date update."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docx import Document

from backend.app.services.word_date_updater import format_invoice_date, update_dated_in_document
from backend.app.services.word_test_processor import build_word_test_zip

WORD_DIR = ROOT / "Data" / "word"
OUT = WORD_DIR / "output"


def test_format_date():
    assert format_invoice_date(date(2026, 6, 1)) == "Jun 1, 2026"


def test_update_dated():
    path = WORD_DIR / "Invoice1.docx"
    if not path.is_file():
        print("Skip: Word templates not present")
        return
    doc = Document(str(path))
    update_dated_in_document(doc, date(2026, 6, 1))
    found = False
    for p in doc.paragraphs:
        if "Jun 1, 2026" in p.text or "Jun 01, 2026" in p.text:
            found = True
    assert found, "Updated date not found in document"


def test_excel_zip():
    sample = ROOT / "sample_data" / "word_invoice_test.xlsx"
    if not sample.is_file() or not (WORD_DIR / "Invoice1.docx").is_file():
        print("Skip: sample excel or templates missing")
        return
    zip_bytes, names = build_word_test_zip(sample.read_bytes())
    assert len(zip_bytes) > 100
    assert len(names) == 5


if __name__ == "__main__":
    test_format_date()
    test_update_dated()
    test_excel_zip()
    print("Word tests passed.")
