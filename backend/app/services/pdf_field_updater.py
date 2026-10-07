from __future__ import annotations

import re
from datetime import date

import fitz

from backend.app.models import WordInvoiceData
from backend.app.services.word_date_updater import format_invoice_date
from backend.app.services.word_field_updater import format_amount

# Sample line-item descriptions embedded in each PDF template (must match PDF text).
SAMPLE_LINE_ITEMS: dict[int, list[str]] = {
    1: [
        "Domain & Hosting",
        "UI/UX Design (Figma)",
        "Chat Integration / User ($24)",
    ],
    2: [
        "Cloud Server Services",
        "Mobile Application Development",
        "Brand Management",
    ],
    3: [
        "Social Media Marketing Services",
        "Content Writing",
        "website Development",
    ],
    4: [
        "Social Media Marketing Services",
        "Content Writing",
        "Website Development",
    ],
    5: [
        "Social Media Marketing Services",
        "Content Writing",
        "Website Development",
    ],
}

SAMPLE_LINE_AMOUNTS: dict[int, list[str]] = {
    1: ["$72522222", "$759", "$810"],
    2: ["$983", "$887", "$550"],
    3: ["$2,036.00", "$1,545.00", "$ 1,795.00"],
    4: ["$2,001", "$1,563", "$737"],
    5: ["$4,000", "$3,500", "$2,500"],
}

SAMPLE_TOTALS: dict[int, list[str]] = {
    1: ["$,294"],
    2: ["$2,420"],
    3: ["$ 5,376.00", "$5,376.00"],
    4: ["$4,301", "$4301"],
    5: ["$10,000"],
}

SAMPLE_NAMES: dict[int, list[str]] = {
    1: ["Hammad Hassan"],
    2: ["Syed Muhammad Daniyal Rizvi"],
    3: ["SHAYAN TARIQ SHAIKH"],
    4: ["Anum Aziz"],
    5: ["Syed Muhammad Daniyal Rizvi"],
}

SAMPLE_BANKS: dict[int, list[str]] = {
    1: ["United Bank"],
    2: ["United Bank"],
    3: ["UNITED BANK LIMITED"],
    4: ["HABIB BANK LIMITED"],
    5: ["Faisal Bank"],
}

SAMPLE_IBANS: dict[int, list[str]] = {
    1: ["PK75UNIL0109000307328225"],
    2: ["PK66UNIL0109000280272953"],
    3: ["PK80UNIL0109000302404124"],
    4: ["PK69HABB0000277901470603"],
    5: ["PK52FAYS3059301000006776"],
}

SAMPLE_BRANCHES: dict[int, list[str]] = {
    1: ["1285"],
    2: ["0213"],
    3: ["khushab"],
    4: ["Lahore"],
    5: ["Karachi"],
}

SAMPLE_INVOICE_NOS: dict[int, list[str]] = {
    1: ["HH-007"],
    2: ["SMDR-001"],
    3: ["STS-001"],
    4: ["AA-001"],
    5: ["DV-001"],
}

# Invoice 1 packs payment lines tightly; replace whole lines to avoid neighbor corruption.
INVOICE1_PAYMENT_LINES = [
    ("Send Payment To: Hammad Hassan", "Send Payment To: {name}"),
    ("Bank Name: United Bank", "Bank Name: {bank}"),
    ("IBAN NO.: PK75UNIL0109000307328225", "IBAN NO.: {iban}"),
    ("Branch Code: 1285", "Branch Code: {branch}"),
]


def _replace_text(
    page: fitz.Page,
    old: str,
    new: str,
    *,
    fontsize: float = 9,
    max_width: float | None = None,
    expand: bool = True,
    baseline: bool = False,
) -> int:
    """Replace exact visible text instances via redaction + insert."""
    if not old or old == new:
        return 0
    hits = page.search_for(old, quads=False)
    if not hits:
        return 0

    rects = [fitz.Rect(h) for h in hits]
    for r in rects:
        # Tight wipe — avoid eating the next label line (common in payment blocks).
        wipe = fitz.Rect(r.x0 - 0.3, r.y0 + 0.6, r.x1 + 0.3, r.y1 - 0.6)
        if wipe.y1 <= wipe.y0:
            wipe = fitz.Rect(r.x0 - 0.2, r.y0, r.x1 + 0.2, r.y1)
        page.add_redact_annot(wipe, fill=(1, 1, 1))
    page.apply_redactions(images=0)

    for r in rects:
        fs = min(fontsize, max(6.0, (r.y1 - r.y0) * 0.85))
        if expand:
            char_w = max(fs * 0.5, 3.8)
            width = max(r.width, len(new) * char_w + 2)
            if max_width is not None:
                width = min(width, max_width)
            if len(new) * char_w > width and len(new) > 0:
                fs = max(6.0, (width - 2) / (len(new) * 0.5))
        else:
            width = r.width

        if baseline:
            page.insert_text(
                (r.x0, r.y1 - 1.2),
                new,
                fontsize=fs,
                fontname="helv",
                color=(0, 0, 0),
            )
        else:
            box = fitz.Rect(
                r.x0,
                r.y0,
                min(page.rect.x1 - 8, r.x0 + width),
                r.y1,
            )
            # Ensure a usable textbox height for the chosen font.
            if box.height < fs + 1:
                box.y0 = box.y1 - (fs + 2)
            rc = page.insert_textbox(
                box,
                new,
                fontsize=fs,
                fontname="helv",
                color=(0, 0, 0),
                align=fitz.TEXT_ALIGN_LEFT,
            )
            if rc < 0:
                page.insert_text(
                    (r.x0, r.y1 - 1.2),
                    new,
                    fontsize=fs,
                    fontname="helv",
                    color=(0, 0, 0),
                )
    return len(rects)


def _replace_any(
    page: fitz.Page,
    olds: list[str],
    new: str,
    *,
    fontsize: float = 9,
    max_width: float | None = None,
    expand: bool = True,
    baseline: bool = False,
) -> int:
    total = 0
    for old in olds:
        total += _replace_text(
            page,
            old,
            new,
            fontsize=fontsize,
            max_width=max_width,
            expand=expand,
            baseline=baseline,
        )
    return total


def _replace_many(
    page: fitz.Page,
    pairs: list[tuple[str, str]],
    *,
    fontsize: float = 9,
    max_width: float | None = None,
    expand: bool = True,
    baseline: bool = False,
) -> int:
    """
    Replace multiple strings in one wipe pass so packed PDF lines
    are not corrupted by sequential redactions.
    """
    jobs: list[tuple[fitz.Rect, str]] = []
    for old, new in pairs:
        if not old or not new or old == new:
            continue
        for h in page.search_for(old, quads=False):
            jobs.append((fitz.Rect(h), new))
    if not jobs:
        return 0

    for r, _new in jobs:
        wipe = fitz.Rect(r.x0 - 0.3, r.y0 + 0.4, r.x1 + 0.3, r.y1 - 0.4)
        if wipe.y1 <= wipe.y0:
            wipe = fitz.Rect(r.x0 - 0.2, r.y0, r.x1 + 0.2, r.y1)
        page.add_redact_annot(wipe, fill=(1, 1, 1))
    page.apply_redactions(images=0)

    for r, new in jobs:
        fs = min(fontsize, max(6.0, (r.y1 - r.y0) * 0.85))
        if expand:
            char_w = max(fs * 0.5, 3.8)
            width = max(r.width, len(new) * char_w + 2)
            if max_width is not None:
                width = min(width, max_width)
        if baseline:
            page.insert_text(
                (r.x0, r.y1 - 1.2),
                new,
                fontsize=fs,
                fontname="helv",
                color=(0, 0, 0),
            )
        else:
            box = fitz.Rect(
                r.x0,
                r.y0,
                min(page.rect.x1 - 8, r.x0 + (max_width or r.width * 2)),
                r.y1,
            )
            if box.height < fs + 1:
                box.y0 = box.y1 - (fs + 2)
            rc = page.insert_textbox(
                box,
                new,
                fontsize=fs,
                fontname="helv",
                color=(0, 0, 0),
                align=fitz.TEXT_ALIGN_LEFT,
            )
            if rc < 0:
                page.insert_text(
                    (r.x0, r.y1 - 1.2),
                    new,
                    fontsize=fs,
                    fontname="helv",
                    color=(0, 0, 0),
                )
    return len(jobs)


def _guess_fontsize(page: fitz.Page, sample: str, default: float = 9.0) -> float:
    if not sample:
        return default
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if sample in (span.get("text") or ""):
                    size = float(span.get("size") or default)
                    return size if size > 0 else default
    return default


def fill_pdf_invoice(pdf_path, data: WordInvoiceData, *, invoice_date: date | None = None) -> bytes:
    """
    Copy/fill a PDF invoice template and return PDF bytes.
    Replaces sample placeholder text with employee/club invoice values.
    """
    invoice_date = invoice_date or date.today()
    num = data.invoice_number
    tasks = list(data.tasks[:3])
    if len(tasks) < 3:
        raise ValueError("Need 3 line items to fill PDF invoice.")

    doc = fitz.open(pdf_path)
    try:
        page = doc[0]
        samples = SAMPLE_LINE_ITEMS[num]
        fs_item = _guess_fontsize(page, samples[0], 9)
        fs_amt = _guess_fontsize(page, SAMPLE_LINE_AMOUNTS[num][0], 9)
        fs_name = _guess_fontsize(page, SAMPLE_NAMES[num][0], 9)

        # Payment / header first so later line-item wipes cannot erase them.
        if num == 1:
            pairs = []
            for old, tmpl in INVOICE1_PAYMENT_LINES:
                new = tmpl.format(
                    name=data.person_name or "",
                    bank=data.bank or "",
                    iban=data.iban or "",
                    branch=data.branch_code or "",
                )
                if new.split(": ", 1)[-1]:
                    pairs.append((old, new))
            _replace_many(page, pairs, fontsize=fs_name, expand=True, baseline=True)
            if data.person_name and page.search_for("Hammad Hassan"):
                _replace_text(
                    page,
                    "Hammad Hassan",
                    data.person_name,
                    fontsize=fs_name,
                    expand=True,
                    baseline=True,
                )
        else:
            if data.person_name:
                _replace_any(
                    page,
                    SAMPLE_NAMES[num],
                    data.person_name,
                    fontsize=fs_name,
                    expand=True,
                    baseline=True,
                )
            if data.bank:
                _replace_any(
                    page,
                    SAMPLE_BANKS[num],
                    data.bank,
                    fontsize=fs_name,
                    expand=True,
                    baseline=True,
                )
            if data.iban:
                _replace_any(
                    page,
                    SAMPLE_IBANS[num],
                    data.iban,
                    fontsize=fs_name,
                    expand=True,
                    baseline=True,
                )
            if data.branch_code:
                _replace_any(
                    page,
                    SAMPLE_BRANCHES[num],
                    data.branch_code,
                    fontsize=fs_name,
                    expand=True,
                    baseline=True,
                )
        if data.document_invoice_no:
            _replace_any(
                page,
                SAMPLE_INVOICE_NOS[num],
                data.document_invoice_no,
                fontsize=fs_name,
                expand=True,
                baseline=True,
            )

        new_date = format_invoice_date(invoice_date)
        date_samples = {
            1: ["11-0-2026", "11-03-2026"],
            2: ["12 / 06 / 2025", "12 Jun 2025"],
            3: ["17 March 2025"],
            4: ["March 18, 2025"],
            5: ["18 / 04 / 2025", "18 April 2025"],
        }
        for sample in date_samples.get(num, []):
            if "/" in sample and sample.count("/") == 2:
                styled = (
                    f"{invoice_date.day:02d} / {invoice_date.month:02d} / {invoice_date.year}"
                )
                _replace_text(page, sample, styled, fontsize=fs_name, expand=True)
            elif re.search(r"(?i)jun|march|april", sample):
                styled = (
                    f"{invoice_date.day} {invoice_date.strftime('%b')} {invoice_date.year}"
                )
                _replace_text(page, sample, styled, fontsize=fs_name, expand=True)
            else:
                _replace_text(page, sample, new_date, fontsize=fs_name, expand=True)

        # Description column width cap keeps text out of amount/payment columns.
        desc_max = {
            1: 280,
            2: 260,
            3: 300,
            4: 220,
            5: 260,
        }.get(num, 250)

        for sample, task in zip(samples, tasks):
            _replace_text(
                page,
                sample,
                task.sub_task,
                fontsize=fs_item,
                max_width=desc_max,
                expand=True,
            )
        for sample, task in zip(SAMPLE_LINE_AMOUNTS[num], tasks):
            _replace_text(
                page,
                sample,
                format_amount(task.amount),
                fontsize=fs_amt,
                expand=True,
            )

        total_str = format_amount(data.total_amount)
        for sample in SAMPLE_TOTALS[num]:
            replacement = total_str
            if sample.startswith("$") and "," not in sample and sample.count(".") == 0:
                replacement = f"${data.total_amount:,}".replace(",", "")
                if sample == "$4301":
                    replacement = f"${data.total_amount}"
            _replace_text(page, sample, replacement, fontsize=fs_amt, expand=True)

        return doc.tobytes(deflate=True)
    finally:
        doc.close()
