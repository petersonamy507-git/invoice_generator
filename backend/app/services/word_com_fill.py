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


def _story_ranges(doc):
    """Yield main + textbox/header stories (invoice NO often lives in text frames)."""
    seen: set[int] = set()
    for story_id in range(1, 12):  # wdMainTextStory … wdTextFrameStory, etc.
        try:
            story = doc.StoryRanges(story_id)
        except Exception:
            continue
        while story is not None:
            try:
                key = int(story.Start) ^ (int(story.End) << 16) ^ story_id
            except Exception:
                key = id(story)
            if key in seen:
                break
            seen.add(key)
            yield story
            try:
                story = story.NextStoryRange
            except Exception:
                break


def _replace(doc, find_text: str, replace_text: str, *, replace_all: bool = True) -> int:
    if not find_text:
        return 0
    repl = replace_text if len(replace_text) <= 255 else replace_text[:255]
    hits = 0
    for story in _story_ranges(doc):
        try:
            ok = story.Find.Execute(
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
        except Exception:
            continue
        if ok:
            hits += 1
            if not replace_all:
                return hits
    return hits


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


def _set_cell_plain(table, row_1based: int, col_1based: int, text: str) -> None:
    """Replace entire cell body (all paragraphs), keeping the end-of-cell mark."""
    cell = table.Cell(row_1based, col_1based)
    rng = cell.Range.Duplicate
    rng.MoveEnd(1, -1)
    rng.Text = text if text != "" else " "


def _fill_empty_label(doc, label: str, value: str) -> None:
    """Fill 'Label' / 'Label:' once without Word Find re-matching the result."""
    if not value:
        return
    # Prefer already-colon forms with trailing space (empty value).
    for find in (f"{label}:  ", f"{label}: ", f"{label} ", label):
        if find.endswith(": ") or find.endswith(":  "):
            repl = f"{label}: {value}" + ("  " if find.endswith(":  ") else " ")
        elif find.endswith(" "):
            repl = f"{label}: {value} "
        else:
            repl = f"{label}: {value}"
        if _replace_one(doc, find, repl):
            return


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


def _ravotek_date(invoice_date: date | None) -> str:
    """Real Ravotek date style: '11 . 02 . 2030' (DD . MM . YYYY)."""
    d = invoice_date or date.today()
    return f"{d.day:02d} . {d.month:02d} . {d.year}"


def _fill_ravotek(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    # Invoice06 — 6 sample rows; keep 3, delete 4–6.
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(doc, "01234", inv)
    _replace_all(doc, "11 . 02 . 2030", _ravotek_date(invoice_date))
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [7, 6, 5])  # rows 5–7 were sample 4–6 (1=header)
    _replace_all(doc, "Account Name: Daniel Gallego", f"Account Name: {name}")
    _replace_all(doc, "Daniel Gallego", name)
    _fill_empty_label(doc, "Bank Name", bank)
    _replace_one(doc, "Account No.:", f"Account No.: {iban}")
    _fill_empty_label(doc, "Branch Code", branch)
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
    # Real format: "Invoice:     000" (not "Invoice Number:" / "2024-003").
    if inv:
        if not _replace_all(doc, "Invoice:     000", f"Invoice:     {inv}"):
            if not _replace_all(doc, "   Invoice:     000", f"   Invoice:     {inv}"):
                _replace_all(doc, "2024-003", inv)
    # Real template uses full month style: "March 14, 2025"
    _replace_all(doc, "March 14, 2025", _full_date(invoice_date))
    # Real PDF stacks four bank lines; keep each label on its own soft-break line.
    bank_block = (
        f"Bank Name: {bank}^l"
        f"Account Name: {name}^l"
        f"Account No: {iban}^l"
        f"Branch Code: {branch}"
    )
    replaced = _replace_all(
        doc,
        "Bank Name: Account Name: Account No:^lBranch Code:",
        bank_block,
    )
    if not replaced:
        replaced = _replace_all(
            doc,
            "Bank Name: Account Name: Account No:",
            f"Bank Name: {bank}^lAccount Name: {name}^lAccount No: {iban}",
        )
        if replaced:
            _replace_one(doc, "Branch Code:", f"Branch Code: {branch}")
        else:
            _fill_empty_label(doc, "Bank Name", bank)
            _fill_empty_label(doc, "Account Name", name)
            _replace_one(doc, "Account No:", f"Account No: {iban}")
            _fill_empty_label(doc, "Branch Code", branch)

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
    # Soft breaks between Payable/From bank lines (preserve stacked layout).
    replaced = _replace_all(
        doc,
        "Bank Name ^lAccount Name ^lAccount No:^l^lBranch Code",
        f"Bank Name: {bank}^lAccount Name: {name}^lAccount No: {iban}^l^lBranch Code: {branch}",
    )
    if not replaced:
        replaced = _replace_all(
            doc,
            "Bank Name ^lAccount Name ^lAccount No:^lBranch Code",
            f"Bank Name: {bank}^lAccount Name: {name}^lAccount No: {iban}^lBranch Code: {branch}",
        )
    if not replaced:
        _fill_empty_label(doc, "Bank Name", bank)
        _fill_empty_label(doc, "Account Name", name)
        _replace_one(doc, "Account No:", f"Account No: {iban}")
        _fill_empty_label(doc, "Branch Code", branch)
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [6, 5])
    _fill_three_service_rows(
        doc,
        data,
        # Top-to-bottom order must match sample_amounts / table rows.
        sample_names=["Consultation", "Web Development", "Business Development"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    _replace_all(doc, "$95.00", total)


def _ecomify_spaced(text: str) -> str:
    """Ecomify template letter-spaces values (e.g. 0 1 / 0 2 / 2 0 2 3)."""
    return " ".join(text)


def _ecomify_date(invoice_date: date | None) -> str:
    """Match real template date cell: spaced DD/MM/YYYY."""
    d = invoice_date or date.today()
    return _ecomify_spaced(f"{d.day:02d}/{d.month:02d}/{d.year}")


def _ecomify_money(amount: int) -> str:
    """Match real amount cells: $ 1 5 0 0."""
    return _ecomify_spaced(f"${int(amount)}")


def _clear_table_row_com(table, row_1based: int) -> None:
    if row_1based < 1 or row_1based > table.Rows.Count:
        return
    for col in range(1, table.Columns.Count + 1):
        try:
            _set_cell_text(table, row_1based, col, " ")
        except Exception:
            pass


def _fill_ecomify(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _ecomify_money(data.total_amount)
    zero = _ecomify_spaced("$0")
    if inv:
        _replace_all(doc, "1 2 3 4 / 5 6 7 8 9", _ecomify_spaced(inv))
    _replace_all(doc, "0 1 / 0 2 / 2 0 2 3", _ecomify_date(invoice_date))
    replaced = _replace_all(
        doc,
        "Bank Name^lAccount Name:^lAccount No:",
        f"Bank Name: {bank}^lAccount Name: {name}^lAccount No: {iban}",
    )
    if not replaced:
        _fill_empty_label(doc, "Bank Name", bank)
        _replace_one(doc, "Account Name:", f"Account Name: {name}")
        _replace_one(doc, "Account No:", f"Account No: {iban}")
    _replace_one(doc, "Branch Code: ", f"Branch Code: {branch} ")
    # Keep full 7-row grid (real format); fill 3 tasks, clear leftover sample rows.
    if doc.Tables.Count >= 2:
        table = doc.Tables(2)
        tasks = list(data.tasks[:3]) if data.tasks else []
        for i, row_1 in enumerate((1, 2, 3)):
            if i >= len(tasks) or row_1 > table.Rows.Count:
                break
            if table.Columns.Count >= 2:
                _set_cell_text(table, row_1, 2, tasks[i].sub_task)
            if table.Columns.Count >= 5:
                _set_cell_text(table, row_1, 5, _ecomify_money(tasks[i].amount))
        for row_1 in range(len(tasks) + 1, table.Rows.Count + 1):
            _clear_table_row_com(table, row_1)
    if doc.Tables.Count >= 3:
        summary = doc.Tables(3)
        if summary.Rows.Count >= 1:
            _set_cell_text(summary, 1, summary.Columns.Count, total)
        if summary.Rows.Count >= 2:
            _set_cell_text(summary, 2, summary.Columns.Count, zero)
        if summary.Rows.Count >= 3:
            _set_cell_text(summary, 3, summary.Columns.Count, zero)
        if summary.Rows.Count >= 4:
            _set_cell_text(summary, 4, summary.Columns.Count, total)


def _fill_cozy(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(doc, "01234", inv)
    _replace_all(doc, "11 . 02 . 2030", _short_date(invoice_date))
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [7, 6, 5])
    replaced = _replace_all(
        doc,
        "Bank Name^lAccount Name: Daniel Gallego Account No.: 0123 4567 8901^lBranch Code: ",
        f"Bank Name: {bank}^lAccount Name: {name} Account No.: {iban}^lBranch Code: {branch} ",
    )
    if not replaced:
        _replace_all(doc, "Account Name: Daniel Gallego", f"Account Name: {name}")
        _replace_all(doc, "Daniel Gallego", name)
        _replace_all(doc, "Account No.: 0123 4567 8901", f"Account No.: {iban}")
        _replace_all(doc, "0123 4567 8901", iban)
        _fill_empty_label(doc, "Bank Name", bank)
        _fill_empty_label(doc, "Branch Code", branch)
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


def _dynamo_slash_date(invoice_date: date | None) -> str:
    """Header date style: 18 / 04 / 2025."""
    d = invoice_date or date.today()
    return f"{d.day:02d} / {d.month:02d} / {d.year}"


def _dynamo_pay_by_date(invoice_date: date | None) -> str:
    """Pay by style: 18 April 2025."""
    d = invoice_date or date.today()
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _fill_dynamo(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    """Invoice05 — real Dynamo Creatives layout (Bank Name / Account Name / Account No)."""
    inv = data.document_invoice_no or "DV-001"
    bank, name, iban = data.bank or "", data.person_name or "", data.iban or ""
    total = _money(data.total_amount)
    slash = _dynamo_slash_date(invoice_date)
    # Soft-break keeps Invoice# above Date in the narrow right column (avoids wrap bleed).
    if not _replace_all(doc, "DV-001 18 / 04 / 2025", f"{inv}^l{slash}"):
        if inv and inv != "DV-001":
            _replace_all(doc, "DV-001", inv)
        _replace_all(doc, "18 / 04 / 2025", slash)
    if len(inv) > 6:
        # Squeeze longer IDs so they stay on one line under Invoice#.
        for story in _story_ranges(doc):
            try:
                found = story.Find.Execute(
                    FindText=inv,
                    MatchCase=True,
                    MatchWholeWord=False,
                    Forward=True,
                    Wrap=0,
                )
            except Exception:
                continue
            if found:
                try:
                    story.Font.Spacing = -1.0
                    story.Font.Scaling = 80
                except Exception:
                    pass
                break
    _replace_all(doc, "18 April 2025", _dynamo_pay_by_date(invoice_date))
    # Real PDF stacks Bank Name then Account Name; keep soft-break between them.
    replaced = _replace_all(
        doc,
        "Bank Name:Faisal Bank Account Name:Dynaverse",
        f"Bank Name: {bank}^lAccount Name: {name}",
    )
    if not replaced:
        replaced = _replace_all(
            doc,
            "Bank Name:Faisal Bank Account Name:Dynaverse",
            f"Bank Name: {bank} Account Name: {name}",
        )
    if not replaced:
        _replace_all(doc, "Faisal Bank", bank)
        _replace_all(doc, "Dynaverse", name)
    if not _replace_all(
        doc,
        "Account  No.:  PK52FAYS3059301000006776",
        f"Account  No.:  {iban}",
    ):
        _replace_all(doc, "PK52FAYS3059301000006776", iban)
    _fill_three_service_rows(
        doc,
        data,
        sample_names=[
            "Social Media Marketing Services",
            "Content Writing",
            "Website Development",
        ],
        sample_amounts=["$4,000", "$3,500", "$2,500"],
        cents=False,
    )
    _replace_all(doc, "$10,000", total)
    _replace_all(doc, "Total$10,000", f"Total{total}")


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
        sample_names=["Consultation", "Web Development", "Business Development"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    _replace_all(doc, "$95.00", total)


def _bravix_date(invoice_date: date | None) -> str:
    """Bravix template uses DD.MM.YYYY (e.g. 11.03.2030)."""
    d = invoice_date or date.today()
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _fill_bravix_payment_lines(table, total_row: int, name: str, bank: str, iban: str, branch: str) -> None:
    """Keep real layout: four stacked lines in the payment cell (not one wrapped line)."""
    cell = table.Cell(total_row, 1)
    filled = {
        "account name": f"Account Name: {name}",
        "bank name": f"Bank Name: {bank}",
        "account no": f"Account No: {iban}",
        "branch code": f"Branch Code: {branch}",
    }
    for i in range(1, cell.Range.Paragraphs.Count + 1):
        para = cell.Range.Paragraphs(i)
        rng = para.Range.Duplicate
        rng.MoveEnd(1, -1)
        raw = rng.Text.replace("\r", "").replace("\x07", "").strip()
        if not raw:
            continue
        key = raw.lower().rstrip(":").strip()
        for label, text in filled.items():
            if key == label or key.startswith(label):
                rng.Text = text
                break


def _fill_bravix(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(doc, "01234", inv)
    _replace_all(doc, "11.03.2030", _bravix_date(invoice_date))
    if doc.Tables.Count >= 1:
        _delete_table_rows(doc.Tables(1), [6, 5])
    _fill_three_service_rows(
        doc,
        data,
        sample_names=["Consultation", "Web Development", "Business Development"],
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
            _fill_bravix_payment_lines(table, total_row, name, bank, iban, branch)
    _replace_all(doc, "$95.00", total)


def _alpha_date(invoice_date: date | None) -> str:
    """Alpha template date cell: 28/ 07 / 2095 → DD/ MM / YYYY."""
    d = invoice_date or date.today()
    return f"{d.day:02d}/ {d.month:02d} / {d.year}"


def _fill_alpha(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(doc, "52131", inv)
    _replace_all(doc, "28/ 07 / 2095", _alpha_date(invoice_date))
    # Real PDF stacks payment lines; keep Account/No/Branch on soft-break lines.
    _replace_one(doc, "Bank Name: ", f"Bank Name: {bank} ")
    replaced = _replace_all(
        doc,
        "Account Name: Daniel Gallego Account No.: 0123 4567 8901 Branch Code",
        f"Account Name: {name}^lAccount No.: {iban}^lBranch Code: {branch}",
    )
    if not replaced:
        _replace_all(doc, "Daniel Gallego", name)
        _replace_all(doc, "0123 4567 8901", iban)
        _replace_one(doc, "Branch Code", f"Branch Code: {branch}")
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


def _synergo_slash_date(invoice_date: date | None) -> str:
    """Invoice date style: '01 / 02 / 2023'."""
    d = invoice_date or date.today()
    return f"{d.day:02d} / {d.month:02d} / {d.year}"


def _synergo_pay_by_date(invoice_date: date | None) -> str:
    """Pay by style: '23 June 2023'."""
    d = invoice_date or date.today()
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _synergo_total_font_pt(total: str) -> float:
    """Point size so Total + amount stay on one line in the narrow right column."""
    n = len(total)
    if n <= 5:
        return 18.0
    if n <= 7:
        return 14.0
    if n <= 9:
        return 11.0
    return 9.0


def _fill_synergo(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    """Invoice14 — Synergo Incdocx (Invoice to / qty-price table / PAYMENT METHOD)."""
    inv = data.document_invoice_no or ""
    bank, name, iban = data.bank or "", data.person_name or "", data.iban or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(doc, "52131", inv)
    _replace_all(doc, "01 / 02 / 2023", _synergo_slash_date(invoice_date))
    _replace_all(doc, "23 June 2023", _synergo_pay_by_date(invoice_date))
    _replace_all(doc, "Rimberio Bank", bank)
    # Soft-break so Account Name / Account No. match original PDF line layout.
    if not _replace_all(
        doc,
        "Account Name: Alfredo Torres Account No.: 0123 4567 8901",
        f"Account Name: {name}^lAccount No.: {iban}",
    ):
        _replace_all(doc, "Alfredo Torres", name)
        _replace_all(doc, "0123 4567 8901", iban)
    tasks = list(data.tasks[:3]) if data.tasks else []
    if tasks and doc.Tables.Count >= 2:
        table = doc.Tables(2)
        for i, task in enumerate(tasks):
            row = i + 2
            if row > table.Rows.Count:
                break
            amt = _money(task.amount)
            _set_cell_text(table, row, 1, task.sub_task)
            if table.Columns.Count >= 2:
                _set_cell_text(table, row, 2, "1")
            if table.Columns.Count >= 3:
                _set_cell_text(table, row, 3, amt)
            if table.Columns.Count >= 4:
                _set_cell_text(table, row, 4, amt)
        # Subtotal is the last row of the items table.
        try:
            last = table.Rows.Count
            _set_cell_text(table, last, table.Columns.Count, total)
        except Exception:
            pass
    else:
        _fill_three_service_rows(
            doc,
            data,
            sample_names=[
                "A4 Paper (75gr/m2)",
                "Pencil (12ea/box)",
                "Ruler",
            ],
            sample_amounts=["$200", "$75", "$10"],
            cents=False,
        )
    sample_total = "$" + "285"
    _replace_all(doc, sample_total, total)
    # Total paragraph: label + tab + amount on one line (match original).
    for i in range(1, doc.Paragraphs.Count + 1):
        para = doc.Paragraphs(i)
        raw = para.Range.Text.replace("\r", "").replace("\x07", "")
        if raw.strip().lower().startswith("total") and (
            sample_total in raw or total in raw or "$" in raw
        ):
            rng = para.Range.Duplicate
            rng.MoveEnd(1, -1)
            rng.Text = f"Total\t{total}"
            try:
                rng.Font.Bold = True
                rng.Font.Size = _synergo_total_font_pt(total)
            except Exception:
                pass
            break


def _com_fill_document(doc, data: WordInvoiceData, invoice_date: date | None) -> None:
    fillers = {
        5: _fill_dynamo,
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
