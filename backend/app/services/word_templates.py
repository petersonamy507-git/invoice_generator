from pathlib import Path

from backend.app.services.validation import ValidationError

WORD_DIR = Path(__file__).resolve().parents[3] / "Data" / "word"
WORD_OUTPUT_DIR = WORD_DIR / "output"

INVOICE_WORD_MAP = {
    1: "Invoice1-MAXIS",
    2: "Invoice02-ForestTechInc1",
    3: "Invoice03-RadnorInnovationsInc",
    4: "Invoice04-APPFOUNDERSINC",
    5: "Invoice05-DynamoCreativesInc",
    6: "Invoice06-RavotekInc",
    7: "Invoice07-IgnitaiInc",
    8: "Invoice08-CoretechifyInc",
    9: "Invoice09-EcomifyInc",
    10: "Invoice10-CozyHomeEssentials",
    11: "Invoice11-BeecodifyInc",
    12: "Invoice12-BravixTechnologiesInc",
    13: "Invoice13-AlphaDigitalInc",
    14: "Invoice14-SynergoInc",
}

MAX_INVOICE_TEMPLATE = max(INVOICE_WORD_MAP)


def validate_invoice_number(value, context: str = "") -> int:
    try:
        num = int(float(value))
    except (TypeError, ValueError) as e:
        raise ValidationError(
            f"{context}Invoice column must be an integer between 1 and {MAX_INVOICE_TEMPLATE}."
        ) from e
    if num not in INVOICE_WORD_MAP:
        raise ValidationError(
            f"{context}Invoice must be between 1 and {MAX_INVOICE_TEMPLATE} (got {num})."
        )
    return num


def _candidate_paths(base: str) -> list[Path]:
    """Return possible paths, including filenames with a space before the extension."""
    paths: list[Path] = []
    for ext in (".docx", ".doc"):
        paths.append(WORD_DIR / f"{base}{ext}")
        paths.append(WORD_DIR / f"{base} {ext}")  # e.g. "Invoice1-MAXIS .docx"
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def template_path(invoice_number: int) -> Path:
    base = INVOICE_WORD_MAP[invoice_number]
    for path in _candidate_paths(base):
        if path.is_file():
            return path

    # Case-insensitive / trimmed match against files in the word folder
    if WORD_DIR.is_dir():
        target = base.strip().lower()
        for path in WORD_DIR.iterdir():
            if not path.is_file():
                continue
            stem = path.stem.strip().lower()
            if stem == target and path.suffix.lower() in (".docx", ".doc"):
                return path

    return WORD_DIR / f"{base}.docx"


def template_filename(invoice_number: int) -> str:
    return template_path(invoice_number).name


def ensure_template_exists(invoice_number: int) -> Path:
    path = template_path(invoice_number)
    if not path.is_file():
        base = INVOICE_WORD_MAP[invoice_number]
        raise ValidationError(
            f"Word template not found for Invoice {invoice_number} "
            f"(expected like {base}.docx or '{base} .docx'). "
            f"Place it in {WORD_DIR}"
        )
    return path
