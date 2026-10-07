import tempfile
from pathlib import Path

from docx import Document

from backend.app.services.libreoffice import convert_with_libreoffice
from backend.app.services.validation import ValidationError


def convert_doc_to_docx(doc_path: Path) -> Path:
    """Convert legacy .doc to .docx using LibreOffice."""
    doc_path = doc_path.resolve()
    tmp = Path(tempfile.mkdtemp()) / f"{doc_path.stem}.docx"

    try:
        convert_with_libreoffice([doc_path], tmp.parent, "docx")
        if not tmp.is_file():
            raise ValidationError(
                f"LibreOffice did not create a docx file for '{doc_path.name}'."
            )
    except ValidationError as e:
        raise ValidationError(
            f"Could not convert '{doc_path.name}' to docx using LibreOffice: {e}"
        ) from e
    except Exception as e:
        raise ValidationError(
            f"Could not convert '{doc_path.name}' to docx using LibreOffice."
        ) from e

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
