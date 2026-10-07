# Phase 1 — Architecture Analysis (MySQL Upgrade)

## 1. Current architecture

| Layer | Tech / location |
|-------|-----------------|
| Backend | FastAPI (`backend/app/main.py`) |
| Models | Dataclasses in `backend/app/models.py` (`WordInvoiceData`, `InvoiceTask`) — **no DB** |
| Frontend | Static `frontend/index.html` + `app.js` + `styles.css` |
| Line items | Excel `Data/excel/ListOFservicesforInvoices_v.1.2.xlsx` via `category_tasks.py` |
| Invoice fill | `word_field_updater.py` + Word templates in `Data/word/` |
| PDF | DOCX → PDF via Word COM (`word_to_pdf.py`) |
| Download | ZIP of PDFs + history Excel (`zip_export.py`) |

**No MySQL usage today.** Employee/payment data currently comes from an uploaded current-month Excel sheet.

## 2. Files / modules involved

- `backend/app/main.py` — routes
- `backend/app/services/excel_parser.py` — bulk orchestration
- `backend/app/services/category_tasks.py` — department → Excel items
- `backend/app/services/task_assignment.py` — 3 unique line items / batch
- `backend/app/services/amount_distribution.py` — 40/25/35
- `backend/app/services/invoice_no_utils.py` — increment Invoice No.
- `backend/app/services/word_*` — template fill + PDF
- `frontend/*` — category + Excel upload UI
- MySQL DB `invoice_generation` already has empty `clubing` table

## 3. Current invoice-generation flow

```
Select category (QA/Devops/Call centre/Account/HR)
  → Upload current-month Excel (Name, Bank, IBAN, Branch, Invoice 1–5, Invoice No., Amount)
  → Load 3+ items from category Excel sheet
  → Assign 3 unique items per person (batch uniqueness)
  → Split amount 40/25/35
  → Increment Invoice No. for document
  → Fill Word template → PDF → ZIP download
```

## 4. Proposed MySQL schema

See migrations SQL in `backend/app/db/migrations/001_init.sql`.

- `employees` — PK `employee_id`, index `department`, soft-delete `is_active`
- `clubing` — existing table; add UNIQUE(`club_id`), index `department`
- `invoice_backup` — history + FKs; UNIQUE(`club_id`,`invoice_year`,`invoice_month`) for same-month rule

## 5. Proposed APIs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/employees?department=` | List active employees |
| GET | `/api/employees/{id}` | One employee |
| POST | `/api/employees` | Create |
| PUT | `/api/employees/{id}` | Update |
| DELETE | `/api/employees/{id}` | Soft delete |
| GET | `/api/clubbing?department=` | Clubs by department |
| POST | `/api/employees/generate` | Generate invoices for selected employees (JSON) |
| POST | `/api/bulk/generate` | **Kept** — existing Excel bulk path |

## 6. Club-assignment algorithm

1. Department clubs from `clubing`
2. Exclude clubs used by this employee in last N months of history (N = min(3, available months))
3. Exclude clubs used by anyone in current calendar month
4. Pick first eligible (deterministic by `s_no`/`club_id`)
5. If none → 400: “No eligible club is currently available for this employee.”

## 7. Concurrent same-month protection

- DB UNIQUE KEY on `(club_id, invoice_year, invoice_month)`
- Assign + insert inside a transaction with `SELECT … FOR UPDATE` on candidate club rows / retry on duplicate-key

## 8. Existing files to modify

- `requirements.txt`, `backend/app/main.py`
- `frontend/index.html`, `app.js`, `styles.css`
- `memory.md`

## 9. New files

- `.env.example`, `.env`
- `backend/app/db/` — connection, migrations, repositories
- `backend/app/services/club_assignment.py`
- `backend/app/services/employee_invoice_generate.py`
- `tests/test_employees_db.py`, `tests/test_club_assignment.py`

## 10. Ambiguities / risks / conflicts

1. **Club vs Excel line items:** Spec assigns **one club** per employee; invoices still need **3 line items**.  
   **Decision:** Keep Excel line items for Word/PDF content; assign **one DB club** for history/`invoice_backup`. Do not break PDF layout.
2. **`clubing` table is empty** — seed from category Excel Items (department-mapped) so assignment has data.
3. **Invoice template (1–5)** must be collected in UI (was Excel `Invoice` column).
4. **Invoice No. increment** preserved: user enters current sheet number; document gets +1; `last_invoice` stores document number.
5. Soft-delete employees so `invoice_backup` history stays intact.
6. Keep Excel bulk generate endpoint so old workflow still works.

Department labels stored as: `QA`, `Devops`, `Call centre`, `Account`, `HR`.
