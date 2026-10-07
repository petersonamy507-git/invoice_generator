# Invoice Finance — Project Memory

Summary of architecture, business logic, and solutions used in this project.

---

## 1. Purpose

Bulk (and optional manual) invoice generation system:

1. User selects a **staff category** (QA, Devops, Call centre, Account, HR).
2. Uploads **current month** payment sheet only.
3. System assigns **3 unique line items** per person from that category’s Excel sheet.
4. Fills the matching **Word template** in `Data/word/` (Invoice 1–5), converts to **PDF** via Word (same look as your PDF samples), and returns a **ZIP**.

---

## 2. Stack & Run

| Layer | Tech |
|-------|------|
| API | FastAPI (`backend/app/main.py`) |
| Excel | pandas + openpyxl |
| Word fill | python-docx |
| PDF | LibreOffice headless (`soffice`) — DOC/DOCX/HTML conversion and DOCX → PDF |
| UI | Static `frontend/` (HTML/JS/CSS) |

**Run (from project root `D:\Invoice_finance`):**

```powershell
.venv\Scripts\activate
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Open: http://127.0.0.1:8000

Do **not** run from `backend/` with `app.main:app` — imports use the `backend` package and will fail with `ModuleNotFoundError: No module named 'backend'`.

---

## 3. Main User Flow (Bulk)

```
Category button → Upload current month sheet only
       ↓
Load items from category sheet in ListOFservicesforInvoices_v.1.2.xlsx
       ↓
Assign 3 tasks/person (unique within this batch)
       ↓
Split amount 40% / 25% / 35% (shuffled)
       ↓
Fill Word template by Invoice column (1–5) → convert to PDF
       ↓
ZIP = PDFs + history Excel files for this month's assignments
```

**Primary API:** `POST /api/bulk/generate`  
Form fields: `category`, `current_month`  
(No last-3-months history upload — generation is based on the current month sheet only.)

**UI tabs used:** Bulk Invoice + Word Templates status.  
(Manual / payment-bulk / word-test endpoints may still exist in the API but are not primary UI.)

---

## 4. Categories & Items Sheet

**File:** `Data/excel/ListOFservicesforInvoices_v.1.2.xlsx`

| Frontend label | API key | Excel sheet |
|----------------|---------|-------------|
| QA | `qa` | `QA` |
| Devops | `devops` | `Devops` |
| Call centre | `call_centre` | `Call centre` |
| Account | `account` | `Accounts` |
| HR | `hr` | `HR` |

**Logic (`category_tasks.py`):**

- Auto-detect header row (looks for an **Items** column).
- Take unique values from **Items** as `sub_task`.
- Use Category / second Category column as `main_task` when present.
- Sheet names resolved case-insensitively.
- Status endpoint: `GET /api/categories/status`.

---

## 5. Task Assignment Rules

**File:** `backend/app/services/task_assignment.py`

| Rule | Behavior |
|------|----------|
| Items per invoice | Exactly **3** |
| Batch uniqueness | Same item **cannot** go to two people in one upload |
| History exclusion | Currently **disabled** in bulk UI (no history upload). Assignment still supports exclusion if history is provided in code. |
| Failure | Clear `ValidationError` if fewer than 3 eligible items remain |

Implementation detail: `batch_used_subtasks` set tracks items already taken in the current run.

Earlier design allowed the same item for up to 3 people; that was changed so **each invoice in a batch gets different items**.

---

## 6. Amount Distribution

**File:** `backend/app/services/amount_distribution.py`

- Fixed ratios: **40% / 25% / 35%**
- Order of percentages is **shuffled** per invoice.
- Third amount = remainder so the three amounts always sum exactly to the sheet **Amount**.

---

## 7. Current Month Sheet (Upload)

Required columns (conceptually):

| Column | Use |
|--------|-----|
| Name | Person on invoice |
| Bank | Payment details |
| IBAN NO. | Payment details |
| Branch Code | Written on all invoice templates |
| Invoice | Template number **1–5** |
| Invoice No. | e.g. `HH-007` → written as **incremented** value on document (`HH-008`) |
| Amount | Total to split across 3 line items |

---

## 8. History Sheet (Output Only for Now)

Bulk upload **no longer requires** a last-3-months history file.

**ZIP still includes two Excel files** built from this run's assignments:

1. **`invoice_history_full_…xlsx`** — track record starting from this month (and expandable later).
2. **`invoice_history_last_3_months_…xlsx`** — Name + latest months for this run.

Both include:

- Current month column, e.g. `Jun,26` (items assigned this run).
- Current month invoice-no column, e.g. `Jun Invoice No.` (incremented number used on the PDF).

Month labels use short names: `Mon,YY` (e.g. `Jun,26`, `Sep,26`).

---

## 9. Word Templates → PDF

**Templates folder:** `Data/word/` Word files are the generation source (fonts/layout match your PDF exports). Templates **1–14** (original 5 + Ravotek/Ignitai/Coretechify/Ecomify/CozyHome/Beecodify/Bravix/AlphaDigital/Synergo). `all_templates/` holds HTML/PDF previews only.

| Invoice # | Base filename |
|-----------|----------------|
| 1 | `Invoice1-MAXIS .docx` (space before `.docx` supported) |
| 2 | `Invoice02-ForestTechInc1` |
| 3 | `Invoice03-RadnorInnovationsInc` |
| 4 | `Invoice04-APPFOUNDERSINC` |
| 5 | `Invoice05-DynamoCreativesInc` |

Extensions `.docx` or `.doc` are accepted.

**Fill logic:** `word_field_updater.py` + per-template table indices in `word_template_config.py`:

| Invoice | Items table index | Notes |
|---------|-------------------|--------|
| 1 | table 1 | Amounts in items table |
| 2 | table 1, rows 5–7 | Subtotal/total handling |
| 3 | table 1 | Preserve layout; payment/summary tables separate |
| 4 | table 2 | Grand total in table 3; careful header spacing |
| 5 | table 1 | Standard line items |

**PDF conversion:** Word COM automation (`word_to_pdf.py`) — requires Microsoft Word on Windows.

---

## 10. Invoice Number Logic

**File:** `invoice_no_utils.py`

- Sheet value (e.g. `HH-007`) is **incremented by 1** for what is written on the invoice document.
- Incremented value is stored in history under `{Month} Invoice No.`.

---

## 11. Key Backend Modules

| Module | Role |
|--------|------|
| `main.py` | FastAPI routes, static frontend |
| `category_tasks.py` | Category → Excel sheet → items |
| `excel_parser.py` | Parse uploads, orchestrate bulk Word invoices |
| `task_assignment.py` | History + batch uniqueness + 3 tasks |
| `amount_distribution.py` | 40/25/35 split |
| `word_templates.py` | Template path map (1–5) |
| `word_field_updater.py` | Write fields into Word tables/paragraphs |
| `word_template_config.py` | Locked table/row/column layout per invoice |
| `word_to_pdf.py` | DOCX → PDF via Word |
| `history_tracker.py` | Build full + last-3-months Excel |
| `zip_export.py` | Package PDFs + history files |
| `validation.py` | Column/value validation errors |

---

## 12. Frontend Behavior

- Category buttons set hidden `category` field.
- Category status list loaded from `/api/categories/status` (item counts per sheet).
- Bulk form posts to `/api/bulk/generate` and downloads the ZIP.
- Word Templates tab checks which of the 5 templates exist on disk.

---

## 13. Solutions / Decisions Worth Remembering

1. **Word templates, not ReportLab layouts** — preserve company branding; fill existing DOCX then convert to PDF.
2. **Category-driven item catalogs** — one master Excel with dedicated sheets; frontend category picks the sheet.
3. **Batch-unique items** — prevents identical line items across people in the same upload.
4. **3-month history exclusion** — person does not get the same item again within the rolling window of uploaded history.
5. **Two history outputs** — full archive for audit + slim last-3-months file for next month’s upload.
6. **Invoice No. increment on document only** — sheet holds previous number; document/history store next number.
7. **Template-specific table indices** — each invoice structure has different table layout; configs are locked per invoice.
8. **Always run uvicorn from repo root** with `backend.app.main:app`.

---

## 14. Data Locations

```
Data/
  excel/ListOFservicesforInvoices_v.1.2.xlsx   # category items (5 sheets)
  word/                                       # Invoice1…Invoice05 templates
frontend/                                     # UI
backend/app/                                  # API + services
tests/                                        # category, assignment, layout tests
```

---

## 15. Quick Checklist When Something Breaks

| Symptom | Check |
|---------|--------|
| `No module named 'backend'` | Run from `D:\Invoice_finance`, use `backend.app.main:app` |
| Category not ready | Confirm `ListOFservicesforInvoices_v.1.2.xlsx` exists and sheet names match |
| Template not found | Confirm HTML under `all_templates/` matches `INVOICE_HTML_MAP` |
| Not enough eligible tasks | Need ≥ 3 unused items per person after history + batch rules |
| PDF fails | Install LibreOffice Writer and ensure `soffice` is on PATH; install template fonts |

---

## 16. MySQL upgrade (Oct 2026)

Persistent storage in DB `invoice_generation` (see `ANALYSIS_MYSQL_UPGRADE.md`).

| Table | Purpose |
|-------|---------|
| `employees` | Employee master (soft-delete via `is_active`) |
| `clubing` | Department clubs (seeded from Excel Items) |
| `invoice_backup` | Invoice + club history; UNIQUE(`club_id`,`invoice_year`,`invoice_month`) |

**Primary UI:** Employees tab — select department → load employees → select rows → amount/invoice no/template → Generate.

**Club rules:** 3-month employee exclusion (fallback 2/1/0) + same-month global exclusion; concurrent protection via unique key + `FOR UPDATE`.

**Club → invoice lines:** `clubing.clubs` holds 3 items separated by ` | `; after `club_id` assignment via `invoice_backup`, those become the 3 Word/PDF line items (one per row).

**Preserved:** Excel bulk generate (`/api/bulk/generate`), Word templates, invoice no increment, PDF ZIP download. Employee generate uses MySQL clubs (not Excel catalog).

Config: `.env` (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).

Seed clubs: `python scripts/seed_clubing_from_excel.py`  
Replace clubs from services workbook (groups of 3): `python scripts/replace_clubing_from_services_excel.py [path.xlsx]`

