"""List AcroForm field names in a PDF template (for setup)."""
import sys
from pathlib import Path

import fitz


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/list_pdf_fields.py <path-to.pdf>")
        sys.exit(1)
    path = Path(sys.argv[1])
    doc = fitz.open(path)
    found = False
    for i, page in enumerate(doc):
        for widget in page.widgets() or []:
            found = True
            print(f"Page {i}: {widget.field_name!r} ({widget.field_type_string})")
    if not found:
        print("No form fields found. Use field_positions.json for coordinate overlay.")
    doc.close()


if __name__ == "__main__":
    main()
