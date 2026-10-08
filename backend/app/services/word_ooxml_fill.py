"""Fill Word templates on Linux/AWS by editing OOXML in the .docx zip.

Preserves DrawingML (Beecodify header bars, etc.) that python-docx save strips.
Used when Microsoft Word COM is not available.
"""
from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from lxml import etree

from backend.app.models import WordInvoiceData
from backend.app.services.validation import ValidationError
from backend.app.services.word_date_updater import format_invoice_date
from backend.app.services.word_field_updater import format_amount
from backend.app.services.word_templates import ensure_template_exists

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
NSMAP = {"w": W_NS}


def _q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _money(amount: int, *, cents: bool = False) -> str:
    return format_amount(amount, cents=cents)


def _full_date(invoice_date: date | None) -> str:
    d = invoice_date or date.today()
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _short_date(invoice_date: date | None) -> str:
    return format_invoice_date(invoice_date)


def _para_text(p: etree._Element) -> str:
    return "".join(t.text or "" for t in p.iter(_q("t")))


def _set_text_node(t: etree._Element, new_text: str) -> None:
    t.text = new_text
    if new_text[:1].isspace() or new_text[-1:].isspace():
        t.set(XML_SPACE, "preserve")
    elif XML_SPACE in t.attrib and not (new_text[:1].isspace() or new_text[-1:].isspace()):
        # keep preserve if still useful; harmless either way
        pass


def _set_para_text(p: etree._Element, new_text: str) -> None:
    texts = list(p.iter(_q("t")))
    if not texts:
        r = etree.SubElement(p, _q("r"))
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, new_text)
        return
    _set_text_node(texts[0], new_text)
    for t in texts[1:]:
        t.text = ""


def _line_segments(p: etree._Element) -> list[list[etree._Element]]:
    """Group w:t nodes by soft-break lines so replaces never collapse w:br."""
    segments: list[list[etree._Element]] = []
    current: list[etree._Element] = []
    for node in p.iter():
        if node.tag == _q("t"):
            current.append(node)
        elif node.tag == _q("br"):
            segments.append(current)
            current = []
    segments.append(current)
    return segments


def _set_segment_text(texts: list[etree._Element], new_text: str) -> None:
    if not texts:
        return
    _set_text_node(texts[0], new_text)
    for t in texts[1:]:
        t.text = ""


def _replace_in_text_nodes(
    root: etree._Element, old: str, new: str, *, replace_all: bool = True
) -> int:
    """Replace inside individual w:t nodes (keeps soft-breaks / run layout)."""
    if not old:
        return 0
    count = 0
    for t in root.iter(_q("t")):
        cur = t.text or ""
        if old not in cur:
            continue
        if replace_all:
            t.text = cur.replace(old, new)
            count += cur.count(old)
        else:
            t.text = cur.replace(old, new, 1)
            count += 1
            return count
        if t.text and (t.text[:1].isspace() or t.text[-1:].isspace()):
            t.set(XML_SPACE, "preserve")
    return count


def _replace_in_tree(
    root: etree._Element, old: str, new: str, *, replace_all: bool = True
) -> int:
    """Replace text split across runs without destroying soft-breaks (w:br)."""
    if not old:
        return 0
    hit = _replace_in_text_nodes(root, old, new, replace_all=replace_all)
    if hit:
        return hit
    count = 0
    for p in root.iter(_q("p")):
        for segment in _line_segments(p):
            if not segment:
                continue
            full = "".join(t.text or "" for t in segment)
            if old not in full:
                continue
            if replace_all:
                updated = full.replace(old, new)
                n = full.count(old)
            else:
                updated = full.replace(old, new, 1)
                n = 1
            if updated != full:
                _set_segment_text(segment, updated)
                count += n
                if not replace_all:
                    return count
    return count


def _replace_all(root: etree._Element, old: str, new: str) -> int:
    return _replace_in_tree(root, old, new, replace_all=True)


def _replace_one(root: etree._Element, old: str, new: str) -> int:
    return _replace_in_tree(root, old, new, replace_all=False)


def _fill_label(root: etree._Element, label: str, value: str) -> None:
    """Set 'Label: value' on a single w:t node (never collapse a whole paragraph)."""
    filled = f"{label}: {value}"
    for t in root.iter(_q("t")):
        cur = t.text or ""
        if value and value in cur and label in cur:
            return
        if cur.strip() == label or cur.rstrip() == label:
            suffix = " " if cur.endswith(" ") else ""
            _set_text_node(t, filled + suffix)
            # Clear orphaned ": " / ":" runs that followed a split label.
            nxt = t.getnext()
            # walk following runs' w:t in same paragraph
            parent_r = t.getparent()
            if parent_r is not None:
                para = parent_r.getparent()
                if para is not None:
                    seen = False
                    for rt in para.iter(_q("t")):
                        if rt is t:
                            seen = True
                            continue
                        if not seen:
                            continue
                        frag = (rt.text or "").strip()
                        if frag in (":", "") and (rt.text or "").strip(" ") in (":", ""):
                            if (rt.text or "").strip() == ":":
                                rt.text = ""
                            break
                        break
            return
        if cur.strip() == f"{label}:":
            _set_text_node(t, filled)
            return
        if cur.startswith(f"{label}:") and not (value and value in cur):
            # "Branch Code: " with trailing space / empty value
            _set_text_node(t, filled + (" " if cur.endswith(" ") else ""))
            return
    # Split label e.g. Beecodify "Account" + " NO"
    if label.upper().endswith(" NO") or label.upper().endswith(" NO."):
        for t in root.iter(_q("t")):
            cur = t.text or ""
            if cur.strip() in ("NO", "NO.") or cur.strip() in ("NO ",):
                _set_text_node(t, f" NO: {value}")
                return
            if cur == " NO" or cur.startswith(" NO"):
                _set_text_node(t, f" NO: {value}")
                return


def _tables(root: etree._Element) -> list[etree._Element]:
    return list(root.iter(_q("tbl")))


def _table_blob(tbl: etree._Element) -> str:
    return "".join(_para_text(p) for p in tbl.iter(_q("p")))


def _tables_matching(root: etree._Element, *needles: str) -> list[etree._Element]:
    out: list[etree._Element] = []
    for tbl in _tables(root):
        blob = _table_blob(tbl)
        if any(n in blob for n in needles):
            out.append(tbl)
    return out


def _table_rows(tbl: etree._Element) -> list[etree._Element]:
    return [c for c in tbl if c.tag == _q("tr")]


def _delete_rows(tbl: etree._Element, indexes_0based: list[int]) -> None:
    rows = _table_rows(tbl)
    for idx in sorted(indexes_0based, reverse=True):
        if 0 <= idx < len(rows):
            parent = rows[idx].getparent()
            if parent is not None:
                parent.remove(rows[idx])


def _trim_empty_rows_above_last(tbl: etree._Element, *, min_rows: int = 5) -> None:
    """Remove blank spacer rows immediately above the last (total) row."""
    rows = _table_rows(tbl)
    while len(rows) > min_rows:
        ri = len(rows) - 2
        text = "".join(_para_text(p) for p in rows[ri].iter(_q("p"))).strip()
        if text:
            break
        _delete_rows(tbl, [ri])
        rows = _table_rows(tbl)


def _set_cell_text(tbl: etree._Element, row_0: int, col_0: int, text: str) -> None:
    rows = _table_rows(tbl)
    if row_0 < 0 or row_0 >= len(rows):
        return
    cells = [c for c in rows[row_0] if c.tag == _q("tc")]
    if col_0 < 0 or col_0 >= len(cells):
        return
    cell = cells[col_0]
    paras = [p for p in cell.iter(_q("p"))]
    # Prefer last non-empty para (Beecodify has leading empty para)
    target = None
    for p in paras:
        if _para_text(p).strip():
            target = p
    if target is None:
        target = paras[-1] if paras else None
    if target is None:
        target = etree.SubElement(cell, _q("p"))
    _set_para_text(target, text if text != "" else " ")


def _fill_three_services(
    root: etree._Element,
    data: WordInvoiceData,
    *,
    sample_names: list[str],
    sample_amounts: list[str],
    cents: bool,
) -> None:
    """sample_names/amounts must be in top-to-bottom row order (task 0..2)."""
    tasks = list(data.tasks[:3]) if data.tasks else []
    # Longest labels first so "Consultation" does not hit "Business Consultation".
    for idx, sample in sorted(
        enumerate(sample_names), key=lambda x: len(x[1]), reverse=True
    ):
        if idx < len(tasks):
            _replace_in_text_nodes(root, sample, tasks[idx].sub_task, replace_all=True)
            # fallback if name split across runs
            if tasks[idx].sub_task not in "".join(
                _para_text(p) for p in root.iter(_q("p"))
            ) and not any(
                tasks[idx].sub_task in (t.text or "") for t in root.iter(_q("t"))
            ):
                _replace_all(root, sample, tasks[idx].sub_task)
    for i, sample_amt in enumerate(sample_amounts):
        if i < len(tasks):
            if not _replace_in_text_nodes(
                root, sample_amt, _money(tasks[i].amount, cents=cents), replace_all=False
            ):
                _replace_one(root, sample_amt, _money(tasks[i].amount, cents=cents))


def _fill_beecodify(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(root, "NO. 000001", f"NO. {inv}")
        _replace_all(root, "000001", inv)
    _replace_all(root, "September 15, 2030", _full_date(invoice_date))
    _fill_label(root, "Bank Name", bank)
    _fill_label(root, "Account Name", name)
    # "Account" + " NO" are separate runs in the Beecodify template
    _fill_label(root, "Account NO", iban)
    _fill_label(root, "Branch Code", branch)
    tables = _tables(root)
    if tables:
        # 0=header,1-5=services,6=total,7=note → drop service rows 4 & 5
        _delete_rows(tables[0], [5, 4])
    _fill_three_services(
        root,
        data,
        sample_names=["Consultation", "Web Development", "Business Development"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    _replace_in_text_nodes(root, "$95.00", total, replace_all=True)


def _fill_coretechify(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(root, "INVOICE NO. 000001", f"INVOICE NO. {inv}")
        _replace_all(root, "000001", inv)
    _replace_all(root, "September 15, 2030", _full_date(invoice_date))
    _fill_label(root, "Bank Name", bank)
    _fill_label(root, "Account Name", name)
    _fill_label(root, "Account No", iban)
    _fill_label(root, "Branch Code", branch)
    tables = _tables(root)
    if tables:
        _delete_rows(tables[0], [5, 4])
    _fill_three_services(
        root,
        data,
        sample_names=["Consultation", "Web Development", "Business Development"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    _replace_in_text_nodes(root, "$95.00", total, replace_all=True)


def _fill_bravix(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(root, "01234", inv)
    _replace_all(root, "11.03.2030", _short_date(invoice_date))
    tables = _tables(root)
    if tables:
        _delete_rows(tables[0], [5, 4])
    _fill_three_services(
        root,
        data,
        sample_names=["Consultation", "Web Development", "Business Development"],
        sample_amounts=["$5.00", "$30.00", "$5.00"],
        cents=True,
    )
    if tables:
        rows = _table_rows(tables[0])
        if rows:
            total_row = len(rows) - 1
            cells = [c for c in rows[total_row] if c.tag == _q("tc")]
            if cells:
                _set_cell_text(tables[0], total_row, 0, f"Account Name: {name} Bank Name: {bank} Account No: {iban} Branch Code: {branch}")
                _set_cell_text(tables[0], total_row, len(cells) - 1, total)
                if len(cells) >= 5:
                    _set_cell_text(tables[0], total_row, 4, total)
    _replace_all(root, "$95.00", total)


def _fill_ravotek(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    # Services live in the DESCRIPTION table (not the INVOICE NO header tables).
    for tbl in _tables_matching(root, "Property Valuation", "Professional Photography"):
        _delete_rows(tbl, [6, 5, 4])  # drop sample rows 4–6; keep header + 3 items
    # Keep soft-breaks: touch only matching runs / line segments.
    _replace_in_text_nodes(root, "Daniel Gallego", name)
    _fill_label(root, "Bank Name", bank)
    # "Account " + "No.:" then soft-break then "Branch Code: "
    if not _replace_in_text_nodes(root, "No.:", f"No.: {iban}", replace_all=False):
        _replace_one(root, "Account No.:", f"Account No.: {iban}")
    _fill_label(root, "Branch Code", branch)
    if branch and not any(
        branch in (t.text or "") for t in root.iter(_q("t"))
    ):
        _replace_one(root, "Branch Code: ", f"Branch Code: {branch} ")
        _replace_one(root, "Branch Code:", f"Branch Code: {branch}")
    _fill_three_services(
        root,
        data,
        sample_names=[
            "Property Valuation & Pricing Strategy",
            "Professional Photography",
            "Online Advertising + Social Media Ads",
        ],
        sample_amounts=["$220", "$300", "$430"],
        cents=False,
    )
    _replace_all(root, "$2024", total)
    for tbl in _tables_matching(root, "TOTAL"):
        rows = _table_rows(tbl)
        if len(rows) == 1 and "TOTAL" in _table_blob(tbl):
            cells = [c for c in rows[0] if c.tag == _q("tc")]
            if cells:
                _set_cell_text(tbl, 0, len(cells) - 1, total)
            break


def _fill_cozy(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    for tbl in _tables_matching(root, "Property Valuation", "Professional Photography"):
        _delete_rows(tbl, [6, 5, 4])  # drop sample rows 4–6
        # trailing empty spacer row (was index 7)
        rows = _table_rows(tbl)
        if len(rows) > 4:
            last = "".join(_para_text(p) for p in rows[-1].iter(_q("p"))).strip()
            if not last:
                _delete_rows(tbl, [len(rows) - 1])
    # Soft-break lines: Bank Name | Account Name… | Branch Code
    _fill_label(root, "Bank Name", bank)
    _replace_one(root, "Daniel Gallego", name)
    _replace_in_text_nodes(root, "0123 4567 8901", iban)
    _fill_label(root, "Branch Code", branch)
    _fill_three_services(
        root,
        data,
        sample_names=[
            "Property Valuation & Pricing Strategy",
            "Professional Photography",
            "Online Advertising + Social Media Ads",
        ],
        sample_amounts=["$220", "$300", "$430"],
        cents=False,
    )
    _replace_all(root, "$2244", total)


def _fill_ecomify(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(root, "1 2 3 4 / 5 6 7 8 9", inv)
    _replace_all(root, "0 1 / 0 2 / 2 0 2 3", _short_date(invoice_date))
    _replace_all(root, "Bank Name", f"Bank Name: {bank}")
    _replace_all(root, "Account Name:", f"Account Name: {name}")
    _replace_all(root, "Account No:", f"Account No: {iban}")
    _replace_all(root, "Branch Code: ", f"Branch Code: {branch} ")
    tables = _tables(root)
    if len(tables) >= 2:
        tbl = tables[1]
        tasks = list(data.tasks[:3]) if data.tasks else []
        for i in range(min(3, len(tasks))):
            _set_cell_text(tbl, i, 1, tasks[i].sub_task)
            cells = [c for c in _table_rows(tbl)[i] if c.tag == _q("tc")]
            if len(cells) >= 5:
                _set_cell_text(tbl, i, 4, _money(tasks[i].amount))
        _delete_rows(tbl, [6, 5, 4, 3])
    if len(tables) >= 3:
        summary = tables[2]
        rows = _table_rows(summary)
        for ri, val in ((0, total), (1, "$0"), (2, "$0"), (3, total)):
            if ri < len(rows):
                cells = [c for c in rows[ri] if c.tag == _q("tc")]
                if cells:
                    _set_cell_text(summary, ri, len(cells) - 1, val)


def _fill_alpha(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(root, "52131", inv)
    _replace_all(root, "28/ 07 / 2095", _short_date(invoice_date))
    _replace_all(
        root,
        "Account Name: Daniel Gallego Account No.: 0123 4567 8901 Branch Code",
        f"Account Name: {name} Account No.: {iban} Branch Code: {branch}",
    )
    _replace_all(root, "Daniel Gallego", name)
    _replace_all(root, "0123 4567 8901", iban)
    _replace_all(root, "Bank Name: ", f"Bank Name: {bank} ")
    _replace_all(root, "$285", total)
    tables = _tables(root)
    if len(tables) >= 2:
        tbl = tables[1]
        tasks = list(data.tasks[:3]) if data.tasks else []
        for i, row in enumerate((1, 2, 3)):
            if i >= len(tasks):
                break
            _set_cell_text(tbl, row, 0, tasks[i].sub_task)
            cells = [c for c in _table_rows(tbl)[row] if c.tag == _q("tc")]
            if cells:
                _set_cell_text(tbl, row, len(cells) - 1, _money(tasks[i].amount))


def _fill_synergo(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(root, "150305", inv)
    _replace_all(root, "March 15, 2025", _full_date(invoice_date))
    _replace_all(root, "Bank Name:", f"Bank Name: {bank}")
    _replace_all(root, "Account Name:", f"Account Name: {name}")
    _replace_all(root, "Account No:", f"Account No: {iban}")
    _replace_all(root, "Branch Code:", f"Branch Code: {branch}")
    _replace_all(root, "Ruby", name)
    tables = _tables(root)
    if tables and data.tasks and len(data.tasks) >= 3:
        tbl = tables[0]
        for task, row in zip(data.tasks[:3], (1, 4, 6)):
            _set_cell_text(tbl, row, 0, task.sub_task)
        for task, row in zip(data.tasks[:3], (2, 5, 7)):
            cells = [c for c in _table_rows(tbl)[row] if c.tag == _q("tc")]
            if len(cells) >= 4:
                _set_cell_text(tbl, row, 3, _money(task.amount))
    _replace_all(root, "$0,000.00", total)
    if len(tables) >= 2:
        t2 = tables[1]
        rows = _table_rows(t2)
        if rows:
            cells = [c for c in rows[0] if c.tag == _q("tc")]
            if cells:
                _set_cell_text(t2, 0, len(cells) - 1, total)


def _fill_ignitai(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(root, "2024-003", inv)
    _replace_all(root, "March 14, 2025", _short_date(invoice_date))
    # Soft-break separates Branch Code; replace line-by-line so w:br stays.
    _replace_one(
        root,
        "Bank Name: Account Name: Account No:",
        f"Bank Name: {bank} Account Name: {name} Account No: {iban}",
    )
    if not any(
        f"Bank Name: {bank}" in (t.text or "") or bank in (t.text or "")
        for t in root.iter(_q("t"))
    ):
        # Fallback when label text is split across runs on one soft-break line
        for p in root.iter(_q("p")):
            for segment in _line_segments(p):
                full = "".join(t.text or "" for t in segment)
                if "Bank Name:" in full and "Account No:" in full and bank not in full:
                    _set_segment_text(
                        segment,
                        f"Bank Name: {bank} Account Name: {name} Account No: {iban}",
                    )
                    break
    _fill_label(root, "Branch Code", branch)
    if branch and not any(branch in (t.text or "") for t in root.iter(_q("t"))):
        _replace_one(root, "Branch Code:", f"Branch Code: {branch}")
    tasks = list(data.tasks[:3]) if data.tasks else []
    # Template duplicates the items table (body + textbox); fill every copy.
    for tbl in _tables_matching(root, "Architectural Design", "Item Description"):
        rows = _table_rows(tbl)
        for i, row in enumerate((2, 3, 4)):
            if i >= len(tasks) or row >= len(rows):
                break
            _set_cell_text(tbl, row, 0, tasks[i].sub_task)
            cells = [c for c in rows[row] if c.tag == _q("tc")]
            if len(cells) >= 4:
                _set_cell_text(tbl, row, 3, _money(tasks[i].amount))
        # Drop 4th sample row + empty spacer rows above total
        if len(_table_rows(tbl)) > 5:
            _delete_rows(tbl, [5])
        _trim_empty_rows_above_last(tbl, min_rows=5)
        rows = _table_rows(tbl)
        for ri, row in enumerate(rows):
            text = "".join(_para_text(p) for p in row.iter(_q("p")))
            if "Total Amount Due" in text:
                cells = [c for c in row if c.tag == _q("tc")]
                if cells:
                    _set_cell_text(tbl, ri, len(cells) - 1, total)
                break
    _replace_all(root, "$30,000", total)
    # Tighten empty paragraphs that push "Thank you" onto page 2 in LibreOffice.
    body = root.find(_q("body"))
    if body is not None:
        paras = [p for p in body if p.tag == _q("p")]
        thank_idx = None
        for i, p in enumerate(paras):
            if "Thank you" in _para_text(p):
                thank_idx = i
                break
        if thank_idx is not None:
            j = thank_idx - 1
            while j >= 0 and not _para_text(paras[j]).strip():
                parent = paras[j].getparent()
                if parent is not None:
                    parent.remove(paras[j])
                j -= 1


FILLERS = {
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


def generate_docx_bytes_via_ooxml(
    data: WordInvoiceData,
    *,
    invoice_date: date | None = None,
) -> bytes:
    """Fill template by rewriting document.xml inside the docx (keeps drawings)."""
    if data.invoice_number not in FILLERS:
        raise ValidationError(
            f"OOXML fill is not configured for invoice template {data.invoice_number}."
        )
    source = ensure_template_exists(data.invoice_number)
    with tempfile.TemporaryDirectory(prefix="inv-ooxml-") as tmp:
        work = Path(tmp) / source.name
        shutil.copy2(source, work)
        buf = io.BytesIO()
        with zipfile.ZipFile(work, "r") as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    raw = zin.read(info.filename)
                    if info.filename == "word/document.xml":
                        root = etree.fromstring(raw)
                        FILLERS[data.invoice_number](root, data, invoice_date)
                        raw = etree.tostring(
                            root,
                            xml_declaration=True,
                            encoding="UTF-8",
                            standalone=True,
                        )
                    zout.writestr(info, raw)
        return buf.getvalue()
