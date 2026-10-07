"""Import employee Excel into invoice_generation.employees."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend.app.db.connection import db_cursor
from backend.app.db.migrate import run_migrations

DEFAULT_XLSX = Path(r"d:\AI_CACHE\temp\1791243256J-EmployeeDataforPSEB3.xlsx")

DEPARTMENT_MAP = {
    "qa": "QA",
    "devops": "Devops",
    "call centre": "Call centre",
    "call center": "Call centre",
    "call_centre": "Call centre",
    "sale": "Call centre",
    "sales": "Call centre",
    "sales staff": "Call centre",
    "accounts": "Account",
    "account": "Account",
    "hr": "HR",
}


def _normalize_department(value: str) -> str:
    key = str(value or "").strip().lower()
    if key not in DEPARTMENT_MAP:
        raise ValueError(f"Unknown department: {value!r}")
    return DEPARTMENT_MAP[key]


def _find_column(columns, *candidates: str) -> str:
    lowered = {str(c).strip().lower(): c for c in columns}
    for name in candidates:
        if name in lowered:
            return lowered[name]
    raise ValueError(f"Missing column. Looked for {candidates}, got {list(columns)}")


def _cell_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _generated_employee_id(name: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").upper()
    if not base:
        base = "UNKNOWN"
    base = base[:40]
    candidate = f"GEN-{base}"
    n = 2
    while candidate in used:
        candidate = f"GEN-{base}-{n}"
        n += 1
    return candidate


def import_employees(xlsx_path: Path, *, replace: bool = False) -> dict:
    if not xlsx_path.is_file():
        raise FileNotFoundError(xlsx_path)

    run_migrations()
    df = pd.read_excel(xlsx_path)
    id_col = _find_column(df.columns, "employee id", "employee_id", "id")
    name_col = _find_column(df.columns, "name")
    dept_col = _find_column(df.columns, "department", "dept")
    iban_col = _find_column(df.columns, "iban", "iban no.", "iban_no")
    bank_col = _find_column(df.columns, "bank name", "bank_name", "bank")
    branch_col = _find_column(df.columns, "branch code", "branch_code", "branch")
    last_col = None
    try:
        last_col = _find_column(df.columns, "last invoice", "last_invoice")
    except ValueError:
        last_col = None

    rows: list[tuple] = []
    used_ids: set[str] = set()
    generated = 0
    skipped = 0

    for _, row in df.iterrows():
        name = _cell_text(row[name_col])
        iban = _cell_text(row[iban_col])
        bank = _cell_text(row[bank_col])
        branch = _cell_text(row[branch_col])
        last_invoice = _cell_text(row[last_col]) if last_col else ""
        dept_raw = _cell_text(row[dept_col])
        employee_id = _cell_text(row[id_col])

        if not name or not iban or not bank or not dept_raw:
            skipped += 1
            continue

        if not employee_id:
            employee_id = _generated_employee_id(name, used_ids)
            generated += 1

        if employee_id in used_ids:
            skipped += 1
            continue
        used_ids.add(employee_id)

        department = _normalize_department(dept_raw)
        rows.append(
            (
                employee_id,
                name,
                department,
                iban,
                bank,
                branch or None,
                last_invoice or None,
            )
        )

    with db_cursor(commit=True) as cur:
        if replace:
            cur.execute("DELETE FROM invoice_backup")
            cur.execute("DELETE FROM employees")
        for item in rows:
            cur.execute(
                """
                INSERT INTO employees
                  (employee_id, name, department, iban, bank_name, branch_code, last_invoice, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                  name = VALUES(name),
                  department = VALUES(department),
                  iban = VALUES(iban),
                  bank_name = VALUES(bank_name),
                  branch_code = VALUES(branch_code),
                  last_invoice = VALUES(last_invoice),
                  is_active = 1
                """,
                item,
            )
        cur.execute("SELECT COUNT(*) AS c FROM employees WHERE is_active = 1")
        total = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT department, COUNT(*) AS c
            FROM employees
            WHERE is_active = 1
            GROUP BY department
            ORDER BY department
            """
        )
        by_dept = cur.fetchall()

    print(f"Imported/updated {len(rows)} employees from {xlsx_path.name}")
    print(f"Generated missing employee_id for {generated} rows")
    print(f"Skipped {skipped} rows")
    print(f"Active employees total: {total}")
    for r in by_dept:
        print(f"  {r['department']}: {r['c']}")
    return {"imported": len(rows), "generated_ids": generated, "skipped": skipped, "total": total}


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    replace = "--replace" in sys.argv
    import_employees(path, replace=replace)
