"""Generate templates 1-14 and compare format fidelity vs originals."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz

from backend.app.models import InvoiceTask, WordInvoiceData
from backend.app.services.word_invoice_generator import generate_word_invoice
from backend.app.services.word_templates import INVOICE_WORD_MAP, template_path
from backend.app.services.word_to_pdf import convert_docx_batch_to_pdf

OUT = Path(r"d:\AI_Cache\temp\format_audit")
OUT.mkdir(parents=True, exist_ok=True)

SAMPLES = {
    6: Path(r"d:\AI_Cache\temp\1790191007J-RavoteckInc.docx"),
    7: Path(r"d:\AI_Cache\temp\1790191007Z-IgnitaiInc.docx"),
    8: Path(r"d:\AI_Cache\temp\1790191009M-CoretechifyInc.docx"),
    9: Path(r"d:\AI_Cache\temp\1790191009S-EcomifyInc.docx"),
    10: Path(r"d:\AI_Cache\temp\1790191009Y-CozyHomeEssentials.docx"),
    11: Path(r"d:\AI_Cache\temp\1790191010S-BeecodifyInc (3).docx"),
    12: Path(r"d:\AI_Cache\temp\1790191011E-BravixTechnologiesInc.docx"),
    13: Path(r"d:\AI_Cache\temp\1790191011Z-AlphaDigitalInc.docx"),
    14: Path(r"d:\AI_Cache\temp\1790191007G-SynergoInc.docx"),
}

TASKS = [
    InvoiceTask("S", "Property Valuation", 1200),
    InvoiceTask("S", "Professional Photography", 1500),
    InvoiceTask("S", "Online Advertising", 1800),
]


def xml_stats(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    return {
        "drawing": xml.count("w:drawing"),
        "wsp": xml.count("wps:wsp"),
        "xml_len": len(xml),
        "size": path.stat().st_size,
    }


def main() -> None:
    # Sync originals into Data/word for 6-14 when present
    for n, sample in SAMPLES.items():
        if sample.is_file():
            dest = template_path(n)
            dest.write_bytes(sample.read_bytes())
            print(f"synced template {n} <- {sample.name}")

    rows = []
    gen_items: list[tuple[bytes, str]] = []
    orig_items: list[tuple[bytes, str]] = []

    for n in sorted(INVOICE_WORD_MAP):
        tpl = template_path(n)
        data = WordInvoiceData(
            person_name="Daniel Gallego",
            company_name="Client Co",
            email="a@b.com",
            total_amount=4500,
            invoice_number=n,
            bank="HBL Bank",
            iban="012345678901",
            branch_code="0011",
            document_invoice_no="000002",
            tasks=TASKS,
        )
        try:
            docx_bytes, filename = generate_word_invoice(data)
            gen_path = OUT / f"gen_{n}.docx"
            gen_path.write_bytes(docx_bytes)
            err = ""
        except Exception as e:
            print(f"FAIL gen {n}: {e}")
            rows.append((n, "GEN_FAIL", str(e)[:80]))
            continue

        tstat = xml_stats(tpl)
        gstat = xml_stats(gen_path)
        draw_ok = gstat["drawing"] >= tstat["drawing"]
        row = {
            "n": n,
            "name": INVOICE_WORD_MAP[n],
            "tpl_draw": tstat["drawing"],
            "gen_draw": gstat["drawing"],
            "draw_ok": draw_ok,
            "tpl_size": tstat["size"],
            "gen_size": gstat["size"],
        }
        rows.append(row)
        print(
            f"{n:2} draw {tstat['drawing']}->{gstat['drawing']} "
            f"{'OK' if draw_ok else 'LOSS'} size {tstat['size']}->{gstat['size']}"
        )
        gen_items.append((docx_bytes, f"gen_{n}.docx"))
        if n in SAMPLES and SAMPLES[n].is_file():
            orig_items.append((SAMPLES[n].read_bytes(), f"orig_{n}.docx"))

    print("\n--- PDF page counts ---")
    for batch_name, items in (("orig", orig_items), ("gen", gen_items)):
        if not items:
            continue
        try:
            pdfs = convert_docx_batch_to_pdf(items)
        except Exception as e:
            print(batch_name, "PDF FAIL", e)
            continue
        for pdf_bytes, name in pdfs:
            (OUT / name).write_bytes(pdf_bytes)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages = doc.page_count
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
            (OUT / name.replace(".pdf", ".png")).write_bytes(pix.tobytes("png"))
            doc.close()
            flag = "OK" if pages == 1 else f"PAGES={pages}"
            print(f"  {name}: {flag}")

    print("\nDone", OUT)


if __name__ == "__main__":
    main()
