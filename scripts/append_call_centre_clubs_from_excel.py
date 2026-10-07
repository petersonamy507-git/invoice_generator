"""Append Call centre clubs from Excel rows 71-102 (3 services per club)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend.app.db.connection import db_cursor
from backend.app.db.migrate import run_migrations

DEFAULT_XLSX = ROOT / "Data" / "excel" / "ListOFservicesforInvoices_v1.3..xlsx"
DEPARTMENT = "Call centre"
PREFIX = "CC"
# Excel 1-based inclusive row numbers
ROW_START = 71
ROW_END = 102


def _find_sheet(xl: pd.ExcelFile) -> str:
    for name in xl.sheet_names:
        key = name.strip().lower()
        if key in {"call centre", "call center"}:
            return name
    raise ValueError(f"No Call centre/center sheet in {xl.sheet_names}")


def _header_and_service_col(df: pd.DataFrame) -> tuple[int, int]:
    for i in range(min(12, len(df))):
        vals = [
            str(x).strip().lower() if pd.notna(x) else ""
            for x in df.iloc[i].tolist()
        ]
        if "service name" in vals:
            return i, vals.index("service name")
    raise ValueError("Service Name header not found")


def _services_from_excel_rows(df: pd.DataFrame, start: int, end: int) -> list[str]:
    _, sn_col = _header_and_service_col(df)
    services: list[str] = []
    # Convert Excel 1-based rows to 0-based iloc
    for excel_row in range(start, end + 1):
        i = excel_row - 1
        if i < 0 or i >= len(df):
            continue
        raw = df.iloc[i, sn_col]
        if pd.isna(raw):
            continue
        name = str(raw).strip()
        if not name or name.lower() in {"nan", "service name"}:
            continue
        services.append(name)
    return services


def _next_club_number(cur) -> int:
    cur.execute(
        """
        SELECT club_id
        FROM clubing
        WHERE department = %s AND club_id REGEXP %s
        """,
        (DEPARTMENT, f"^{PREFIX}[0-9]+$"),
    )
    max_n = 0
    for row in cur.fetchall() or []:
        m = re.search(r"(\d+)$", str(row["club_id"]))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def append_call_centre_clubs(
    xlsx_path: Path,
    *,
    row_start: int = ROW_START,
    row_end: int = ROW_END,
) -> int:
    if not xlsx_path.is_file():
        raise FileNotFoundError(xlsx_path)

    run_migrations()
    xl = pd.ExcelFile(xlsx_path)
    sheet = _find_sheet(xl)
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
    services = _services_from_excel_rows(df, row_start, row_end)
    print(f"Sheet {sheet!r}: Excel rows {row_start}-{row_end} -> {len(services)} services")

    clubs: list[tuple[str, str]] = []
    for i in range(0, len(services) - 2, 3):
        trio = services[i : i + 3]
        clubs.append((" | ".join(trio),))

    rem = len(services) % 3
    if rem:
        print(f"Skipping {rem} leftover service(s) not forming a full club of 3")

    with db_cursor(commit=True) as cur:
        next_n = _next_club_number(cur)
        inserted = 0
        for offset, (clubs_text,) in enumerate(clubs):
            club_id = f"{PREFIX}{next_n + offset:03d}"
            cur.execute(
                """
                INSERT INTO clubing (club_id, clubs, department)
                VALUES (%s, %s, %s)
                """,
                (club_id, clubs_text, DEPARTMENT),
            )
            print(f"  {club_id}: {clubs_text}")
            inserted += 1

        cur.execute(
            "SELECT COUNT(*) AS c FROM clubing WHERE department = %s",
            (DEPARTMENT,),
        )
        total = int(cur.fetchone()["c"])

    print(f"Inserted {inserted} Call centre clubs; department total now {total}")
    return inserted


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    append_call_centre_clubs(path)
