# Invoice PDF Templates

Place your four template PDFs in this folder:

| Structure | Filename |
|-----------|----------|
| 1 | `invoice_structure_1.pdf` |
| 2 | `invoice_structure_2.pdf` |
| 3 | `invoice_structure_3.pdf` |
| 4 | `invoice_structure_4.pdf` |

You can also upload them from the web UI (**Invoice Templates** tab) or via `POST /api/templates/upload`.

## Filling data onto templates

The system keeps your template design unchanged and only adds dynamic data in two ways:

### Option A — PDF form fields (recommended)

Add AcroForm text fields to your PDF with these names:

- `person_name`, `company_name`, `email`, `invoice_date`, `total_amount`
- `task_1_main`, `task_1_sub`, `task_1_amount`
- `task_2_main`, `task_2_sub`, `task_2_amount`
- `task_3_main`, `task_3_sub`, `task_3_amount`

### Option B — Coordinate overlay

Edit `field_positions.json` in this folder. Coordinates are in PDF points from the **top-left** of the page. Adjust `x`, `y`, and `start_y` until text aligns with the blank areas on each template.

Per-structure keys: `"1"`, `"2"`, `"3"`, `"4"`.

List form field names in an uploaded PDF:

```bash
python scripts/list_pdf_fields.py backend/templates/pdf/invoice_structure_1.pdf
```
