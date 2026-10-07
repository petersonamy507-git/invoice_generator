import json
from pathlib import Path

from backend.app.services.validation import ValidationError

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "pdf"
POSITIONS_FILE = TEMPLATE_DIR / "field_positions.json"

TEMPLATE_FILENAMES = {
    1: "invoice_structure_1.pdf",
    2: "invoice_structure_2.pdf",
    3: "invoice_structure_3.pdf",
    4: "invoice_structure_4.pdf",
}

def template_path(structure_number: int) -> Path:
    filename = TEMPLATE_FILENAMES.get(structure_number)
    if not filename:
        raise ValidationError(f"Invalid invoice structure number: {structure_number}")
    return TEMPLATE_DIR / filename


def ensure_template_exists(structure_number: int) -> Path:
    path = template_path(structure_number)
    if not path.is_file():
        raise ValidationError(
            f"PDF template for structure {structure_number} is not uploaded. "
            f"Please upload '{path.name}' to backend/templates/pdf/ "
            f"or use the template upload API."
        )
    return path


def list_template_status() -> dict[int, bool]:
    return {n: template_path(n).is_file() for n in range(1, 5)}


def save_template(structure_number: int, content: bytes) -> Path:
    if structure_number not in TEMPLATE_FILENAMES:
        raise ValidationError("Invoice structure number must be between 1 and 4.")
    if not content.startswith(b"%PDF"):
        raise ValidationError("Uploaded file is not a valid PDF.")
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    path = template_path(structure_number)
    path.write_bytes(content)
    return path


def load_field_positions(structure_number: int) -> dict:
    if not POSITIONS_FILE.is_file():
        return _default_positions().get(str(structure_number), {})
    with open(POSITIONS_FILE, encoding="utf-8") as f:
        all_positions = json.load(f)
    key = str(structure_number)
    if key not in all_positions:
        return _default_positions().get(key, {})
    return all_positions[key]


def _default_positions() -> dict:
    """Fallback coordinates (points, origin top-left) for US Letter–sized templates."""
    base_fields = {
        "person_name": {"x": 72, "y": 130, "font_size": 11},
        "company_name": {"x": 72, "y": 148, "font_size": 11},
        "email": {"x": 72, "y": 166, "font_size": 10},
        "invoice_date": {"x": 400, "y": 130, "font_size": 10},
        "total_amount": {"x": 400, "y": 680, "font_size": 12},
    }
    base_tasks = {
        "main_task": {"x": 72},
        "sub_task": {"x": 220},
        "amount": {"x": 460},
        "start_y": 320,
        "row_height": 22,
        "font_size": 10,
    }
    return {str(i): {"page": 0, "fields": base_fields, "tasks": base_tasks} for i in range(1, 5)}


def save_default_positions_file() -> None:
    """Write default field_positions.json if missing (for user calibration)."""
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    if not POSITIONS_FILE.exists():
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_default_positions(), f, indent=2)
