"""Fill Word invoice templates via Microsoft Word COM (preserves shapes/headers).

python-docx save strips DrawingML on some templates (Beecodify) and can inflate
page count. On Windows, templates 6–14 are filled with Word COM from the original
DOCX samples in Data/word/.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

from backend.app.models import WordInvoiceData
from backend.app.services.validation import ValidationError
from backend.app.services.word_date_updater import format_invoice_date
from backend.app.services.word_field_updater import format_amount
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


def _replace(doc, find_text: str, replace_text: str, *, replace_all: bool = True) -> int:
    if not find_text:
        return 0
    repl = replace_text if len(replace_text) <= 255 else replace_text[:255]
    ok = doc.Content.Find.Execute(
        FindText=find_text,
        MatchCase=False,
        MatchWholeWord=False,
        MatchWildcards=False,
        MatchSoundsLike=False,
        MatchAllWordForms=False,
        Forward=True,
        Wrap=1,
        Format=False,
        ReplaceWith=repl,
        Replace=2 if replace_all else 1,
    )
    return int(bool(ok))


def _replace_all(doc, find_text: str, replace_text: str) -> int:
    return _replace(doc, find_text, replace_text, replace_all=True)


def _replace_one(doc, find_text: str, replace_text: str) -> int:
    return _replace(doc, find_text, replace_text, replace_all=False)


def _full_date(invoice_date: date | None) -> str:
    d = invoice_date or date.today()
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _short_date(invoice_date: date | None) -> str:
    return format_invoice_date(invoice_date)


def _money(amount: int, *, cents: bool = False) -> str:
    """Template-safe money: auto-compacts large amounts (no thousands commas)."""
    return format_amount(amount, cents=cents)


def _set_cell_text(table, row_1based: int, col_1based: int, text: str) -> None:
    cell = table.Cell(row_1based, col_1based)
    target = None
    for i in range(1, cell.Range.Paragraphs.Count + 1):
        para = cell.Range.Paragraphs(i)
        probe = para.Range.Duplicate
        probe.MoveEnd(1, -1)
        visible = probe.Text.replace("\r", "").replace("\x07", "")
        if visible.strip():
            target = para
            break
    if target is None:
        target = cell.Range.Paragraphs(cell.Range.Paragraphs.Count)
    rng = target.Range.Duplicate
    rng.MoveEnd(1, -1)
    if rng.Text.endswith("\r"):
        rng.MoveEnd(1, -1)
    rng.Text = text if text != "" else " "
    # Shrink font for long amounts so they stay on one line in narrow cells.
    if text.startswith("$") and len(text) >= 8:
        try:
            size = float(rng.Font.Size)
            if size > 0 and size < 100:
                shrink = 2.0 if len(text) >= 10 else 1.0
                rng.Font.Size = max(7.0, size - shrink)
        except Exception:
            pass


def _delete_table_rows(table, row_1based_list: list[int]) -> None:
    """Delete rows highest-index first so indices stay valid."""
    for row_1 in sorted(row_1based_list, reverse=True):
        if 1 <= row_1 <= table.Rows.Count:
            table.Rows(row_1).Delete()


def _fill_three_service_rows(
    doc,
    data: WordInvoiceData,
    *,
    sample_names: list[str],
    sample_amounts: list[str],
    cents: bool,
) -> None:
    tasks = list(data.tasks[:3]) if data.tasks else []
    # Longest names first to avoid partial matches.
    ordered = sorted(enumerate(sample_names), key=lambda x: len(x[1]), reverse=True)
    for idx, sample in ordered:
        if idx < len(tasks):
            _replace_all(doc, sample, tasks[idx].sub_task)
    for i, sample_amt in enumerate(sample_amounts):
        if i < len(tasks):
            _replace_one(doc, sample_amt, _money(tasks[i].amount, cents=cents))


# ----- per-template fillers (original DOCX layouts) -----


def _fill_ravotek(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    # Invoice06 — 6 sample rows; keep 3, delete 4–6.
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [7, 6, 5])  # rows 5–7 were sample 4–6 (1=header)
    _replace_all(doc, "Account Name: Daniel Gallego", f"Account Name: {name}")
    _replace_all(doc, "Daniel Gallego", name)
    _replace_all(doc, "Bank Name ", f"Bank Name: {bank} ")
    _replace_all(doc, "Bank Name", f"Bank Name: {bank}")
    _replace_all(doc, "Account No.:", f"Account No.: {iban}")
    _replace_all(doc, "Branch Code:  ", f"Branch Code: {branch}  ")
    _replace_all(doc, "Branch Code:", f"Branch Code: {branch}")
    names = [
        "Property Valuation & Pricing Strategy",
        "Professional Photography",
        "Online Advertising + Social Media Ads",
    ]
    # After deleting rows 5-7, remaining amounts are $220,$300,$430
    _fill_three_service_rows(
        doc, data, sample_names=names, sample_amounts=["$220", "$300", "$430"], cents=False
    )
    _replace_all(doc, "$2024", total)
    if doc.Tables.Count >= 2:
        _set_cell_text(doc.Tables(2), 1, doc.Tables(2).Columns.Count, total)


def _ignitai_item_table(doc):
    """Ignitai line items live in a textbox (StoryRanges), not main doc.Tables."""
    # 5 = wdTextFrameStory
    try:
        story = doc.StoryRanges(5)
        if story.Tables.Count >= 1:
            return story.Tables(1)
    except Exception:
        pass
    for i in range(1, doc.Shapes.Count + 1):
        try:
            shape = doc.Shapes(i)
            if not shape.TextFrame.HasText:
                continue
            tables = shape.TextFrame.TextRange.Tables
            if tables.Count >= 1:
                return tables(1)
        except Exception:
            continue
    return None


def _fill_ignitai(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = (
        data.bank or "",
        data.person_name or "",
        data.iban or "",
        data.branch_code or "",
    )
    total = _money(data.total_amount, cents=False)
    if inv:
        _replace_all(doc, "2024-003", inv)
    _replace_all(doc, "March 14, 2025", _short_date(invoice_date))
    # Match original two-line bank block (soft break before Branch Code only).
    replaced = _replace_all(
        doc,
        "Bank Name: Account Name: Account No:^lBranch Code:",
        f"Bank Name: {bank} Account Name: {name} Account No: {iban}^lBranch Code: {branch}",
    )
    if not replaced:
        _replace_all(
            doc,
            "Bank Name: Account Name: Account No:",
            f"Bank Name: {bank} Account Name: {name} Account No: {iban}",
        )
        # Only fill bare "Branch Code:" if still empty (avoid double prefix).
        _replace_all(doc, "Branch Code:", f"Branch Code: {branch}")

    table = _ignitai_item_table(doc)
    tasks = list(data.tasks[:3]) if data.tasks else []
    if table is not None:
        for i, row_1 in enumerate((3, 4, 5)):
            if i >= len(tasks) or row_1 > table.Rows.Count:
                break
            _set_cell_text(table, row_1, 1, tasks[i].sub_task)
            _set_cell_text(table, row_1, 4, _money(tasks[i].amount))
        if table.Rows.Count >= 6:
            try:
                table.Rows(6).Delete()
            except Exception:
                _set_cell_text(table, 6, 1, " ")
                _set_cell_text(table, 6, 4, " ")
        # Drop leftover empty spacer rows above the total
        for _ in range(3):
            if table.Rows.Count <= 5:
                break
            ri = table.Rows.Count - 1  # row above last
            try:
                label = ""
                try:
                    label += table.Cell(ri, 3).Range.Text
                except Exception:
                    pass
                try:
                    label += table.Cell(ri, 1).Range.Text
                except Exception:
                    pass
                if "Total Amount" in label:
                    break
                clean = label.replace("\r", "").replace("\x07", "").strip()
                if not clean:
                    table.Rows(ri).Delete()
                else:
                    break
            except Exception:
                break
        for ri in range(table.Rows.Count, 0, -1):
            try:
                label = table.Cell(ri, 3).Range.Text
            except Exception:
                continue
            if "Total Amount Due" in label:
                try:
                    _set_cell_text(table, ri, 4, total)
                except Exception:
                    pass
                break
    _replace_all(doc, "$30,000", total)
    try:
        story = doc.StoryRanges(5)
        story.Find.Execute(
            FindText="$30,000",
            ReplaceWith=total,
            Replace=2,
            Wrap=1,
            MatchWildcards=False,
        )
    except Exception:
        pass

    # If thank-you spilled to page 2, tighten empty paras above it.
    try:
        if int(doc.ComputeStatistics(2)) > 1:
            for i in range(doc.Paragraphs.Count, 0, -1):
                if "Thank you" not in doc.Paragraphs(i).Range.Text:
                    continue
                j = i - 1
                while j >= 1:
                    pt = (
                        doc.Paragraphs(j)
                        .Range.Text.replace("\r", "")
                        .replace("\x07", "")
                        .replace("\x0c", "")
                        .replace("\x0e", "")
                        .strip()
                    )
                    if pt:
                        break
                    doc.Paragraphs(j).Range.Delete()
                    j -= 1
                break
    except Exception:
        pass


def _fill_coretechify(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(doc, "INVOICE NO. 000001", f"INVOICE NO. {inv}")
        _replace_all(doc, "000001", inv)
    _replace_all(doc, "September 15, 2030", _full_date(invoice_date))
    # Soft breaks; labels use "Account No:" (not NO)
    _replace_all(
        doc,
        "Bank Name ^lAccount Name ^lAccount No:^lBranch Code",
        f"Bank Name: {bank}^lAccount Name: {name}^lAccount No: {iban}^lBranch Code: {branch}",
    )
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [6, 5])
    _fill_three_service_rows(
        doc,
        data,
        sample_names=["Business Development", "Web Development", "Consultation"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    _replace_all(doc, "$95.00", total)


def _fill_ecomify(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(doc, "1 2 3 4 / 5 6 7 8 9", inv)
    _replace_all(doc, "0 1 / 0 2 / 2 0 2 3", _short_date(invoice_date))
    _replace_all(
        doc,
        "Bank Name^lAccount Name:^lAccount No:",
        f"Bank Name: {bank}^lAccount Name: {name}^lAccount No: {iban}",
    )
    _replace_all(doc, "Branch Code: ", f"Branch Code: {branch} ")
    # Fill first 3 line rows in table 2 (1-based table index 2); delete extras
    if doc.Tables.Count >= 2:
        table = doc.Tables(2)
        tasks = list(data.tasks[:3]) if data.tasks else []
        for i, row_1 in enumerate((1, 2, 3)):
            if i >= len(tasks) or row_1 > table.Rows.Count:
                break
            if table.Columns.Count >= 2:
                _set_cell_text(table, row_1, 2, tasks[i].sub_task)
            if table.Columns.Count >= 5:
                _set_cell_text(table, row_1, 5, _money(tasks[i].amount))
        _delete_table_rows(table, [7, 6, 5, 4])
    if doc.Tables.Count >= 3:
        summary = doc.Tables(3)
        if summary.Rows.Count >= 1:
            _set_cell_text(summary, 1, summary.Columns.Count, total)
        if summary.Rows.Count >= 2:
            _set_cell_text(summary, 2, summary.Columns.Count, "$0")
        if summary.Rows.Count >= 3:
            _set_cell_text(summary, 3, summary.Columns.Count, "$0")
        if summary.Rows.Count >= 4:
            _set_cell_text(summary, 4, summary.Columns.Count, total)


def _fill_cozy(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [7, 6, 5])
    _replace_all(
        doc,
        "Bank Name^lAccount Name: Daniel Gallego Account No.: 0123 4567 8901^lBranch Code: ",
        f"Bank Name: {bank}^lAccount Name: {name} Account No.: {iban}^lBranch Code: {branch} ",
    )
    _replace_all(doc, "Account Name: Daniel Gallego", f"Account Name: {name}")
    _replace_all(doc, "Daniel Gallego", name)
    _replace_all(doc, "Account No.: 0123 4567 8901", f"Account No.: {iban}")
    _replace_all(doc, "0123 4567 8901", iban)
    _replace_all(doc, "Bank Name", f"Bank Name: {bank}")
    _replace_all(doc, "Branch Code: ", f"Branch Code: {branch} ")
    names = [
        "Property Valuation & Pricing Strategy",
        "Professional Photography",
        "Online Advertising + Social Media Ads",
    ]
    _fill_three_service_rows(
        doc, data, sample_names=names, sample_amounts=["$220", "$300", "$430"], cents=False
    )
    _replace_all(doc, "$2244", total)
    _replace_all(doc, "   $2244", f"   {total}")


def _fill_beecodify(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(doc, "NO. 000001", f"NO. {inv}")
    _replace_all(doc, "September 15, 2030", _full_date(invoice_date))
    _replace_all(
        doc,
        "Bank Name^lAccount Name ^lAccount NO ^lBranch Code",
        f"Bank Name: {bank}^lAccount Name: {name}^lAccount NO: {iban}^lBranch Code: {branch}",
    )
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [6, 5])
    _fill_three_service_rows(
        doc,
        data,
        sample_names=["Business Development", "Web Development", "Consultation"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    _replace_all(doc, "$95.00", total)


def _fill_bravix(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(doc, "01234", inv)
    _replace_all(doc, "11.03.2030", _short_date(invoice_date))
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [6, 5])
    _fill_three_service_rows(
        doc,
        data,
        sample_names=["Business Development", "Web Development", "Consultation"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    # After deletes: header + 3 items + total row (was row 7 → now row 5)
    if doc.Tables.Count >= 1:
        table = doc.Tables(1)
        total_row = table.Rows.Count
        if total_row >= 1:
            cols = table.Columns.Count
            _set_cell_text(table, total_row, cols, total)
            if cols >= 5:
                _set_cell_text(table, total_row, 5, total)
            _set_cell_text(
                table,
                total_row,
                1,
                f"Account Name: {name} Bank Name: {bank} Account No: {iban} Branch Code: {branch}",
            )
    _replace_all(doc, "$95.00", total)


def _fill_alpha(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(doc, "52131", inv)
    _replace_all(doc, "28/ 07 / 2095", _short_date(invoice_date))
    _replace_all(doc, "Account Name: Daniel Gallego Account No.: 0123 4567 8901 Branch Code",
                 f"Account Name: {name} Account No.: {iban} Branch Code: {branch}")
    _replace_all(doc, "Daniel Gallego", name)
    _replace_all(doc, "0123 4567 8901", iban)
    _replace_all(doc, "Bank Name: ", f"Bank Name: {bank} ")
    _replace_all(doc, "$285", total)
    _replace_all(doc, "Total\t$285", f"Total\t{total}")
    if doc.Tables.Count >= 2:
        table = doc.Tables(2)
        tasks = list(data.tasks[:3]) if data.tasks else []
        for i, row_1 in enumerate((2, 3, 4)):
            if i >= len(tasks) or row_1 > table.Rows.Count:
                break
            _set_cell_text(table, row_1, 1, tasks[i].sub_task)
            _set_cell_text(table, row_1, table.Columns.Count, _money(tasks[i].amount))


def _fill_synergo(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(doc, "150305", inv)
    _replace_all(doc, "March 15, 2025", _full_date(invoice_date))
    _replace_all(doc, "Bank Name:", f"Bank Name: {bank}")
    _replace_all(doc, "Account Name:", f"Account Name: {name}")
    _replace_all(doc, "Account No:", f"Account No: {iban}")
    _replace_all(doc, "Branch Code:", f"Branch Code: {branch}")
    # Person name sample "Ruby"
    _replace_all(doc, "Ruby", name)
    if data.tasks and len(data.tasks) >= 3 and doc.Tables.Count >= 1:
        table = doc.Tables(1)
        for task, row in zip(data.tasks[:3], (2, 5, 7)):
            if row <= table.Rows.Count:
                _set_cell_text(table, row, 1, task.sub_task)
        for task, row in zip(data.tasks[:3], (3, 6, 8)):
            if row <= table.Rows.Count and table.Columns.Count >= 4:
                _set_cell_text(table, row, 4, _money(task.amount))
    _replace_all(doc, "$0,000.00", total)
    if doc.Tables.Count >= 2:
        _set_cell_text(doc.Tables(2), 1, doc.Tables(2).Columns.Count, total)


def _com_fill_document(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    fillers = {
        6: _fill_ravotek,
        7: _fill_ignitai,
        8: _fill_coretechify,
        9: _fill_ecomify,
        10: _fill_cozy,
        11: _fill_beecodify,
        12: _fill_bravix,
        13: _fill_alpha,
        14: _fill_synergo,
    }
    filler = fillers.get(data.invoice_number)
    if filler is None:
        raise ValidationError(
            f"Word COM fill is not configured for invoice template {data.invoice_number}."
        )
    filler(doc, data, invoice_date)


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
