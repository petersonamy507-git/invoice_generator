import tempfile
from pathlib import Path

from backend.app.services.libreoffice import convert_with_libreoffice
from backend.app.services.validation import ValidationError


def docx_filename_to_pdf(filename: str) -> str:
    path = Path(filename)
    return f"{path.stem}.pdf"


def convert_docx_batch_to_pdf(items: list[tuple[bytes, str]]) -> list[tuple[bytes, str]]:
    """Convert generated .docx invoice bytes to PDF using LibreOffice."""
    if not items:
        return []

    results: list[tuple[bytes, str]] = []

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            input_paths: list[Path] = []
            output_paths: list[tuple[Path, str]] = []
            for index, (docx_bytes, filename) in enumerate(items):
                stem = f"invoice_{index}_{Path(filename).stem}"
                docx_path = tmpdir / f"{stem}.docx"
                pdf_path = tmpdir / f"{stem}.pdf"
                docx_path.write_bytes(docx_bytes)
                input_paths.append(docx_path)
                output_paths.append((pdf_path, filename))

            convert_with_libreoffice(input_paths, tmpdir, "pdf")

            for pdf_path, filename in output_paths:
                if not pdf_path.is_file():
                    raise ValidationError(
                        f"LibreOffice did not create a PDF for '{filename}'."
                    )
                results.append((pdf_path.read_bytes(), docx_filename_to_pdf(filename)))
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            "Could not convert invoices to PDF with LibreOffice."
        ) from e

    return results
