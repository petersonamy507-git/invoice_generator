"""Generate filled Beecodify from the (2).docx format and compare visually."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz

from backend.app.models import InvoiceTask, WordInvoiceData
from backend.app.services.word_invoice_generator import generate_word_invoice
from backend.app.services.word_to_pdf import convert_docx_batch_to_pdf

OUT = Path(r"d:\AI_Cache\temp\bee_compare")
OUT.mkdir(parents=True, exist_ok=True)
PROPER = Path(r"d:\AI_Cache\temp\1790191010S-BeecodifyInc (2).docx")
USER_OUT = Path(r"d:\AI_Cache\temp\1790191010S-BeecodifyInc.docx")


def render_pdf(pdf_bytes: bytes, png_path: Path, zoom: float = 1.8) -> None:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    png_path.write_bytes(pix.tobytes("png"))
    doc.close()


def main() -> None:
    data = WordInvoiceData(
        person_name="Sample Person",
        company_name="Beecodify Inc",
        email="t@example.com",
        total_amount=1500,
        invoice_number=11,
        tasks=[
            InvoiceTask("A", "Web Design", 500),
            InvoiceTask("B", "API Integration", 600),
            InvoiceTask("C", "Support Retainer", 400),
        ],
        bank="HBL",
        iban="PK12ABCD0000123456789012",
        branch_code="0123",
        document_invoice_no="1790191010S",
    )
    gen_bytes, _ = generate_word_invoice(data)
    gen_path = OUT / "gen_beecodify.docx"
    gen_path.write_bytes(gen_bytes)
    USER_OUT.write_bytes(gen_bytes)
    print("wrote", gen_path, "and", USER_OUT, "size", len(gen_bytes))
    print("proper size", PROPER.stat().st_size)

    for label, path in (("proper", PROPER), ("gen", gen_path)):
        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        print(
            label,
            "drawing",
            xml.count("w:drawing"),
            "xml_len",
            len(xml),
            "size",
            path.stat().st_size,
        )

    items = [(PROPER.read_bytes(), "proper.docx"), (gen_bytes, "gen.docx")]
    for pdf_bytes, name in convert_docx_batch_to_pdf(items):
        stem = Path(name).stem
        (OUT / f"{stem}.pdf").write_bytes(pdf_bytes)
        render_pdf(pdf_bytes, OUT / f"{stem}.png")
        print("png", stem)


if __name__ == "__main__":
    main()
