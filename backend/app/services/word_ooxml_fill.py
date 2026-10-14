"""Fill Word templates on Linux/AWS by editing OOXML in the .docx zip.

Preserves DrawingML (Beecodify header bars, etc.) that python-docx save strips.
Used when Microsoft Word COM is not available.
"""
from __future__ import annotations

import io
import re
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


def _is_nested_object(tag: str) -> bool:
    """Drawing/VML/ActiveX subtrees embed their own paragraphs — never walk into them."""
    if tag in (_q("drawing"), _q("pict"), _q("object"), _q("objectLink")):
        return True
    # mc:AlternateContent wraps DrawingML + VML fallback textboxes
    return tag.endswith("}AlternateContent") or tag.endswith("}drawing") or tag.endswith(
        "}pict"
    )


def _iter_para_text_nodes(p: etree._Element):
    """Yield w:t / w:br that belong to this paragraph's runs only (not nested textboxes)."""

    def walk(el: etree._Element):
        for child in el:
            if _is_nested_object(child.tag):
                continue
            if child.tag in (_q("t"), _q("br")):
                yield child
            else:
                yield from walk(child)

    yield from walk(p)


def _para_text(p: etree._Element) -> str:
    return "".join(
        (t.text or "") for t in _iter_para_text_nodes(p) if t.tag == _q("t")
    )


def _set_text_node(t: etree._Element, new_text: str) -> None:
    t.text = new_text
    if new_text[:1].isspace() or new_text[-1:].isspace():
        t.set(XML_SPACE, "preserve")
    elif XML_SPACE in t.attrib and not (new_text[:1].isspace() or new_text[-1:].isspace()):
        # keep preserve if still useful; harmless either way
        pass


def _set_para_text(p: etree._Element, new_text: str) -> None:
    texts = [t for t in _iter_para_text_nodes(p) if t.tag == _q("t")]
    if not texts:
        r = etree.SubElement(p, _q("r"))
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, new_text)
        return
    _set_text_node(texts[0], new_text)
    for t in texts[1:]:
        t.text = ""


def _line_segments(p: etree._Element) -> list[list[etree._Element]]:
    """Group w:t nodes by soft-break lines so replaces never collapse w:br.

    Skips DrawingML/VML textboxes nested inside the paragraph (Ravotek/Cozy
    invoice-NO boxes). Walking into those with p.iter() used to flatten the
    whole textbox into one run and hide invoice# in LibreOffice/Word PDF.
    """
    segments: list[list[etree._Element]] = []
    current: list[etree._Element] = []
    for node in _iter_para_text_nodes(p):
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


def _set_cell_text_exclusive(tbl: etree._Element, row_0: int, col_0: int, text: str) -> None:
    """Set cell text and blank every other paragraph (multi-label total rows)."""
    rows = _table_rows(tbl)
    if row_0 < 0 or row_0 >= len(rows):
        return
    cells = [c for c in rows[row_0] if c.tag == _q("tc")]
    if col_0 < 0 or col_0 >= len(cells):
        return
    cell = cells[col_0]
    paras = [p for p in cell.iter(_q("p"))]
    if not paras:
        p = etree.SubElement(cell, _q("p"))
        _set_para_text(p, text if text != "" else " ")
        return
    _set_para_text(paras[0], text if text != "" else " ")
    for p in paras[1:]:
        _set_para_text(p, "")


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


def _rpr_verdana(*, bold: bool = False, size_half_points: str = "24") -> etree._Element:
    """Beecodify uses Verdana; keep it so LibreOffice matches Word glyphs."""
    rpr = etree.Element(_q("rPr"))
    if bold:
        etree.SubElement(rpr, _q("b"))
    sz = etree.SubElement(rpr, _q("sz"))
    sz.set(_q("val"), size_half_points)
    sz_cs = etree.SubElement(rpr, _q("szCs"))
    sz_cs.set(_q("val"), size_half_points)
    for tag in ("rFonts",):
        fonts = etree.SubElement(rpr, _q(tag))
        fonts.set(_q("ascii"), "Verdana")
        fonts.set(_q("hAnsi"), "Verdana")
        fonts.set(_q("cs"), "Verdana")
    return rpr


def _make_para(text: str, *, bold: bool = False, size_half_points: str = "24") -> etree._Element:
    p = etree.Element(_q("p"))
    r = etree.SubElement(p, _q("r"))
    r.append(_rpr_verdana(bold=bold, size_half_points=size_half_points))
    t = etree.SubElement(r, _q("t"))
    _set_text_node(t, text)
    return p


def _make_para_multiline(
    lines: list[str], *, bold: bool = False, size_half_points: str = "24"
) -> etree._Element:
    """One paragraph with soft-breaks between lines (LibreOffice-safe)."""
    p = etree.Element(_q("p"))
    for i, line in enumerate(lines):
        if i:
            r_br = etree.SubElement(p, _q("r"))
            r_br.append(_rpr_verdana(bold=bold, size_half_points=size_half_points))
            etree.SubElement(r_br, _q("br"))
        r = etree.SubElement(p, _q("r"))
        r.append(_rpr_verdana(bold=bold, size_half_points=size_half_points))
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, line)
    return p


def _make_labeled_para(label: str, value: str, *, size_half_points: str = "24") -> etree._Element:
    """'Date: October 13, 2026' with bold label — matches Word COM PDF."""
    p = etree.Element(_q("p"))
    r1 = etree.SubElement(p, _q("r"))
    r1.append(_rpr_verdana(bold=True, size_half_points=size_half_points))
    t1 = etree.SubElement(r1, _q("t"))
    _set_text_node(t1, f"{label} ")
    r2 = etree.SubElement(p, _q("r"))
    r2.append(_rpr_verdana(bold=True, size_half_points=size_half_points))
    t2 = etree.SubElement(r2, _q("t"))
    _set_text_node(t2, value)
    return p


def _tc_with_paras(paras: list[etree._Element], width_twips: str) -> etree._Element:
    tc = etree.Element(_q("tc"))
    tc_pr = etree.SubElement(tc, _q("tcPr"))
    tc_w = etree.SubElement(tc_pr, _q("tcW"))
    tc_w.set(_q("w"), width_twips)
    tc_w.set(_q("type"), "dxa")
    # Match Word's visual padding inside Beecodify columns.
    mar = etree.SubElement(tc_pr, _q("tcMar"))
    for edge, val in (("top", "0"), ("left", "0"), ("bottom", "0"), ("right", "120")):
        el = etree.SubElement(mar, _q(edge))
        el.set(_q("w"), val)
        el.set(_q("type"), "dxa")
    for p in paras:
        tc.append(p)
    if not paras:
        tc.append(_make_para(""))
    return tc


def _split_beecodify_address(addr: str) -> list[str]:
    """Word wraps Beecodify address as street / city-state-zip."""
    addr = " ".join(addr.split())
    m = re.match(r"^(.*?\bST)\s+(.+)$", addr, flags=re.IGNORECASE)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    m = re.match(r"^(.+)\s+([A-Z]{2}\s+\d{5}(?:-\d{4})?)$", addr)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    return [addr]


def _bank_lines_from_para(bank_p: etree._Element) -> list[str]:
    """Extract filled bank lines (soft-break separated)."""
    lines: list[str] = []
    buf = ""
    for node in bank_p.iter():
        if node.tag == _q("br"):
            lines.append(buf)
            buf = ""
            continue
        if node.tag == _q("t"):
            buf += node.text or ""
    lines.append(buf)
    return [ln.strip() for ln in lines if ln.strip()]


def _flatten_beecodify_columns(root: etree._Element, *, invoice_date: date | None) -> None:
    """Rebuild Beecodify header to match Microsoft Word PDF positions.

    Measured from a correct Word COM PDF:
      left text ~x=59.5pt, right 'From' ~x=342pt
    Template page has left/right margin 0 and uses newspaper columns — LibreOffice
    reflows those columns, so we replace that block with a borderless 2-col table.
    """
    body = root.find(_q("body"))
    if body is None:
        return
    children = list(body)
    date_p = billed_p = company_p = bank_p = None
    for child in children:
        if child.tag != _q("p"):
            continue
        text = _para_text(child)
        if text.startswith("Date:") or text.startswith("Date: "):
            date_p = child
        elif "Billed" in text and "to:" in text and "BEECODIFY" not in text:
            billed_p = child
        elif "BEECODIFY" in text or "From:" in text:
            company_p = child
        elif "Bank Name" in text:
            bank_p = child

    if not all([date_p is not None, billed_p is not None, company_p is not None, bank_p is not None]):
        return

    left_extra: list[str] = []
    right_extra: list[str] = []
    buf = ""
    saw_from = False

    def _flush() -> None:
        nonlocal buf
        (right_extra if saw_from else left_extra).append(buf)
        buf = ""

    for node in company_p.iter():
        if node.tag == _q("br"):
            if node.get(_q("type")) == "column":
                _flush()
                saw_from = True
                continue
            _flush()
            continue
        if node.tag == _q("t"):
            buf += node.text or ""
    _flush()
    left_extra = [ln.strip() for ln in left_extra if ln.strip()]
    right_extra = [ln.strip() for ln in right_extra if ln.strip()]
    if not any(x.lower().startswith("from") for x in right_extra):
        right_extra = ["From:", *right_extra]

    # LEFT: Date (one line) + Billed to + company + address lines (Word wrap)
    left_paras: list[etree._Element] = [
        _make_labeled_para("Date:", _full_date(invoice_date)),
        _make_para(""),
        _make_para("Billed to:", bold=True),
    ]
    for i, ln in enumerate(left_extra):
        if i == 0:
            left_paras.append(_make_para(""))
            left_paras.append(_make_para(ln))
        else:
            for part in _split_beecodify_address(ln):
                left_paras.append(_make_para(part))

    # RIGHT: From (bold) + bank lines. Spacer aligns From near "Billed to" (Word ~y=212).
    right_paras: list[etree._Element] = [_make_para(""), _make_para("")]
    for ln in right_extra:
        right_paras.append(_make_para(ln, bold=ln.lower().startswith("from")))
    for ln in _bank_lines_from_para(bank_p):
        low = ln.lower()
        # Soft-wrap long bank lines like Word's narrow right column.
        if low.startswith("bank name:"):
            rest = ln.split(":", 1)[-1].strip().split()
            # Word PDF: "Bank Name: Eos in" / "temporibus q"
            if len(rest) >= 3:
                right_paras.append(_make_para(f"Bank Name: {rest[0]} {rest[1]}"))
                right_paras.append(_make_para(" ".join(rest[2:])))
                continue
        if low.startswith("account no:"):
            val = ln.split(":", 1)[-1].strip()
            right_paras.append(_make_para("Account NO:"))
            right_paras.append(_make_para(val))
            continue
        if low.startswith("branch code:"):
            rest = ln.split(":", 1)[-1].strip().split()
            # Word PDF: "Branch Code: Ut anim" / "conset E"
            if len(rest) >= 3:
                right_paras.append(_make_para(f"Branch Code: {rest[0]} {rest[1]}"))
                right_paras.append(_make_para(" ".join(rest[2:])))
                continue
        right_paras.append(_make_para(ln))

    # Page is 11910 twips wide, margins 0. Word places left @59.5pt, From @342pt.
    left_indent = "1190"  # ~59.5pt
    left_w = "5650"  # ~282.5pt → right starts ~342pt
    right_w = "5070"
    table_w = str(int(left_w) + int(right_w))

    tbl = etree.Element(_q("tbl"))
    tbl_pr = etree.SubElement(tbl, _q("tblPr"))
    tbl_w = etree.SubElement(tbl_pr, _q("tblW"))
    tbl_w.set(_q("w"), table_w)
    tbl_w.set(_q("type"), "dxa")
    tbl_ind = etree.SubElement(tbl_pr, _q("tblInd"))
    tbl_ind.set(_q("w"), left_indent)
    tbl_ind.set(_q("type"), "dxa")
    borders = etree.SubElement(tbl_pr, _q("tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = etree.SubElement(borders, _q(edge))
        b.set(_q("val"), "nil")
        b.set(_q("sz"), "0")
        b.set(_q("space"), "0")
        b.set(_q("color"), "auto")
    tbl_grid = etree.SubElement(tbl, _q("tblGrid"))
    for w in (left_w, right_w):
        g = etree.SubElement(tbl_grid, _q("gridCol"))
        g.set(_q("w"), w)

    tr = etree.SubElement(tbl, _q("tr"))
    tr.append(_tc_with_paras(left_paras, left_w))
    tr.append(_tc_with_paras(right_paras, right_w))

    insert_at = list(body).index(date_p)
    body.insert(insert_at, tbl)

    remove = {date_p, billed_p, company_p, bank_p}
    started = False
    for child in list(body):
        if child in remove:
            started = True
            body.remove(child)
            continue
        if started and child.tag == _q("p") and not _para_text(child).strip():
            nxt = child.getnext()
            if nxt is not None and (nxt in remove or nxt is tbl or nxt.tag == _q("tbl")):
                body.remove(child)
            else:
                break
        elif started and child is tbl:
            continue
        elif started:
            break

    for sect in root.iter(_q("sectPr")):
        cols = sect.find(_q("cols"))
        if cols is not None:
            cols.set(_q("num"), "1")
            cols.set(_q("space"), "0")
            for col in list(cols):
                cols.remove(col)


def _fill_beecodify(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(root, "NO. 000001", f"NO. {inv}")
        _replace_all(root, "000001", inv)
    # Keep "Date:" run intact (template splits month/day/year across runs).
    new_date = _full_date(invoice_date)
    d = invoice_date or date.today()
    if not (
        _replace_in_text_nodes(root, "September", f" {d.strftime('%B')}", replace_all=False)
        and _replace_in_text_nodes(root, "15,", f"{d.day},", replace_all=False)
        and _replace_in_text_nodes(root, "2030", str(d.year), replace_all=False)
    ):
        _replace_all(root, "September 15, 2030", new_date)
    # Match Word COM soft-break bank block (preserves line breaks for LibreOffice).
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
    # Critical for live Linux PDF (LibreOffice): flatten MS newspaper columns
    # into Word-matched left/right positions.
    _flatten_beecodify_columns(root, invoice_date=invoice_date)


def _split_coretechify_address(addr: str) -> list[str]:
    """Word wraps Coretechify address as street / city-state / zip."""
    addr = " ".join(addr.split())
    m = re.match(
        r"^(.*?\b(?:BLVD|ST|AVE|RD|DR))\s+(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$",
        addr,
        flags=re.IGNORECASE,
    )
    if m:
        return [
            m.group(1).strip(),
            f"{m.group(2).strip()}, {m.group(3).strip()}",
            m.group(4).strip(),
        ]
    m = re.match(r"^(.+)\s+([A-Z]{2}\s+\d{5}(?:-\d{4})?)$", addr)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    return [addr]


def _flatten_coretechify_columns(
    root: etree._Element,
    *,
    invoice_date: date | None,
    invoice_no: str,
) -> None:
    """Flatten newspaper columns so LibreOffice matches Word left/right layout.

    Word positions (from real COM PDF): left ~x=59.5pt, right ~x=342pt.
    """
    body = root.find(_q("body"))
    if body is None:
        return
    children = list(body)
    date_label_p = date_val_p = invoice_p = billed_p = company_p = bank_p = None
    for child in children:
        if child.tag != _q("p"):
            continue
        text = _para_text(child)
        if text.strip() == "Date:":
            date_label_p = child
        elif date_label_p is not None and date_val_p is None and text.strip() and "Billed" not in text and "INVOICE" not in text.upper():
            # Next non-empty after Date: is the date value (may carry a column break).
            if re.search(r"\d{4}", text) or any(
                m in text for m in ("January", "February", "March", "April", "May", "June",
                                    "July", "August", "September", "October", "November", "December")
            ):
                date_val_p = child
        elif text.upper().startswith("INVOICE NO"):
            invoice_p = child
        elif "Billed" in text and "to:" in text:
            billed_p = child
        elif "CORETECHIFY" in text.upper() or ("From:" in text and "Bank" not in text):
            company_p = child
        elif "Bank Name" in text:
            bank_p = child

    if date_label_p is None or billed_p is None or company_p is None or bank_p is None:
        return

    left_lines: list[str] = []
    right_head: list[str] = []
    buf = ""
    saw_from = False
    for node in company_p.iter():
        if node.tag == _q("br"):
            chunk = buf.strip()
            if node.get(_q("type")) == "column":
                if chunk:
                    left_lines.append(chunk)
                buf = ""
                saw_from = True
                continue
            if chunk:
                (right_head if saw_from else left_lines).append(chunk)
            buf = ""
            continue
        if node.tag == _q("t"):
            buf += node.text or ""
    tail = buf.strip()
    if tail:
        (right_head if saw_from else left_lines).append(tail)
    if not any(x.lower().startswith("from") for x in right_head):
        right_head = ["From:", *right_head]

    company = left_lines[0] if left_lines else "CORETECHIFY INC"
    addr_parts: list[str] = []
    for ln in left_lines[1:]:
        addr_parts.extend(_split_coretechify_address(ln))

    inv = invoice_no or "000001"
    left_paras: list[etree._Element] = [
        _make_labeled_para("Date:", _full_date(invoice_date)),
        _make_para(""),
        _make_para("Billed to:", bold=True),
        _make_para(""),
        _make_para(company),
    ]
    for part in addr_parts:
        left_paras.append(_make_para(part))

    right_paras: list[etree._Element] = [
        _make_para(f"INVOICE NO. {inv}"),
        _make_para(""),
    ]
    for ln in right_head:
        right_paras.append(_make_para(ln, bold=ln.lower().startswith("from")))
    for ln in _bank_lines_from_para(bank_p):
        right_paras.append(_make_para(ln))

    left_indent = "1190"  # ~59.5pt
    left_w = "5650"
    right_w = "5070"
    table_w = str(int(left_w) + int(right_w))

    tbl = etree.Element(_q("tbl"))
    tbl_pr = etree.SubElement(tbl, _q("tblPr"))
    tbl_w = etree.SubElement(tbl_pr, _q("tblW"))
    tbl_w.set(_q("w"), table_w)
    tbl_w.set(_q("type"), "dxa")
    tbl_ind = etree.SubElement(tbl_pr, _q("tblInd"))
    tbl_ind.set(_q("w"), left_indent)
    tbl_ind.set(_q("type"), "dxa")
    borders = etree.SubElement(tbl_pr, _q("tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = etree.SubElement(borders, _q(edge))
        b.set(_q("val"), "nil")
        b.set(_q("sz"), "0")
        b.set(_q("space"), "0")
        b.set(_q("color"), "auto")
    tbl_grid = etree.SubElement(tbl, _q("tblGrid"))
    for w in (left_w, right_w):
        g = etree.SubElement(tbl_grid, _q("gridCol"))
        g.set(_q("w"), w)

    tr = etree.SubElement(tbl, _q("tr"))
    tr.append(_tc_with_paras(left_paras, left_w))
    tr.append(_tc_with_paras(right_paras, right_w))

    insert_at = list(body).index(date_label_p)
    body.insert(insert_at, tbl)

    remove = {date_label_p, billed_p, company_p, bank_p}
    if date_val_p is not None:
        remove.add(date_val_p)
    if invoice_p is not None:
        remove.add(invoice_p)
    started = False
    for child in list(body):
        if child in remove:
            started = True
            body.remove(child)
            continue
        if started and child.tag == _q("p") and not _para_text(child).strip():
            nxt = child.getnext()
            if nxt is not None and (nxt in remove or nxt is tbl or nxt.tag == _q("tbl")):
                body.remove(child)
            else:
                break
        elif started and child is tbl:
            continue
        elif started:
            break

    for sect in root.iter(_q("sectPr")):
        cols = sect.find(_q("cols"))
        if cols is not None:
            cols.set(_q("num"), "1")
            cols.set(_q("space"), "0")
            for col in list(cols):
                cols.remove(col)

    # Leftover column breaks (e.g. under Note) make LibreOffice spill to extra pages.
    for br in list(root.iter(_q("br"))):
        if br.get(_q("type")) == "column":
            parent = br.getparent()
            if parent is not None:
                parent.remove(br)


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
    # Live LibreOffice misplaces address into the right column; flatten like Word.
    _flatten_coretechify_columns(root, invoice_date=invoice_date, invoice_no=inv)


def _bravix_date(invoice_date: date | None) -> str:
    """Bravix template uses DD.MM.YYYY (e.g. 11.03.2030)."""
    d = invoice_date or date.today()
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _fill_bravix_payment_lines(
    tbl: etree._Element,
    row_0: int,
    name: str,
    bank: str,
    iban: str,
    branch: str,
) -> None:
    """Keep real layout: four stacked label lines in the payment cell."""
    rows = _table_rows(tbl)
    if row_0 < 0 or row_0 >= len(rows):
        return
    cells = [c for c in rows[row_0] if c.tag == _q("tc")]
    if not cells:
        return
    filled = {
        "account name": f"Account Name: {name}",
        "bank name": f"Bank Name: {bank}",
        "account no": f"Account No: {iban}",
        "branch code": f"Branch Code: {branch}",
    }
    # Direct cell paragraphs only (template has empty spacers + 4 label lines).
    for p in cells[0].findall(_q("p")):
        raw = _para_text(p).strip()
        if not raw:
            continue
        key = raw.lower().rstrip(":").strip()
        for label, text in filled.items():
            if key == label or key.startswith(label):
                _set_para_text(p, text)
                break


def _fill_bravix(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount, cents=True)
    if inv:
        _replace_all(root, "01234", inv)
    _replace_all(root, "11.03.2030", _bravix_date(invoice_date))
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
                _fill_bravix_payment_lines(tables[0], total_row, name, bank, iban, branch)
                _set_cell_text(tables[0], total_row, len(cells) - 1, total)
                if len(cells) >= 5:
                    _set_cell_text(tables[0], total_row, 4, total)
    _replace_all(root, "$95.00", total)


def _ravotek_date(invoice_date: date | None) -> str:
    """Real Ravotek date style: '11 . 02 . 2030' (DD . MM . YYYY)."""
    d = invoice_date or date.today()
    return f"{d.day:02d} . {d.month:02d} . {d.year}"


def _fill_ravotek(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(root, "01234", inv)
    _replace_all(root, "11 . 02 . 2030", _ravotek_date(invoice_date))
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
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(root, "01234", inv)
    _replace_all(root, "11 . 02 . 2030", _short_date(invoice_date))
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


def _ecomify_spaced(text: str) -> str:
    """Ecomify template letter-spaces values (e.g. 0 1 / 0 2 / 2 0 2 3)."""
    return " ".join(text)


def _ecomify_date(invoice_date: date | None) -> str:
    d = invoice_date or date.today()
    return _ecomify_spaced(f"{d.day:02d}/{d.month:02d}/{d.year}")


def _ecomify_money(amount: int) -> str:
    return _ecomify_spaced(f"${int(amount)}")


def _clear_table_row(tbl: etree._Element, row_0: int) -> None:
    rows = _table_rows(tbl)
    if row_0 < 0 or row_0 >= len(rows):
        return
    cells = [c for c in rows[row_0] if c.tag == _q("tc")]
    for ci in range(len(cells)):
        _set_cell_text(tbl, row_0, ci, " ")


def _fill_ecomify(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _ecomify_money(data.total_amount)
    zero = _ecomify_spaced("$0")
    if inv:
        _replace_all(root, "1 2 3 4 / 5 6 7 8 9", _ecomify_spaced(inv))
    _replace_all(root, "0 1 / 0 2 / 2 0 2 3", _ecomify_date(invoice_date))
    # Preserve soft-breaks between Payable To lines (real format).
    _fill_label(root, "Bank Name", bank)
    _fill_label(root, "Account Name", name)
    _fill_label(root, "Account No", iban)
    _fill_label(root, "Branch Code", branch)
    tables = _tables(root)
    if len(tables) >= 2:
        tbl = tables[1]
        tasks = list(data.tasks[:3]) if data.tasks else []
        rows = _table_rows(tbl)
        for i in range(min(3, len(tasks))):
            _set_cell_text(tbl, i, 1, tasks[i].sub_task)
            cells = [c for c in rows[i] if c.tag == _q("tc")]
            if len(cells) >= 5:
                _set_cell_text(tbl, i, 4, _ecomify_money(tasks[i].amount))
        # Keep full 7-row grid like the real Word template; clear unused sample rows.
        for ri in range(len(tasks), len(rows)):
            _clear_table_row(tbl, ri)
    if len(tables) >= 3:
        summary = tables[2]
        rows = _table_rows(summary)
        for ri, val in ((0, total), (1, zero), (2, zero), (3, total)):
            if ri < len(rows):
                cells = [c for c in rows[ri] if c.tag == _q("tc")]
                if cells:
                    _set_cell_text(summary, ri, len(cells) - 1, val)


def _alpha_date(invoice_date: date | None) -> str:
    """Alpha template date cell: 28/ 07 / 2095 → DD/ MM / YYYY."""
    d = invoice_date or date.today()
    return f"{d.day:02d}/ {d.month:02d} / {d.year}"


def _set_alpha_payment_para(p: etree._Element, name: str, iban: str, branch: str) -> None:
    """Rebuild Account/No/Branch as three soft-break lines (real Alpha layout).

    Template ends this paragraph with a column break so TOTAL stays in the
    right newspaper column — keep that or LibreOffice moves Branch Code right.
    """
    first_rpr = None
    for r in p.findall(_q("r")):
        rpr = r.find(_q("rPr"))
        if rpr is not None:
            first_rpr = etree.fromstring(etree.tostring(rpr))
            break
    for child in list(p):
        if child.tag in (_q("r"), _q("hyperlink")):
            p.remove(child)

    def _add_text(text: str) -> None:
        r = etree.SubElement(p, _q("r"))
        if first_rpr is not None:
            r.append(etree.fromstring(etree.tostring(first_rpr)))
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, text)

    def _add_break(*, column: bool = False) -> None:
        r = etree.SubElement(p, _q("r"))
        if first_rpr is not None:
            r.append(etree.fromstring(etree.tostring(first_rpr)))
        br = etree.SubElement(r, _q("br"))
        if column:
            br.set(_q("type"), "column")

    lines = [
        f"Account Name: {name}",
        f"Account No.: {iban}",
        f"Branch Code: {branch}",
    ]
    for i, line in enumerate(lines):
        if i:
            _add_break()
        _add_text(line)
    _add_break(column=True)


def _fill_alpha(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(root, "52131", inv)
    _replace_all(root, "28/ 07 / 2095", _alpha_date(invoice_date))
    # Label is split across runs ("Bank" + " Name: "); replace joined segment.
    if not _replace_one(root, "Bank Name: ", f"Bank Name: {bank} "):
        _fill_label(root, "Bank Name", bank)
    # Account line is one paragraph that Word wraps into 3 visual lines — rebuild with soft-breaks.
    payment_paras = [
        p
        for p in root.iter(_q("p"))
        if "Account Name" in _para_text(p) and "Branch Code" in _para_text(p)
    ]
    if payment_paras:
        for p in payment_paras:
            _set_alpha_payment_para(p, name, iban, branch)
    else:
        _replace_all(
            root,
            "Account Name: Daniel Gallego Account No.: 0123 4567 8901 Branch Code",
            f"Account Name: {name} Account No.: {iban} Branch Code: {branch}",
        )
        _replace_all(root, "Daniel Gallego", name)
        _replace_all(root, "0123 4567 8901", iban)
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


def _synergo_slash_date(invoice_date: date | None) -> str:
    """Invoice date style: '01 / 02 / 2023'."""
    d = invoice_date or date.today()
    return f"{d.day:02d} / {d.month:02d} / {d.year}"


def _synergo_pay_by_date(invoice_date: date | None) -> str:
    """Pay by style: '23 June 2023'."""
    d = invoice_date or date.today()
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _synergo_total_sz(total: str) -> str:
    """Half-points for Total line so amount stays on one line in the narrow column."""
    n = len(total)
    if n <= 5:
        return "36"  # original 18pt
    if n <= 7:
        return "28"
    if n <= 9:
        return "22"
    return "18"


def _synergo_rebuild_total_para(p: etree._Element, total: str) -> None:
    """Keep Total\\t$amount on one line (original layout); shrink font for long totals."""
    for child in list(p):
        if child.tag != _q("pPr"):
            p.remove(child)
    sz = _synergo_total_sz(total)

    def _add(*, text: str | None = None, tab: bool = False) -> None:
        r = etree.SubElement(p, _q("r"))
        rpr = etree.SubElement(r, _q("rPr"))
        fonts = etree.SubElement(rpr, _q("rFonts"))
        fonts.set(_q("ascii"), "Tahoma")
        etree.SubElement(rpr, _q("b"))
        sz_el = etree.SubElement(rpr, _q("sz"))
        sz_el.set(_q("val"), sz)
        sz_cs = etree.SubElement(rpr, _q("szCs"))
        sz_cs.set(_q("val"), sz)
        if tab:
            etree.SubElement(r, _q("tab"))
            return
        spacing = etree.SubElement(rpr, _q("spacing"))
        spacing.set(_q("val"), "-2" if text == "Total" else "-4")
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, text or "")

    _add(text="Total")
    _add(tab=True)
    _add(text=total)


def _synergo_rebuild_account_para(p: etree._Element, name: str, iban: str) -> None:
    """Match original PDF lines: Account Name, then Account No. (soft-break)."""
    first_rpr = None
    for r in p.findall(_q("r")):
        rpr = r.find(_q("rPr"))
        if rpr is not None and r.find(_q("t")) is not None:
            first_rpr = etree.fromstring(etree.tostring(rpr))
            break
    for child in list(p):
        if child.tag in (_q("r"), _q("hyperlink")):
            p.remove(child)

    def _add(text: str, *, br: bool = False) -> None:
        r = etree.SubElement(p, _q("r"))
        if first_rpr is not None:
            r.append(etree.fromstring(etree.tostring(first_rpr)))
        if br:
            etree.SubElement(r, _q("br"))
            return
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, text)

    _add(f"Account Name: {name}")
    _add("", br=True)
    _add(f"Account No.: {iban}")


def _fill_synergo(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    """Invoice14 — Synergo Incdocx (Invoice to / qty-price table / PAYMENT METHOD)."""
    inv = data.document_invoice_no or ""
    bank, name, iban = data.bank or "", data.person_name or "", data.iban or ""
    total = _money(data.total_amount)
    if inv:
        _replace_all(root, "52131", inv)
    _replace_all(root, "01 / 02 / 2023", _synergo_slash_date(invoice_date))
    _replace_all(root, "23 June 2023", _synergo_pay_by_date(invoice_date))
    _replace_all(root, "Rimberio Bank", bank)
    account_paras = [
        p
        for p in root.iter(_q("p"))
        if "Account Name" in _para_text(p) and "Account No" in _para_text(p)
    ]
    if account_paras:
        for p in account_paras:
            _synergo_rebuild_account_para(p, name, iban)
    else:
        _replace_all(root, "Alfredo Torres", name)
        _replace_all(root, "0123 4567 8901", iban)
    tasks = list(data.tasks[:3]) if data.tasks else []
    tables = _tables(root)
    item_tables = _tables_matching(root, "Unit Price", "Quantity")
    if not item_tables and len(tables) >= 2:
        item_tables = [tables[1]]
    if tasks and item_tables:
        tbl = item_tables[0]
        rows = _table_rows(tbl)
        for i, task in enumerate(tasks):
            row = i + 1
            if row >= len(rows):
                break
            amt = _money(task.amount)
            _set_cell_text(tbl, row, 0, task.sub_task)
            cells = [c for c in rows[row] if c.tag == _q("tc")]
            if len(cells) >= 2:
                _set_cell_text(tbl, row, 1, "1")
            if len(cells) >= 3:
                _set_cell_text(tbl, row, 2, amt)
            if len(cells) >= 4:
                _set_cell_text(tbl, row, 3, amt)
        if rows:
            last = rows[-1]
            blob = "".join(_para_text(p) for p in last.iter(_q("p")))
            if "Subtotal" in blob:
                cells = [c for c in last if c.tag == _q("tc")]
                if cells:
                    _set_cell_text(tbl, len(rows) - 1, len(cells) - 1, total)
    else:
        _fill_three_services(
            root,
            data,
            sample_names=[
                "A4 Paper (75gr/m2)",
                "Pencil (12ea/box)",
                "Ruler",
            ],
            sample_amounts=["$200", "$75", "$10"],
            cents=False,
        )
    # Subtotal cell still has sample $285 when tasks path didn't set it.
    _replace_all(root, "$285", total)
    # Rebuild Total so long amounts stay on one line with the label (original look).
    for p in root.iter(_q("p")):
        text = _para_text(p)
        if text.strip().lower().startswith("total") and "$" in text:
            _synergo_rebuild_total_para(p, total)
            break


def _set_ignitai_bank_para(
    p: etree._Element, bank: str, name: str, iban: str, branch: str
) -> None:
    """Rebuild bank paragraph as four soft-break lines (real Ignitai layout)."""
    # Keep first run props if present for font continuity.
    first_rpr = None
    for r in p.findall(_q("r")):
        rpr = r.find(_q("rPr"))
        if rpr is not None:
            first_rpr = etree.fromstring(etree.tostring(rpr))
            break
    for child in list(p):
        if child.tag in (_q("r"), _q("hyperlink")):
            p.remove(child)

    def _add_text(text: str) -> None:
        r = etree.SubElement(p, _q("r"))
        if first_rpr is not None:
            r.append(etree.fromstring(etree.tostring(first_rpr)))
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, text)

    def _add_break() -> None:
        r = etree.SubElement(p, _q("r"))
        if first_rpr is not None:
            r.append(etree.fromstring(etree.tostring(first_rpr)))
        etree.SubElement(r, _q("br"))

    lines = [
        f"Bank Name: {bank}",
        f"Account Name: {name}",
        f"Account No: {iban}",
        f"Branch Code: {branch}",
    ]
    for i, line in enumerate(lines):
        if i:
            _add_break()
        _add_text(line)


def _ignitai_rpr(*, bold: bool = False, size_half_points: str = "22") -> etree._Element:
    rpr = etree.Element(_q("rPr"))
    if bold:
        etree.SubElement(rpr, _q("b"))
    sz = etree.SubElement(rpr, _q("sz"))
    sz.set(_q("val"), size_half_points)
    sz_cs = etree.SubElement(rpr, _q("szCs"))
    sz_cs.set(_q("val"), size_half_points)
    fonts = etree.SubElement(rpr, _q("rFonts"))
    fonts.set(_q("ascii"), "Lucida Sans Unicode")
    fonts.set(_q("hAnsi"), "Lucida Sans Unicode")
    fonts.set(_q("cs"), "Lucida Sans Unicode")
    return rpr


def _ignitai_para(text: str, *, bold: bool = False) -> etree._Element:
    p = etree.Element(_q("p"))
    r = etree.SubElement(p, _q("r"))
    r.append(_ignitai_rpr(bold=bold))
    t = etree.SubElement(r, _q("t"))
    _set_text_node(t, text)
    return p


def _flatten_ignitai_header(
    root: etree._Element,
    *,
    invoice_no: str,
    invoice_date: date | None,
) -> None:
    """LibreOffice misreads Ignitai newspaper columns; flatten header to a 2-col table."""
    body = root.find(_q("body"))
    if body is None:
        return
    children = [c for c in body if c.tag == _q("p")]
    from_p = draw_p = addr_p = date_p = None
    for p in children:
        text = _para_text(p)
        has_drawing = any(
            True
            for n in p.iter()
            if n.tag.endswith("}drawing") or n.tag.endswith("}AlternateContent")
        )
        if "From:" in text and "IGNITIA" in text.upper():
            from_p = p
        elif "Invoice:" in text or has_drawing:
            # Drawing para also carries "Invoice: …" after a column break.
            if has_drawing or "Invoice:" in text:
                draw_p = p if draw_p is None or has_drawing else draw_p
        elif "KENTWOOD" in text.upper() or (
            "Date:" in text and "RIVERSIDE" in text.upper()
        ):
            addr_p = p
        elif date_p is None and (
            re.search(r"\d{4}", text)
            and any(
                m in text
                for m in (
                    "January",
                    "February",
                    "March",
                    "April",
                    "May",
                    "June",
                    "July",
                    "August",
                    "September",
                    "October",
                    "November",
                    "December",
                )
            )
            and "Pay" not in text
            and "Bank" not in text
        ):
            date_p = p

    if from_p is None or addr_p is None:
        return

    company = "IGNITIA INC"
    m = re.search(r"(IGNITIA\s+INC)", _para_text(from_p), flags=re.IGNORECASE)
    if m:
        company = m.group(1).upper()
    addr_blob = _para_text(addr_p)
    addr_blob = re.split(r"Date\s*:", addr_blob, maxsplit=1)[0].strip()
    # Real PDF wraps street / city line.
    if "," in addr_blob:
        street, rest = addr_blob.split(",", 1)
        addr_lines = [street.strip() + ",", rest.strip()]
    else:
        addr_lines = [addr_blob] if addr_blob else []

    inv = invoice_no or "000"
    date_str = _full_date(invoice_date)
    left = [
        _ignitai_para("From:", bold=True),
        _ignitai_para(company),
        *[_ignitai_para(line) for line in addr_lines],
    ]
    right = [
        _ignitai_para(f"Invoice:     {inv}", bold=True),
        _ignitai_para(""),
        _ignitai_para("Date:", bold=True),
        _ignitai_para(date_str),
    ]

    left_w, right_w = "5400", "4200"
    table_w = str(int(left_w) + int(right_w))
    tbl = etree.Element(_q("tbl"))
    tbl_pr = etree.SubElement(tbl, _q("tblPr"))
    tbl_w = etree.SubElement(tbl_pr, _q("tblW"))
    tbl_w.set(_q("w"), table_w)
    tbl_w.set(_q("type"), "dxa")
    borders = etree.SubElement(tbl_pr, _q("tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = etree.SubElement(borders, _q(edge))
        b.set(_q("val"), "nil")
        b.set(_q("sz"), "0")
        b.set(_q("space"), "0")
        b.set(_q("color"), "auto")
    grid = etree.SubElement(tbl, _q("tblGrid"))
    for w in (left_w, right_w):
        g = etree.SubElement(grid, _q("gridCol"))
        g.set(_q("w"), w)
    tr = etree.SubElement(tbl, _q("tr"))
    tr.append(_tc_with_paras(left, left_w))
    tr.append(_tc_with_paras(right, right_w))

    insert_at = list(body).index(from_p)
    body.insert(insert_at, tbl)

    # Keep the floating items drawing; strip Invoice text + column break from that para.
    if draw_p is not None:
        for child in list(draw_p):
            if child.tag != _q("r"):
                continue
            has_draw = any(
                True
                for n in child.iter()
                if n.tag.endswith("}drawing") or n.tag.endswith("}AlternateContent")
            )
            if has_draw:
                continue
            draw_p.remove(child)

    for p in (from_p, addr_p, date_p):
        if p is not None and p.getparent() is body:
            body.remove(p)

    for sect in root.iter(_q("sectPr")):
        cols = sect.find(_q("cols"))
        if cols is not None:
            cols.set(_q("num"), "1")
            cols.set(_q("space"), "0")
            for col in list(cols):
                cols.remove(col)

    for br in list(root.iter(_q("br"))):
        if br.get(_q("type")) != "column":
            continue
        # Don't touch breaks nested inside drawings/textboxes.
        parent = br
        skip = False
        while parent is not None:
            tag = parent.tag if isinstance(parent.tag, str) else ""
            if _is_nested_object(tag):
                skip = True
                break
            parent = parent.getparent()
        if skip:
            continue
        parent = br.getparent()
        if parent is not None:
            parent.remove(br)


def _fill_ignitai(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    inv = data.document_invoice_no or ""
    bank, name, iban, branch = data.bank or "", data.person_name or "", data.iban or "", data.branch_code or ""
    total = _money(data.total_amount)
    # Real format: "Invoice:     000" (not "Invoice Number:" / "2024-003").
    if inv:
        if not _replace_all(root, "Invoice:     000", f"Invoice:     {inv}"):
            if not _replace_all(root, "   Invoice:     000", f"   Invoice:     {inv}"):
                _replace_all(root, "2024-003", inv)
    # Real template: "March 14, 2025" (full month name)
    _replace_all(root, "March 14, 2025", _full_date(invoice_date))
    # Stack bank fields on four soft-break lines (matches Word PDF).
    bank_paras = [
        p
        for p in root.iter(_q("p"))
        if "Bank Name" in _para_text(p) and "Branch Code" in _para_text(p)
    ]
    if bank_paras:
        for p in bank_paras:
            _set_ignitai_bank_para(p, bank, name, iban, branch)
    else:
        _fill_label(root, "Bank Name", bank)
        _fill_label(root, "Account Name", name)
        _fill_label(root, "Account No", iban)
        _fill_label(root, "Branch Code", branch)
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
    # Critical for live Linux PDF: flatten MS newspaper columns for header.
    _flatten_ignitai_header(root, invoice_no=inv, invoice_date=invoice_date)
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
                # Keep section-break paras (they hold sectPr).
                ppr = paras[j].find(_q("pPr"))
                if ppr is not None and ppr.find(_q("sectPr")) is not None:
                    break
                parent = paras[j].getparent()
                if parent is not None:
                    parent.remove(paras[j])
                j -= 1


def _dynamo_slash_date(invoice_date: date | None) -> str:
    d = invoice_date or date.today()
    return f"{d.day:02d} / {d.month:02d} / {d.year}"


def _dynamo_pay_by_date(invoice_date: date | None) -> str:
    d = invoice_date or date.today()
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _dynamo_rebuild_para(
    p: etree._Element,
    lines: list[str],
    *,
    keep_leading_column_br: bool = False,
    compact_first: bool = False,
) -> None:
    """Replace paragraph runs with stacked lines; optionally keep a leading column break."""
    first_rpr = None
    for r in p.findall(_q("r")):
        rpr = r.find(_q("rPr"))
        if rpr is not None and r.find(_q("t")) is not None:
            first_rpr = etree.fromstring(etree.tostring(rpr))
            break
    for child in list(p):
        if child.tag in (_q("r"), _q("hyperlink")):
            p.remove(child)

    def _add(text: str, *, br: bool = False, column: bool = False, compact: bool = False) -> None:
        r = etree.SubElement(p, _q("r"))
        if first_rpr is not None and not column:
            rpr = etree.fromstring(etree.tostring(first_rpr))
            if compact:
                # Narrow right column fits ~6 chars at template scale; squeeze longer IDs.
                w_el = rpr.find(_q("w"))
                if w_el is None:
                    w_el = etree.SubElement(rpr, _q("w"))
                w_el.set(_q("val"), "72")
                sp = rpr.find(_q("spacing"))
                if sp is None:
                    sp = etree.SubElement(rpr, _q("spacing"))
                sp.set(_q("val"), "-12")
            r.append(rpr)
        if br or column:
            br_el = etree.SubElement(r, _q("br"))
            if column:
                br_el.set(_q("type"), "column")
            return
        t = etree.SubElement(r, _q("t"))
        _set_text_node(t, text)

    if keep_leading_column_br:
        _add("", column=True)
    for i, line in enumerate(lines):
        if i:
            _add("", br=True)
        _add(line, compact=compact_first and i == 0 and len(line) > 6)


def _fill_dynamo(root: etree._Element, data: WordInvoiceData, invoice_date: date | None) -> None:
    """Invoice05 — real Dynamo Creatives (Bank Name / Account Name / Account No)."""
    inv = data.document_invoice_no or "DV-001"
    bank, name, iban = data.bank or "", data.person_name or "", data.iban or ""
    total = _money(data.total_amount)
    slash = _dynamo_slash_date(invoice_date)
    # Soft-break keeps Invoice# above Date in the narrow right column.
    inv_paras = [
        p
        for p in root.iter(_q("p"))
        if "DV-001" in _para_text(p) or ("18 / 04 / 2025" in _para_text(p) and "Pay" not in _para_text(p))
    ]
    if inv_paras:
        for p in inv_paras:
            _dynamo_rebuild_para(
                p,
                [inv, slash],
                keep_leading_column_br=True,
                compact_first=True,
            )
    else:
        if inv and inv != "DV-001":
            _replace_all(root, "DV-001", inv)
        _replace_all(root, "18 / 04 / 2025", slash)
    _replace_all(root, "18 April 2025", _dynamo_pay_by_date(invoice_date))
    # Stack Bank Name / Account Name like the real Word PDF.
    bank_paras = [
        p
        for p in root.iter(_q("p"))
        if "Bank Name" in _para_text(p) and "Account Name" in _para_text(p)
    ]
    if bank_paras:
        for p in bank_paras:
            _dynamo_rebuild_para(p, [f"Bank Name: {bank}", f"Account Name: {name}"])
    else:
        _replace_all(
            root,
            "Bank Name:Faisal Bank Account Name:Dynaverse",
            f"Bank Name: {bank} Account Name: {name}",
        )
    if not _replace_all(
        root,
        "Account  No.:  PK52FAYS3059301000006776",
        f"Account  No.:  {iban}",
    ):
        _replace_all(root, "PK52FAYS3059301000006776", iban)
    _fill_three_services(
        root,
        data,
        sample_names=[
            "Social Media Marketing Services",
            "Content Writing",
            "Website Development",
        ],
        sample_amounts=["$4,000", "$3,500", "$2,500"],
        cents=False,
    )
    _replace_all(root, "$10,000", total)
    # Keep column breaks: header (Invoice#/Date) and Tax (payment left / totals right).


FILLERS = {
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
