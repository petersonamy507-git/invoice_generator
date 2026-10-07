import tempfile
from io import BytesIO
from pathlib import Path

from backend.app.services.libreoffice import convert_with_libreoffice
from backend.app.services.validation import ValidationError


def convert_html_to_docx_bytes(html_path: Path) -> bytes:
    """
    Convert an HTML invoice template with LibreOffice and return .docx bytes.
    Companion *_files folders must sit beside the .html for images.
    """
    html_path = html_path.resolve()
    if not html_path.is_file():
        raise ValidationError(f"HTML template not found: {html_path}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_docx = Path(tmp) / f"{html_path.stem.strip()}.docx"
        try:
            convert_with_libreoffice([html_path], tmp_docx.parent, "docx")
        except ValidationError as e:
            raise ValidationError(
                f"Could not convert HTML template '{html_path.name}' "
                f"using LibreOffice: {e}"
            ) from e
        if not tmp_docx.is_file():
            raise ValidationError(
                f"LibreOffice did not create a docx file for '{html_path.name}'."
            )
        return tmp_docx.read_bytes()


def document_from_html_template(html_path: Path):
    """Return a python-docx Document loaded from the HTML template via Word."""
    from docx import Document

    return Document(BytesIO(convert_html_to_docx_bytes(html_path)))
