import tempfile
from io import BytesIO
from pathlib import Path

from backend.app.services.validation import ValidationError

# Word: wdFormatXMLDocument / wdFormatDocumentDefault
WD_FORMAT_DOCX = 16


def convert_html_to_docx_bytes(html_path: Path) -> bytes:
    """
    Open an HTML invoice template in Microsoft Word and return .docx bytes.
    Companion *_files folders must sit beside the .html for images.
    """
    try:
        import win32com.client
    except ImportError as e:
        raise ValidationError(
            "HTML invoice generation requires pywin32 and Microsoft Word on Windows."
        ) from e

    html_path = html_path.resolve()
    if not html_path.is_file():
        raise ValidationError(f"HTML template not found: {html_path}")

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_docx = tmp_dir / f"{html_path.stem.strip()}.docx"
    try:
        document = word.Documents.Open(str(html_path))
        try:
            document.SaveAs2(str(tmp_docx.resolve()), FileFormat=WD_FORMAT_DOCX)
        finally:
            document.Close(False)
        if not tmp_docx.is_file():
            raise ValidationError(
                f"Could not convert HTML template '{html_path.name}' to Word format."
            )
        return tmp_docx.read_bytes()
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            f"Could not open HTML template '{html_path.name}'. "
            "Ensure Microsoft Word is installed."
        ) from e
    finally:
        word.Quit()
        try:
            if tmp_docx.exists():
                tmp_docx.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


def document_from_html_template(html_path: Path):
    """Return a python-docx Document loaded from the HTML template via Word."""
    from docx import Document

    return Document(BytesIO(convert_html_to_docx_bytes(html_path)))
