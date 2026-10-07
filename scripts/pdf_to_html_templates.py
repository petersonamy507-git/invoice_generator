"""Convert invoice PDFs in Data/word/ into all_templates/*.html (+ assets)."""
from __future__ import annotations

import html
import shutil
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
WORD_DIR = ROOT / "Data" / "word"
OUT_DIR = ROOT / "all_templates"

# Matches backend.app.services.html_templates.INVOICE_HTML_MAP
PDF_SOURCES = [
    (WORD_DIR / "Invoice1-MAXIS .pdf", "Invoice1-MAXIS"),
    (WORD_DIR / "Invoice02-ForestTechInc1.pdf", "Invoice02-ForestTechInc1"),
    (WORD_DIR / "Invoice03-RadnorInnovationsInc.pdf", "Invoice03-RadnorInnovationsInc"),
    (WORD_DIR / "Invoice04-APPFOUNDERSINC.pdf", "Invoice04-APPFOUNDERSINC"),
    (WORD_DIR / "Invoice05-DynamoCreativesInc.pdf", "Invoice05-DynamoCreativesInc"),
]

# Render scale for crisp page images (2x ≈ 144 dpi from 72)
RENDER_SCALE = 2.0


def convert_one(pdf_path: Path, stem: str) -> Path:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Missing PDF: {pdf_path}")

    assets = OUT_DIR / f"{stem}_files"
    if assets.exists():
        shutil.rmtree(assets)
    assets.mkdir(parents=True)

    # Keep a copy of the source PDF beside the HTML for generation.
    dest_pdf = OUT_DIR / f"{stem}.pdf"
    shutil.copy2(pdf_path, dest_pdf)

    doc = fitz.open(pdf_path)
    page_imgs: list[tuple[str, float, float]] = []
    try:
        mat = fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_name = f"page{i + 1}.png"
            pix.save(assets / img_name)
            page_imgs.append((img_name, pix.width / RENDER_SCALE, pix.height / RENDER_SCALE))
    finally:
        doc.close()

    pages_html = []
    for img_name, w, h in page_imgs:
        pages_html.append(
            f'<div class="page" style="width:{w:.1f}pt;height:{h:.1f}pt">'
            f'<img src="{html.escape(stem)}_files/{html.escape(img_name)}" '
            f'width="{w:.1f}" height="{h:.1f}" alt="Invoice page"/>'
            f"</div>"
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="generator" content="pdf-to-html"/>
  <title>{html.escape(stem)}</title>
  <style>
    html, body {{ margin: 0; padding: 0; background: #e8e8e8; }}
    .page {{
      margin: 16px auto;
      background: #fff;
      box-shadow: 0 1px 4px rgba(0,0,0,.2);
      overflow: hidden;
    }}
    .page img {{ display: block; width: 100%; height: auto; }}
  </style>
</head>
<body>
{"".join(pages_html)}
</body>
</html>
"""
    out_html = OUT_DIR / f"{stem}.html"
    out_html.write_text(html_doc, encoding="utf-8")
    return out_html


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    for pdf_path, stem in PDF_SOURCES:
        out = convert_one(pdf_path, stem)
        size = out.stat().st_size
        pdf_size = (OUT_DIR / f"{stem}.pdf").stat().st_size
        print(f"OK {stem}.html ({size} bytes) + {stem}.pdf ({pdf_size} bytes)")


if __name__ == "__main__":
    main()
