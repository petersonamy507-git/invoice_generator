import tempfile
from pathlib import Path

from docx import Document

from backend.app.services.validation import ValidationError


def convert_doc_to_docx(doc_path: Path) -> Path:
    """Convert legacy .doc to .docx using Microsoft Word (Windows)."""
    try:
        import win32com.client
    except ImportError as e:
        raise ValidationError(
            "Invoice 1 template is a .doc file. Install pywin32 and Microsoft Word "
            "to process it, or save the template as .docx in Data/word/."
        ) from e

    doc_path = doc_path.resolve()
    tmp = Path(tempfile.mkdtemp()) / f"{doc_path.stem}.docx"

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        document = word.Documents.Open(str(doc_path))
        document.SaveAs2(str(tmp), FileFormat=16)
        document.Close()
    except Exception as e:
        raise ValidationError(
            f"Could not convert '{doc_path.name}' to docx. "
            "Ensure Microsoft Word is installed, or save the file as .docx."
        ) from e
    finally:
        word.Quit()

    return tmp


def open_template_document(template_path: Path) -> tuple[Document, Path | None]:
    """
    Open a Word template. Returns (document, temp_docx_path).
    temp_docx_path is set when a .doc was converted and should be deleted after use.
    """
    if template_path.suffix.lower() == ".doc":
        temp_path = convert_doc_to_docx(template_path)
        return Document(str(temp_path)), temp_path
    return Document(str(template_path)), None
