from io import BytesIO
from pathlib import Path

import pandas as pd

from backend.app.services.validation import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2].parent
SERVICES_EXCEL_PATH = PROJECT_ROOT / "Data" / "excel" / "ListOFservicesforInvoices_v.1.2.xlsx"

CATEGORIES: dict[str, str] = {
    "qa": "QA",
    "devops": "Devops",
    "call_centre": "Call centre",
    "account": "Account",
    "hr": "HR",
}

# category key -> dedicated Excel sheet name
_CATEGORY_SHEET_CONFIG: dict[str, str] = {
    "qa": "QA",
    "devops": "Devops",
    "call_centre": "Call centre",
    "account": "Accounts",
    "hr": "HR",
}


def normalize_category(category: str) -> str:
    key = str(category or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "callcentre": "call_centre",
        "call_center": "call_centre",
        "callcenter": "call_centre",
        "accounts": "account",
        "sales": "call_centre",
        "sales_staff": "call_centre",
    }
    key = aliases.get(key, key)
    if key not in CATEGORIES:
        labels = ", ".join(CATEGORIES.values())
        raise ValidationError(
            f"Invalid category {category!r}. Choose one of: {labels}."
        )
    return key


def _excel_sheet_names() -> list[str]:
    if not SERVICES_EXCEL_PATH.is_file():
        return []
    try:
        return pd.ExcelFile(
            BytesIO(SERVICES_EXCEL_PATH.read_bytes())
        ).sheet_names
    except Exception:
        return []


def _resolve_sheet_name(sheet_name: str) -> str:
    available = _excel_sheet_names()
    if not available:
        return sheet_name

    if sheet_name in available:
        return sheet_name

    target = sheet_name.strip().lower()
    for name in available:
        if name.strip().lower() == target:
            return name

    raise ValidationError(
        f"Sheet {sheet_name!r} not found in {SERVICES_EXCEL_PATH.name}. "
        f"Available sheets: {', '.join(available)}."
    )


def _find_header_row(raw: pd.DataFrame) -> int:
    for i, row in raw.iterrows():
        values = {str(v).strip().lower() for v in row if pd.notna(v)}
        if "items" in values:
            return int(i)
    raise ValidationError("Could not find header row with Items column.")


def _find_column(columns, target: str) -> str | None:
    target_lower = target.strip().lower()
    for col in columns:
        if str(col).strip().lower() == target_lower:
            return col
    return None


def _read_service_sheet(sheet_name: str) -> pd.DataFrame:
    if not SERVICES_EXCEL_PATH.is_file():
        raise ValidationError(
            f"Services list not found: {SERVICES_EXCEL_PATH}. "
            "Place ListOFservicesforInvoices_v.1.2.xlsx in Data/excel/."
        )

    resolved_sheet = _resolve_sheet_name(sheet_name)
    try:
        raw = pd.read_excel(
            BytesIO(SERVICES_EXCEL_PATH.read_bytes()),
            sheet_name=resolved_sheet,
            header=None,
        )
    except Exception as e:
        raise ValidationError(
            f"Could not read sheet {resolved_sheet!r} from "
            f"{SERVICES_EXCEL_PATH.name}: {e}"
        ) from e

    header_row = _find_header_row(raw)
    df = pd.read_excel(
        BytesIO(SERVICES_EXCEL_PATH.read_bytes()),
        sheet_name=resolved_sheet,
        header=header_row,
    )
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _items_tasks_dataframe(sheet_name: str) -> pd.DataFrame:
    df = _read_service_sheet(sheet_name)

    items_col = _find_column(df.columns, "items")
    if not items_col:
        raise ValidationError(
            f"Sheet {sheet_name!r} in {SERVICES_EXCEL_PATH.name} has no Items column."
        )

    category_col = _find_column(df.columns, "category")
    sub_category_col = None
    if category_col:
        for col in df.columns:
            if col != category_col and str(col).lower().startswith("category"):
                sub_category_col = col
                break

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        item = row.get(items_col)
        if pd.isna(item) or not str(item).strip():
            continue
        sub_task = str(item).strip()
        key = sub_task.lower()
        if key in seen:
            continue
        seen.add(key)

        if sub_category_col and pd.notna(row.get(sub_category_col)):
            main_task = str(row[sub_category_col]).strip()
        elif category_col and pd.notna(row.get(category_col)):
            main_task = str(row[category_col]).strip()
        else:
            main_task = sheet_name

        rows.append({"main_task": main_task, "sub_task": sub_task})

    if len(rows) < 3:
        raise ValidationError(
            f"Not enough items for sheet {sheet_name!r} in {SERVICES_EXCEL_PATH.name} "
            f"(need at least 3, found {len(rows)})."
        )

    return pd.DataFrame(rows)


def load_category_tasks_df(category: str) -> pd.DataFrame:
    key = normalize_category(category)
    sheet_name = _CATEGORY_SHEET_CONFIG[key]
    return _items_tasks_dataframe(sheet_name)


def categories_status() -> dict:
    file_exists = SERVICES_EXCEL_PATH.is_file()
    categories: dict[str, dict] = {}
    for key, label in CATEGORIES.items():
        sheet_name = _CATEGORY_SHEET_CONFIG[key]
        ready = False
        item_count = 0
        resolved_sheet = sheet_name
        if file_exists:
            try:
                resolved_sheet = _resolve_sheet_name(sheet_name)
                df = _items_tasks_dataframe(sheet_name)
                item_count = len(df)
                ready = item_count >= 3
            except ValidationError:
                ready = False
        categories[key] = {
            "label": label,
            "sheet": resolved_sheet,
            "item_count": item_count,
            "ready": ready,
        }
    return {
        "file": str(SERVICES_EXCEL_PATH),
        "filename": SERVICES_EXCEL_PATH.name,
        "exists": file_exists,
        "categories": categories,
    }
