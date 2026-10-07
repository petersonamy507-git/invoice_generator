# Invoice Generation System

Generate PDF invoices manually or in bulk from Excel uploads. Uses **your uploaded PDF files** as invoice templates (structures 1–4), with automatic task assignment and amount distribution (40% / 25% / 35%).

## PDF templates (required before generating invoices)

Upload four branded PDF templates:

| Structure | File |
|-----------|------|
| 1 | `invoice_structure_1.pdf` |
| 2 | `invoice_structure_2.pdf` |
| 3 | `invoice_structure_3.pdf` |
| 4 | `invoice_structure_4.pdf` |

**Option A — Web UI:** Open the app → **PDF Templates** tab → upload each file.

**Option B — Copy files to:** `backend/templates/pdf/`

**Option C — API:** `POST /api/templates/upload` with `invoice_structure_number` and `file`.

See [backend/templates/pdf/README.md](backend/templates/pdf/README.md) for how data is placed on your PDFs (form fields vs coordinates).

For local testing only, generate placeholder templates:

```bash
.venv\Scripts\python scripts\create_blank_pdf_templates.py
```

## Setup

### Windows

```bash
cd d:\Invoice_finance
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Install LibreOffice Writer on the Windows machine that runs Uvicorn. If `soffice`
is not on `PATH`, add its executable to `.env` and restart the backend:

```dotenv
SOFFICE_PATH="C:\\Program Files\\LibreOffice\\program\\soffice.exe"
```

### Linux / Ubuntu

Install LibreOffice Writer and the Python runtime before installing the app:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libreoffice-writer fontconfig fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-noto-core
cd /path/to/Invoice_finance
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

LibreOffice is used for HTML/DOC/DOCX conversions. Install the fonts used by the
invoice templates on the server as well; missing fonts can change line wrapping,
spacing, and pagination. Confirm a template font resolves with `fc-match`.

### Docker deployment

The included `Dockerfile` installs LibreOffice Writer and font substitutes in
the runtime image. Build and run it with:

```bash
docker build -t invoice-finance .
docker run --rm -p 8000:8000 --env-file .env invoice-finance
```

Configure `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` for a MySQL server
reachable from the container. `127.0.0.1` inside the container is the container
itself, not the host or a separate database server. Keep `.env` and SQL data
dumps out of the image and Git repository.

The included Linux font packages provide compatible substitutes, not Microsoft's
exact Arial/Calibri/Cambria/Georgia/Tahoma/Trebuchet fonts. Install the exact
licensed fonts used by the templates for closer layout fidelity. LibreOffice can
still differ slightly from Microsoft Word; verify generated PDFs against the
reference PDFs before production use.

## Run

Windows:

```bash
.venv\Scripts\python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Linux / Ubuntu:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Sample Excel files

```bash
.venv\Scripts\python scripts\create_sample_excel.py
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/templates/status` | GET | Which templates are uploaded |
| `/api/templates/upload` | POST (multipart) | Upload a PDF template |
| `/api/manual/generate` | POST (form) | Single filled PDF |
| `/api/word-test/templates` | GET | Word template status |
| `/api/word-test/generate` | POST (multipart) | Update dates in Word files (test) |

## Word invoice testing (date only)

Place your 5 Word templates in `Data/word/`:

| Invoice | File |
|---------|------|
| 1 | `Invoice01-MAXISTECHNOLOGIESINC11.docx` |
| 2 | `Invoice02-ForestTechInc1.docx` |
| 3 | `Invoice03-RadnorInnovationsInc.docx` |
| 4 | `Invoice04-FusionfolioMediaInc.docx` |
| 5 | `Invoice05-DynamoCreativesInc.docx` |

Upload an Excel sheet with column **Invoice** (values 1–5). The system updates the invoice date to today and saves copies to `Data/word/output/`, then returns a ZIP.

Sample Excel:

```bash
.venv\Scripts\python scripts\create_word_test_excel.py
```

Use the **Word Test** tab in the UI or `POST /api/word-test/generate`.

**Note:** Templates with the word **Dated** are updated directly. The current test files use varied labels (e.g. `INVOICE DATE:`, `Date:`, table Date column, `Pay by:`) and are handled automatically per template.

## Tests

```bash
.venv\Scripts\python tests\test_core.py
```
