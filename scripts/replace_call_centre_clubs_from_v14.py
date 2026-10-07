"""Replace only Call centre rows in clubing from ListOFservicesforInvoices_v1.4.xlsx.

Same logic as replace_clubing_from_services_excel:
group Service Name rows into clubs of 3 joined by ' | ', IDs CC001+.
Other departments are left untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend.app.db.connection import db_cursor
from backend.app.db.migrate import run_migrations
from scripts.replace_clubing_from_services_excel import (
    SHEET_TO_DEPARTMENT,
    _clubs_from_services,
    _service_names,
)

DEFAULT_XLSX = ROOT / "Data" / "excel" / "ListOFservicesforInvoices_v1.4.xlsx"
DEPARTMENT = "Call centre"


def replace_call_centre_clubs(xlsx_path: Path) -> int:
    if not xlsx_path.is_file():
        raise FileNotFoundError(xlsx_path)

    run_migrations()
    xl = pd.ExcelFile(xlsx_path)
    sheet = None
    for name in xl.sheet_names:
        if name.strip().lower() in {"call centre", "call center"}:
            sheet = name
            break
    if not sheet:
        raise ValueError(f"No Call centre sheet in {xl.sheet_names}")

    dept = SHEET_TO_DEPARTMENT[sheet.strip()]
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
    services = _service_names(df)
    clubs = _clubs_from_services(services, dept)
    rem = len(services) % 3
    print(
        f"{sheet} -> {dept}: {len(services)} services -> {len(clubs)} clubs"
        + (f" (skipped {rem} leftover)" if rem else "")
    )
    if not clubs:
        raise ValueError("No Call centre clubs parsed from workbook.")

    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT COUNT(*) AS c FROM clubing WHERE department = %s",
            (DEPARTMENT,),
        )
        before = int(cur.fetchone()["c"])
        cur.execute("DELETE FROM clubing WHERE department = %s", (DEPARTMENT,))
        print(f"Deleted {before} existing {DEPARTMENT} clubs")

        for club_id, clubs_text, department in clubs:
            cur.execute(
                """
                INSERT INTO clubing (club_id, clubs, department)
                VALUES (%s, %s, %s)
                """,
                (club_id, clubs_text, department),
            )

        cur.execute(
            "SELECT COUNT(*) AS c FROM clubing WHERE department = %s",
            (DEPARTMENT,),
        )
        after = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT department, COUNT(*) AS c
            FROM clubing
            GROUP BY department
            ORDER BY department
            """
        )
        by_dept = cur.fetchall()
        cur.execute(
            """
            SELECT club_id, clubs
            FROM clubing
            WHERE department = %s
            ORDER BY club_id
            LIMIT 3
            """,
            (DEPARTMENT,),
        )
        samples = cur.fetchall()
        cur.execute(
            """
            SELECT club_id, clubs
            FROM clubing
            WHERE department = %s
            ORDER BY club_id DESC
            LIMIT 2
            """,
            (DEPARTMENT,),
        )
        tails = cur.fetchall()

    print(f"Inserted {after} {DEPARTMENT} clubs from {xlsx_path.name}")
    for r in by_dept:
        print(f"  {r['department']}: {r['c']}")
    print("first:")
    for r in samples:
        print(f"  {r['club_id']}: {r['clubs']}")
    print("last:")
    for r in tails:
        print(f"  {r['club_id']}: {r['clubs']}")
    return after


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    replace_call_centre_clubs(path)
