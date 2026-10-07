import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.app.services.validation import ValidationError


def convert_with_libreoffice(
    input_paths: list[Path], output_dir: Path, target_format: str
) -> None:
    """Convert files with an isolated headless LibreOffice profile."""
    if not input_paths:
        return

    executable = (
        os.environ.get("SOFFICE_PATH")
        or shutil.which("soffice")
        or shutil.which("libreoffice")
    )
    if not executable:
        raise ValidationError(
            "LibreOffice was not found. Install LibreOffice Writer and ensure "
            "'soffice' is on PATH, or set SOFFICE_PATH."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="libreoffice-profile-") as profile:
        command = [
            executable,
            "--headless",
            f"-env:UserInstallation={Path(profile).as_uri()}",
            "--convert-to",
            target_format,
            "--outdir",
            str(output_dir.resolve()),
            *(str(path.resolve()) for path in input_paths),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValidationError(
                f"LibreOffice timed out while converting files to {target_format}."
            ) from exc
        except OSError as exc:
            raise ValidationError("Could not start LibreOffice.") from exc

    if result.returncode:
        details = (result.stderr or result.stdout).strip()
        message = f"LibreOffice failed to convert files to {target_format}."
        if details:
            message = f"{message} {details}"
        raise ValidationError(message)