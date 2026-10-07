"""Create minimal Word invoice files for local testing (if real files are missing)."""
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
WORD_DIR = ROOT / "Data" / "word"

FILES = {
    1: "Invoice1.docx",
    2: "Invoice02-ForestTechInc1.docx",
    3: "Invoice03-RadnorInnovationsInc.docx",
    4: "Invoice04-APPFOUNDERSINC.docx",
    5: "Invoice05-DynamoCreativesInc.docx",
}


def create_invoice(filename: str, company: str) -> None:
    path = WORD_DIR / filename
    if path.exists():
        print(f"Skip (exists): {path.name}")
        return
    doc = Document()
    doc.add_heading(f"Invoice — {company}", level=1)
    doc.add_paragraph("Bill To: Sample Customer")
    doc.add_paragraph("Dated: January 15, 2025")
    doc.add_paragraph("Total Amount: $1,000.00")
    doc.add_paragraph("This is a placeholder file for Word date-update testing.")
    WORD_DIR.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    print(f"Wrote {path}")


if __name__ == "__main__":
    companies = [
        "MAXIS TECHNOLOGIES INC",
        "Forest Tech Inc",
        "Radnor Innovations Inc",
        "Fusionfolio Media Inc",
        "Dynamo Creatives Inc",
    ]
    for num, filename in FILES.items():
        create_invoice(filename, companies[num - 1])
