"""Import All_Clubs_Single_Sheet_With_SNo.xlsx into invoice_generation.clubing."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend.app.db.connection import db_cursor
from backend.app.db.migrate import run_migrations

DEFAULT_XLSX = Path(r"d:\AI_Cache\temp\All_Clubs_Single_Sheet_With_SNo (1).xlsx")

DEPARTMENT_MAP = {
    "qa": "QA",
    "devops": "Devops",
    "call centre": "Call centre",
    "call center": "Call centre",
    "call_centre": "Call centre",
    "accounts": "Account",
    "account": "Account",
    "hr": "HR",
}


def _normalize_department(value: str) -> str:
    key = str(value or "").strip().lower()
    if key not in DEPARTMENT_MAP:
        raise ValueError(f"Unknown department in sheet: {value!r}")
    return DEPARTMENT_MAP[key]


def _find_column(columns, *candidates: str) -> str:
    lowered = {str(c).strip().lower(): c for c in columns}
    for name in candidates:
        if name in lowered:
            return lowered[name]
    raise ValueError(f"Missing column. Looked for {candidates}, got {list(columns)}")


def import_clubs(xlsx_path: Path, *, replace: bool = True) -> int:
    if not xlsx_path.is_file():
        raise FileNotFoundError(xlsx_path)

    run_migrations()
    df = pd.read_excel(xlsx_path)
    sno_col = _find_column(df.columns, "s.no", "s_no", "sno", "sr#", "sr")
    club_id_col = _find_column(df.columns, "club_id", "club id")
    clubs_col = _find_column(df.columns, "clubs", "club")
    dept_col = _find_column(df.columns, "department", "dept")

    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        club_id = str(row[club_id_col]).strip() if pd.notna(row[club_id_col]) else ""
        clubs = str(row[clubs_col]).strip() if pd.notna(row[clubs_col]) else ""
        dept_raw = row[dept_col] if pd.notna(row[dept_col]) else ""
        if not club_id or not clubs:
            continue
        if club_id.lower() == "nan" or clubs.lower() == "nan":
            continue
        if club_id in seen:
            raise ValueError(f"Duplicate Club_ID in sheet: {club_id}")
        seen.add(club_id)
        department = _normalize_department(str(dept_raw))
        rows.append((club_id, clubs, department))

    with db_cursor(commit=True) as cur:
        if replace:
            # Keep invoice_backup intact; clubing FK is not enforced to clubing.
            cur.execute("DELETE FROM clubing")
        for club_id, clubs, department in rows:
            cur.execute(
                """
                INSERT INTO clubing (club_id, clubs, department)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  clubs = VALUES(clubs),
                  department = VALUES(department)
                """,
                (club_id, clubs, department),
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

    print(f"Imported {len(rows)} clubs from {xlsx_path.name}")
    print(f"clubing total rows: {total}")
    for r in by_dept:
        print(f"  {r['department']}: {r['c']}")
    return len(rows)


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    import_clubs(path, replace=True)
