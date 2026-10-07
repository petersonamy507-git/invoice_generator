from io import BytesIO

import fitz

from backend.app.models import InvoiceData
from backend.app.services.pdf_templates import ensure_template_exists, load_field_positions
from backend.app.services.validation import ValidationError


def _format_amount(amount: int) -> str:
    return f"${amount:,}"


def _format_date(invoice_date) -> str:
    return invoice_date.strftime("%b %d, %Y")


def _task_form_keys(index: int) -> dict[str, str]:
    n = index + 1
    return {
        "main": f"task_{n}_main",
        "sub": f"task_{n}_sub",
        "amount": f"task_{n}_amount",
    }


def _fill_acroform(doc: fitz.Document, invoice: InvoiceData) -> bool:
    """Fill PDF form widgets when template defines matching field names."""
    values = {
        "person_name": invoice.person_name,
        "company_name": invoice.company_name,
        "email": invoice.email,
        "invoice_date": _format_date(invoice.invoice_date),
        "total_amount": _format_amount(invoice.total_amount),
    }
    for i, task in enumerate(invoice.tasks):
        keys = _task_form_keys(i)
        values[keys["main"]] = task.main_task
        values[keys["sub"]] = task.sub_task
        values[keys["amount"]] = _format_amount(task.amount)

    filled_count = 0
    for page in doc:
        for widget in page.widgets() or []:
            name = widget.field_name
            if not name:
                continue
            normalized = name.strip().lower()
            if normalized in values:
                widget.field_value = str(values[normalized])
                widget.update()
                filled_count += 1

    return filled_count > 0


def _insert_text(page: fitz.Page, x: float, y: float, text: str, font_size: float) -> None:
    if not text:
        return
    page.insert_text(
        (x, y),
        text,
        fontsize=font_size,
        fontname="helv",
        color=(0, 0, 0),
    )


def _fill_coordinates(doc: fitz.Document, invoice: InvoiceData, positions: dict) -> None:
    page_index = positions.get("page", 0)
    if page_index >= len(doc):
        raise ValidationError(f"Template has no page at index {page_index}.")
    page = doc[page_index]

    fields = positions.get("fields", {})
    date_str = _format_date(invoice.invoice_date)
    data = {
        "person_name": invoice.person_name,
        "company_name": invoice.company_name,
        "email": invoice.email,
        "invoice_date": date_str,
        "total_amount": _format_amount(invoice.total_amount),
    }
    for key, value in data.items():
        pos = fields.get(key)
        if pos:
            _insert_text(page, pos["x"], pos["y"], value, pos.get("font_size", 11))

    tasks_cfg = positions.get("tasks", {})
    if not tasks_cfg:
        return

    start_y = tasks_cfg.get("start_y", 320)
    row_height = tasks_cfg.get("row_height", 22)
    font_size = tasks_cfg.get("font_size", 10)
    main_x = tasks_cfg.get("main_task", {}).get("x", 72)
    sub_x = tasks_cfg.get("sub_task", {}).get("x", 220)
    amount_x = tasks_cfg.get("amount", {}).get("x", 460)

    for i, task in enumerate(invoice.tasks):
        y = start_y + i * row_height
        _insert_text(page, main_x, y, task.main_task, font_size)
        _insert_text(page, sub_x, y, task.sub_task, font_size)
        _insert_text(page, amount_x, y, _format_amount(task.amount), font_size)


def generate_invoice_pdf(invoice: InvoiceData) -> bytes:
    template_path = ensure_template_exists(invoice.structure_number)
    doc = fitz.open(template_path)

    try:
        used_form = _fill_acroform(doc, invoice)
        if not used_form:
            positions = load_field_positions(invoice.structure_number)
            if not (positions.get("fields") or positions.get("tasks")):
                raise ValidationError(
                    f"Template '{template_path.name}' has no fillable form fields. "
                    "Add AcroForm fields (see backend/templates/pdf/README.md) or "
                    "configure backend/templates/pdf/field_positions.json."
                )
            _fill_coordinates(doc, invoice, positions)

        buffer = BytesIO()
        doc.save(buffer, garbage=4, deflate=True)
        return buffer.getvalue()
    finally:
        doc.close()
