"""DOCX → PDF conversion.

- Windows: Microsoft Word COM when available, else LibreOffice.
- Linux / AWS: LibreOffice headless (`soffice`) — Word/pywin32 are not available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.app.services.validation import ValidationError

WD_EXPORT_FORMAT_PDF = 17


def docx_filename_to_pdf(filename: str) -> str:
    path = Path(filename)
    return f"{path.stem}.pdf"


def _soffice_candidates() -> list[Path]:
    env = os.getenv("SOFFICE_PATH", "").strip()
    paths: list[Path] = []
    if env:
        paths.append(Path(env))
    which = shutil.which("soffice") or shutil.which("libreoffice")
    if which:
        paths.append(Path(which))
    paths.extend(
        [
            Path("/usr/bin/soffice"),
            Path("/usr/bin/libreoffice"),
            Path("/usr/lib/libreoffice/program/soffice"),
            Path("/opt/libreoffice/program/soffice"),
            Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
        ]
    )
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def find_soffice() -> Path | None:
    for path in _soffice_candidates():
        if path.is_file():
            return path
    return None


def _convert_via_libreoffice(items: list[tuple[bytes, str]]) -> list[tuple[bytes, str]]:
    soffice = find_soffice()
    if soffice is None:
        raise ValidationError(
            "PDF export needs LibreOffice on this server. "
            "On AWS/Linux install: sudo apt-get install -y libreoffice-writer "
            "(or set SOFFICE_PATH to the soffice binary). "
            "Microsoft Word/pywin32 only work on Windows."
        )

    results: list[tuple[bytes, str]] = []
    with tempfile.TemporaryDirectory(prefix="inv-pdf-") as tmp:
        tmpdir = Path(tmp)
        outdir = tmpdir / "out"
        outdir.mkdir()
        for index, (docx_bytes, filename) in enumerate(items):
            stem = f"invoice_{index}_{Path(filename).stem}"
            # LibreOffice rejects some characters in paths; keep stem simple.
            safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[
                :80
            ]
            docx_path = tmpdir / f"{safe_stem}.docx"
            docx_path.write_bytes(docx_bytes)

            cmd = [
                str(soffice),
                "--headless",
                "--nologo",
                "--nolockcheck",
                "--nodefault",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir.resolve()),
                str(docx_path.resolve()),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={**os.environ, "HOME": str(tmpdir)},
                )
            except subprocess.TimeoutExpired as e:
                raise ValidationError(
                    f"LibreOffice timed out converting '{filename}' to PDF."
                ) from e

            pdf_path = outdir / f"{safe_stem}.pdf"
            if not pdf_path.is_file():
                err = (proc.stderr or proc.stdout or "").strip()
                raise ValidationError(
                    f"Could not create PDF for '{filename}' via LibreOffice. {err}"
                )
            results.append((pdf_path.read_bytes(), docx_filename_to_pdf(filename)))
    return results


def _convert_via_word_com(items: list[tuple[bytes, str]]) -> list[tuple[bytes, str]]:
    try:
        import win32com.client
    except ImportError as e:
        raise ValidationError(
            "PDF export requires pywin32 and Microsoft Word on Windows."
        ) from e

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    results: list[tuple[bytes, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="inv-pdf-") as tmp:
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
    finally:
        try:
            word.Quit()
        except Exception:
            pass
    return results


def convert_docx_batch_to_pdf(items: list[tuple[bytes, str]]) -> list[tuple[bytes, str]]:
    """Convert generated .docx invoice bytes to PDF."""
    if not items:
        return []

    # Prefer Word on Windows for closest layout; LibreOffice everywhere else (AWS).
    if sys.platform.startswith("win"):
        try:
            return _convert_via_word_com(items)
        except ValidationError:
            if find_soffice() is not None:
                return _convert_via_libreoffice(items)
            raise
        except Exception:
            if find_soffice() is not None:
                return _convert_via_libreoffice(items)
            raise ValidationError(
                "Could not convert invoices to PDF. "
                "Install Microsoft Word or LibreOffice on this machine."
            )

    try:
        return _convert_via_libreoffice(items)
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            "Could not convert invoices to PDF via LibreOffice. "
            "On AWS/Linux: sudo apt-get install -y libreoffice-writer"
        ) from e
