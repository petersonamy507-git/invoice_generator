import tempfile
from pathlib import Path

from backend.app.services.validation import ValidationError

# Word constant: wdExportFormatPDF
WD_EXPORT_FORMAT_PDF = 17


def _word_application():
    try:
        import win32com.client
    except ImportError as e:
        raise ValidationError(
            "PDF export requires pywin32 and Microsoft Word on Windows."
        ) from e
    return win32com.client.Dispatch("Word.Application")


def docx_filename_to_pdf(filename: str) -> str:
    path = Path(filename)
    return f"{path.stem}.pdf"


def convert_docx_batch_to_pdf(items: list[tuple[bytes, str]]) -> list[tuple[bytes, str]]:
    """Convert generated .docx invoice bytes to PDF using one Word session."""
    if not items:
        return []

    word = _word_application()
    word.Visible = False
    results: list[tuple[bytes, str]] = []

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for index, (docx_bytes, filename) in enumerate(items):
                stem = f"invoice_{index}_{Path(filename).stem}"
                docx_path = tmpdir / f"{stem}.docx"
                pdf_path = tmpdir / f"{stem}.pdf"
                docx_path.write_bytes(docx_bytes)

                document = word.Documents.Open(str(docx_path.resolve()))
                try:
                    document.ExportAsFixedFormat(
                        OutputFileName=str(pdf_path.resolve()),
                        ExportFormat=WD_EXPORT_FORMAT_PDF,
                        OpenAfterExport=False,
                    )
                finally:
                    document.Close(False)

                if not pdf_path.is_file():
                    raise ValidationError(
                        f"Could not create PDF for '{filename}'. "
                        "Ensure Microsoft Word is installed."
                    )
                results.append((pdf_path.read_bytes(), docx_filename_to_pdf(filename)))
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            "Could not convert invoices to PDF. Ensure Microsoft Word is installed."
        ) from e
    finally:
        word.Quit()

    return results
