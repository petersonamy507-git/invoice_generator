"""
Replace invoice_generation.clubing from ListOFservicesforInvoices Excel.

Each sheet department's Service Name rows are grouped into clubs of 3:
  "Item A | Item B | Item C"
Incomplete trailing groups (< 3 services) are skipped.
Accounts sheet maps to department Account.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend.app.db.connection import db_cursor
from backend.app.db.migrate import run_migrations

DEFAULT_XLSX = Path(
    r"d:\AI_Cache\temp\1791329418B-ListOFservicesforInvoices3 (2).xlsx"
)

SHEET_TO_DEPARTMENT = {
    "QA": "QA",
    "Devops": "Devops",
    "Call centre": "Call centre",
    "Call center": "Call centre",
    "Accounts": "Account",
    "Account": "Account",
    "HR": "HR",
}

DEPT_CLUB_PREFIX = {
    "QA": "QA",
    "Devops": "DEV",
    "Call centre": "CC",
    "Account": "ACC",
    "HR": "HR",
}


def _header_row_index(df: pd.DataFrame) -> int:
    for i in range(min(12, len(df))):
        vals = [
            str(x).strip().lower() if pd.notna(x) else ""
            for x in df.iloc[i].tolist()
        ]
        if "service name" in vals and ("sr#" in vals or "sr" in vals):
            return i
    raise ValueError("Could not find Service Name header row.")


def _service_names(df: pd.DataFrame) -> list[str]:
    hdr = _header_row_index(df)
    cols = [str(c).strip().lower() if pd.notna(c) else "" for c in df.iloc[hdr].tolist()]
    try:
        sn_col = cols.index("service name")
    except ValueError as e:
        raise ValueError(f"Service Name column missing; got {cols}") from e

    services: list[str] = []
    for i in range(hdr + 1, len(df)):
        raw = df.iloc[i, sn_col]
        if pd.isna(raw):
            continue
        name = str(raw).strip()
        if not name or name.lower() in {"nan", "service name", "grand total:"}:
            continue
        services.append(name)
    return services


def _clubs_from_services(services: list[str], department: str) -> list[tuple[str, str, str]]:
    prefix = DEPT_CLUB_PREFIX[department]
    rows: list[tuple[str, str, str]] = []
    club_n = 0
    for i in range(0, len(services) - 2, 3):
        trio = services[i : i + 3]
        if len(trio) < 3:
            break
        club_n += 1
        club_id = f"{prefix}{club_n:03d}"
        clubs = " | ".join(trio)
        rows.append((club_id, clubs, department))
    return rows


def import_from_services_workbook(xlsx_path: Path, *, replace: bool = True) -> int:
    if not xlsx_path.is_file():
        raise FileNotFoundError(xlsx_path)

    run_migrations()
    xl = pd.ExcelFile(xlsx_path)
    all_rows: list[tuple[str, str, str]] = []
    seen_ids: set[str] = set()

    for sheet in xl.sheet_names:
        dept = SHEET_TO_DEPARTMENT.get(sheet.strip())
        if not dept:
            print(f"Skip unknown sheet: {sheet!r}")
            continue
        df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
        services = _service_names(df)
        clubs = _clubs_from_services(services, dept)
        rem = len(services) % 3
        print(
            f"{sheet} -> {dept}: {len(services)} services -> "
            f"{len(clubs)} clubs"
            + (f" (skipped {rem} leftover)" if rem else "")
        )
        for club_id, clubs_text, department in clubs:
            if club_id in seen_ids:
                raise ValueError(f"Duplicate club_id generated: {club_id}")
            seen_ids.add(club_id)
            all_rows.append((club_id, clubs_text, department))

    if not all_rows:
        raise ValueError("No clubs parsed from workbook.")

    with db_cursor(commit=True) as cur:
        if replace:
            cur.execute("DELETE FROM clubing")
        for club_id, clubs_text, department in all_rows:
            cur.execute(
                """
                INSERT INTO clubing (club_id, clubs, department)
                VALUES (%s, %s, %s)
                """,
                (club_id, clubs_text, department),
            )
        cur.execute("SELECT COUNT(*) AS c FROM clubing")
        total = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT department, COUNT(*) AS c
            FROM clubing
            GROUP BY department
            ORDER BY department
            """
        )
        by_dept = cur.fetchall()

    print(f"Replaced clubing with {len(all_rows)} clubs from {xlsx_path.name}")
    print(f"clubing total rows: {total}")
    for r in by_dept:
        print(f"  {r['department']}: {r['c']}")
    # Show one sample
    print("sample:", all_rows[0][0], "=>", all_rows[0][1][:100], "...")
    return len(all_rows)


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    import_from_services_workbook(path, replace=True)
