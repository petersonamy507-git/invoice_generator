import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd

from backend.app.services.excel_parser import read_excel
from backend.app.services.validation import ValidationError, normalize_columns, require_columns
from backend.app.services.word_date_updater import copy_and_update_date
from backend.app.services.word_templates import (
    INVOICE_WORD_MAP,
    WORD_OUTPUT_DIR,
    ensure_template_exists,
    template_filename,
    validate_invoice_number,
)

INVOICE_COLUMN = "invoice"


def parse_invoice_excel(content: bytes) -> pd.DataFrame:
    df = read_excel(content)
    normalize_columns(df)
    require_columns(df, [INVOICE_COLUMN], "Invoice test sheet")
    if df.empty:
        raise ValidationError("Invoice test sheet has no data rows.")
    return df


def output_filename(invoice_number: int, row_index: int) -> str:
    base = INVOICE_WORD_MAP[invoice_number]
    day = date.today().strftime("%Y-%m-%d")
    return f"{base}_{day}_row{row_index}.docx"


def process_word_test_rows(
    content: bytes,
    output_dir: Path | None = None,
) -> list[Path]:
    df = parse_invoice_excel(content)
    out_dir = output_dir or WORD_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for idx, row in df.iterrows():
        row_num = int(idx) + 2 if isinstance(idx, int) else idx
        ctx = f"Row {row_num}: "
        invoice_number = validate_invoice_number(row[INVOICE_COLUMN], ctx)
        source = ensure_template_exists(invoice_number)
        dest = out_dir / output_filename(invoice_number, row_num)
        copy_and_update_date(source, dest, invoice_number=invoice_number)
        saved.append(dest)

    return saved


def build_word_test_zip(content: bytes) -> tuple[bytes, list[str]]:
    df = parse_invoice_excel(content)
    buffer = BytesIO()
    names: list[str] = []

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, row in df.iterrows():
            row_num = int(idx) + 2 if isinstance(idx, int) else idx
            ctx = f"Row {row_num}: "
            invoice_number = validate_invoice_number(row[INVOICE_COLUMN], ctx)
            source = ensure_template_exists(invoice_number)
            dest_name = output_filename(invoice_number, row_num)
            out_path = WORD_OUTPUT_DIR / dest_name
            copy_and_update_date(source, out_path, invoice_number=invoice_number)
            zf.write(out_path, arcname=dest_name)
            names.append(dest_name)

    buffer.seek(0)
    return buffer.getvalue(), names
