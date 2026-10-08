"""Fill Word invoice templates via Microsoft Word COM (preserves shapes/headers).

python-docx rewrite/save strips DrawingML (e.g. Beecodify blue/gray header bars).
On Windows we copy the template and edit it with Word instead.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

from backend.app.models import WordInvoiceData
from backend.app.services.validation import ValidationError
from backend.app.services.word_date_updater import format_invoice_date
from backend.app.services.word_field_updater import format_amount
from backend.app.services.word_template_config import line_item_config
from backend.app.services.word_templates import ensure_template_exists


def _word_app():
    try:
        import pythoncom
        import win32com.client
    except ImportError as e:
        raise ValidationError(
            "Microsoft Word (pywin32) is required to fill invoice templates."
        ) from e
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    return word


def _replace_all(doc, find_text: str, replace_text: str) -> int:
    """Replace all occurrences via Word Find. Returns 1 if a match was replaced."""
    return _replace(doc, find_text, replace_text, replace_all=True)


def _replace_one(doc, find_text: str, replace_text: str) -> int:
    """Replace the first occurrence only (wdReplaceOne)."""
    return _replace(doc, find_text, replace_text, replace_all=False)


def _replace(doc, find_text: str, replace_text: str, *, replace_all: bool) -> int:
    if not find_text:
        return 0
    # win32com: property-then-Execute often no-ops; pass args to Execute.
    repl = replace_text if len(replace_text) <= 255 else replace_text[:255]
    ok = doc.Content.Find.Execute(
        FindText=find_text,
        MatchCase=False,
        MatchWholeWord=False,
        MatchWildcards=False,
        MatchSoundsLike=False,
        MatchAllWordForms=False,
        Forward=True,
        Wrap=1,  # wdFindContinue
        Format=False,
        ReplaceWith=repl,
        Replace=2 if replace_all else 1,  # wdReplaceAll / wdReplaceOne
    )
    return int(bool(ok))


def _money(amount: int, invoice_number: int) -> str:
    """Beecodify/Coretechify samples use $X.00; skip thousands comma so TOTAL cell does not wrap."""
    if invoice_number in (8, 11):
        return f"${amount:.2f}"
    return format_amount(amount)


def _set_cell_text(table, row_1based: int, col_1based: int, text: str) -> None:
    """
    Replace visible text in a table cell without collapsing its paragraph
    structure. Beecodify cells are [empty para][content para + cell mark];
    wiping cell.Range destroys spacing and TOTAL alignment.
    """
    cell = table.Cell(row_1based, col_1based)
    target = None
    for i in range(1, cell.Range.Paragraphs.Count + 1):
        para = cell.Range.Paragraphs(i)
        probe = para.Range.Duplicate
        # End-of-cell marker is one Word character (often repr as \\r\\x07).
        probe.MoveEnd(1, -1)
        visible = probe.Text.replace("\r", "").replace("\x07", "")
        if visible.strip():
            target = para
            break
    if target is None:
        target = cell.Range.Paragraphs(cell.Range.Paragraphs.Count)

    rng = target.Range.Duplicate
    rng.MoveEnd(1, -1)  # strip cell mark
    if rng.Text.endswith("\r"):
        rng.MoveEnd(1, -1)
    # Keep a non-empty placeholder so the empty leading para / row height stays.
    rng.Text = text if text != "" else " "


def _fill_line_items(doc, data: WordInvoiceData) -> None:
    config = line_item_config(data.invoice_number)
    if doc.Tables.Count < config.table_index + 1:
        return
    table = doc.Tables(config.table_index + 1)
    tasks = list(data.tasks[:3]) if data.tasks else []
    for i, row_idx in enumerate(config.line_item_rows):
        if i >= len(tasks):
            break
        row_1 = row_idx + 1
        if row_1 > table.Rows.Count:
            continue
        task = tasks[i]
        cols = table.Columns.Count
        if config.desc_col + 1 <= cols:
            _set_cell_text(table, row_1, config.desc_col + 1, task.sub_task)
        if config.amount_col + 1 <= cols:
            _set_cell_text(
                table,
                row_1,
                config.amount_col + 1,
                _money(task.amount, data.invoice_number),
            )
    for row_idx in config.clear_rows:
        row_1 = row_idx + 1
        if row_1 > table.Rows.Count:
            continue
        cols = table.Columns.Count
        if config.desc_col + 1 <= cols:
            _set_cell_text(table, row_1, config.desc_col + 1, "")
        if config.amount_col + 1 <= cols:
            _set_cell_text(table, row_1, config.amount_col + 1, "")


def _fill_common_text(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    new_date = format_invoice_date(invoice_date)
    inv = data.document_invoice_no or ""
    bank = data.bank or ""
    name = data.person_name or ""
    iban = data.iban or ""
    branch = data.branch_code or ""
    total = _money(data.total_amount, data.invoice_number)
    n = data.invoice_number

    # Invoice numbers (template samples) — avoid bare short digits globally
    if inv:
        _replace_all(doc, "NO. 000001", f"NO. {inv}")
        _replace_all(doc, "INVOICE NO. 000001", f"INVOICE NO. {inv}")
        _replace_all(doc, "2024-003", inv)
        _replace_all(doc, "150305", inv)
        _replace_all(doc, "52131", inv)
        if n in (6, 10, 12):
            _replace_all(doc, "01234", inv)
        if n == 9:
            _replace_all(doc, "1 2 3 4 / 5 6 7 8 9", inv)

    # Dates used in templates
    for sample in (
        "September 15, 2030",
        "March 14, 2025",
        "March 15, 2025",
        "11.02.2030",
        "11.03.2030",
        "28/ 07 / 2095",
        "0 1 / 0 2 / 2 0 2 3",
    ):
        _replace_all(doc, sample, new_date)

    # Beecodify (11): payment lines use soft breaks (^l / Chr(11)), not ^p
    if n in (8, 11):
        replaced = _replace_all(
            doc,
            "Bank Name^lAccount Name ^lAccount NO ^lBranch Code",
            f"Bank Name: {bank}^lAccount Name: {name}^lAccount NO: {iban}^lBranch Code: {branch}",
        )
        if not replaced:
            replaced = _replace_all(
                doc,
                "Bank Name^pAccount Name ^pAccount NO ^pBranch Code",
                f"Bank Name: {bank}^pAccount Name: {name}^pAccount NO: {iban}^pBranch Code: {branch}",
            )
        if not replaced:
            _replace_all(doc, "Bank Name", f"Bank Name: {bank}")
            _replace_all(doc, "Account Name ", f"Account Name: {name} ")
            _replace_all(doc, "Account NO ", f"Account NO: {iban} ")
            _replace_all(doc, "Branch Code", f"Branch Code: {branch}")
    else:
        _replace_all(doc, "Account Name: Daniel Gallego", f"Account Name: {name}")
        _replace_all(doc, "Daniel Gallego", name)
        _replace_all(doc, "Account No.: 0123 4567 8901", f"Account No.: {iban}")
        _replace_all(doc, "0123 4567 8901", iban)
        # Bank Name label alone (Ravotek / Cozy)
        _replace_all(doc, "Bank Name", f"Bank Name: {bank}")
        _replace_all(doc, "Branch Code:", f"Branch Code: {branch}")
        _replace_all(doc, "Branch Code", f"Branch Code: {branch}")

    # Sample totals in body text (table totals set via cells for 8/11)
    if n not in (8, 11):
        for sample_total in ("$95.00", "$2024", "$2244", "$30,000", "$285", "$0,000.00"):
            _replace_all(doc, sample_total, total)


def _fill_template_extras(doc, data: WordInvoiceData) -> None:
    """Template-specific table totals after line items."""
    n = data.invoice_number
    total = _money(data.total_amount, n)
    if n in (6,) and doc.Tables.Count >= 2:
        _set_cell_text(doc.Tables(2), 1, doc.Tables(2).Columns.Count, total)
    if n in (8, 11) and doc.Tables.Count >= 1:
        table = doc.Tables(1)
        if table.Rows.Count >= 7:
            _set_cell_text(table, 7, table.Columns.Count, total)
    if n == 10:
        _replace_all(doc, "$2244", total)
        _replace_all(doc, "   $2244", f"   {total}")
    if n == 12 and doc.Tables.Count >= 1:
        table = doc.Tables(1)
        if table.Rows.Count >= 7:
            _set_cell_text(table, 7, table.Columns.Count, total)
            if table.Columns.Count >= 5:
                _set_cell_text(table, 7, 5, total)
            bank = data.bank or ""
            name = data.person_name or ""
            iban = data.iban or ""
            branch = data.branch_code or ""
            _set_cell_text(
                table,
                7,
                1,
                (
                    f"Account Name: {name} Bank Name: {bank} "
                    f"Account No: {iban} Branch Code: {branch}"
                ),
            )
    if n == 9 and doc.Tables.Count >= 3:
        summary = doc.Tables(3)
        if summary.Rows.Count >= 1:
            _set_cell_text(summary, 1, summary.Columns.Count, total)
        if summary.Rows.Count >= 2:
            _set_cell_text(summary, 2, summary.Columns.Count, "$0")
        if summary.Rows.Count >= 3:
            _set_cell_text(summary, 3, summary.Columns.Count, "$0")
        if summary.Rows.Count >= 4:
            _set_cell_text(summary, 4, summary.Columns.Count, total)
    if n == 13:
        _replace_all(doc, "$285", total)
        _replace_all(doc, "Total\t$285", f"Total\t{total}")
    if n == 14 and doc.Tables.Count >= 2:
        _set_cell_text(doc.Tables(2), 1, doc.Tables(2).Columns.Count, total)
        # Synergo item title rows
        if data.tasks and len(data.tasks) >= 3 and doc.Tables.Count >= 1:
            table = doc.Tables(1)
            for task, row in zip(data.tasks[:3], (2, 5, 7)):
                if row <= table.Rows.Count:
                    _set_cell_text(table, row, 1, task.sub_task)
            for task, row in zip(data.tasks[:3], (3, 6, 8)):
                if row <= table.Rows.Count and table.Columns.Count >= 4:
                    _set_cell_text(table, row, 4, format_amount(task.amount))


def _fill_beecodify(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    """
    Fill Invoice11 from the original Beecodify DOCX format.

    Template has 5 sample service rows. We fill the first 3 tasks, then delete
    unused sample rows — leaving blank rows adds extra divider lines and pushes
    PDF export onto a second empty page.
    """
    new_date = format_invoice_date(invoice_date)
    inv = data.document_invoice_no or ""
    bank = data.bank or ""
    name = data.person_name or ""
    iban = data.iban or ""
    branch = data.branch_code or ""
    total = _money(data.total_amount, 11)
    tasks = list(data.tasks[:3]) if data.tasks else []

    if inv:
        _replace_all(doc, "NO. 000001", f"NO. {inv}")
    _replace_all(doc, "September 15, 2030", new_date)

    _replace_all(
        doc,
        "Bank Name^lAccount Name ^lAccount NO ^lBranch Code",
        f"Bank Name: {bank}^lAccount Name: {name}^lAccount NO: {iban}^lBranch Code: {branch}",
    )

    # Drop the two unused sample service rows first so "Consultation" find
    # cannot alter "Business Consultation", and PDF stays on one page.
    # Table rows: 1=header, 2-6=services, 7=total, 8=note.
    if doc.Tables.Count >= 1:
        table = doc.Tables(1)
        if table.Rows.Count >= 6:
            table.Rows(6).Delete()  # Graphic Design
        if table.Rows.Count >= 5:
            table.Rows(5).Delete()  # Business Consultation

    # Remaining service samples (top-to-bottom).
    sample_names = [
        "Business Development",  # longer first
        "Web Development",
        "Consultation",
    ]
    name_task_index = {"Consultation": 0, "Web Development": 1, "Business Development": 2}
    for sample in sample_names:
        i = name_task_index[sample]
        if i < len(tasks):
            _replace_all(doc, sample, tasks[i].sub_task)

    # Amounts top-to-bottom among the 3 remaining rows: $5.00, $30.00, $5.00
    sample_amounts = ["$5.00", "$30.00", "$5.00"]
    for i, sample_amt in enumerate(sample_amounts):
        if i < len(tasks):
            _replace_one(doc, sample_amt, _money(tasks[i].amount, 11))

    _replace_all(doc, "$95.00", total)


def _com_fill_document(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    if data.invoice_number == 11:
        _fill_beecodify(doc, data, invoice_date)
        return

    _fill_common_text(doc, data, invoice_date)
    if data.invoice_number != 14:
        _fill_line_items(doc, data)
    _fill_template_extras(doc, data)
    # Ignitai textbox tables: Word Tables collection includes them
    if data.invoice_number == 7 and data.tasks:
        config = line_item_config(7)
        for ti in range(1, doc.Tables.Count + 1):
            table = doc.Tables(ti)
            try:
                header = table.Cell(2, 1).Range.Text
            except Exception:
                continue
            if "Item" not in header and "Description" not in header:
                continue
            for i, row_idx in enumerate(config.line_item_rows):
                if i >= len(data.tasks):
                    break
                row_1 = row_idx + 1
                task = data.tasks[i]
                _set_cell_text(table, row_1, config.desc_col + 1, task.sub_task)
                _set_cell_text(
                    table, row_1, config.amount_col + 1, format_amount(task.amount)
                )
            if table.Rows.Count >= 9:
                _set_cell_text(
                    table, 9, table.Columns.Count, format_amount(data.total_amount)
                )


def generate_docx_bytes_via_word_com(
    data: WordInvoiceData,
    *,
    invoice_date: date | None = None,
) -> bytes:
    """Return filled .docx bytes using MS Word (keeps original visual format)."""
    source = ensure_template_exists(data.invoice_number)
    word = _word_app()
    try:
        with tempfile.TemporaryDirectory(prefix="inv-com-") as tmp:
            work = Path(tmp) / source.name
            shutil.copy2(source, work)
            doc = word.Documents.Open(str(work.resolve()), ReadOnly=False)
            try:
                _com_fill_document(doc, data, invoice_date)
                # Save in place (not SaveAs2) to keep original package/layout closer
                # to the source template (e.g. Beecodify (2).docx format).
                doc.Save()
            finally:
                doc.Close(False)
            return work.read_bytes()
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            f"Could not fill Word template with Microsoft Word: {e}"
        ) from e
    finally:
        try:
            word.Quit()
        except Exception:
            pass
