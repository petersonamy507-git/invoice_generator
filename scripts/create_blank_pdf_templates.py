"""Create minimal blank PDF templates with AcroForm fields for local testing."""
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "templates" / "pdf"

FIELD_SPECS = [
    ("person_name", 72, 120, 200, 14),
    ("company_name", 72, 140, 200, 14),
    ("email", 72, 160, 220, 14),
    ("invoice_date", 350, 120, 120, 14),
    ("task_1_main", 72, 280, 140, 12),
    ("task_1_sub", 220, 280, 160, 12),
    ("task_1_amount", 420, 280, 80, 12),
    ("task_2_main", 72, 310, 140, 12),
    ("task_2_sub", 220, 310, 160, 12),
    ("task_2_amount", 420, 310, 80, 12),
    ("task_3_main", 72, 340, 140, 12),
    ("task_3_sub", 220, 340, 160, 12),
    ("task_3_amount", 420, 340, 80, 12),
    ("total_amount", 350, 680, 120, 14),
]


def create_template(structure: int) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(
        (72, 50),
        f"Invoice Structure {structure} — Template",
        fontsize=16,
        fontname="helv",
    )
    page.insert_text(
        (72, 75),
        "Upload your branded PDF to replace this test file.",
        fontsize=9,
        fontname="helv",
        color=(0.4, 0.4, 0.4),
    )
    for name, x, y, w, h in FIELD_SPECS:
        widget = fitz.Widget()
        widget.field_name = name
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(x, y, x + w, y + h)
        widget.field_flags = fitz.PDF_FIELD_IS_READ_ONLY
        page.add_widget(widget)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"invoice_structure_{structure}.pdf"
    doc.save(path)
    doc.close()
    print(f"Wrote {path}")


if __name__ == "__main__":
    for n in range(1, 5):
        create_template(n)
