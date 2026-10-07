from __future__ import annotations

from typing import Any

from backend.app.db.connection import db_cursor
from backend.app.db.employees_repo import normalize_department
from backend.app.services.validation import ValidationError


def list_clubs(department: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if department:
        where = "WHERE department = %s"
        params.append(normalize_department(department))
    sql = f"""
        SELECT s_no, club_id, clubs, department
        FROM clubing
        {where}
        ORDER BY s_no ASC
    """
    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
    return [
        {
            "s_no": r["s_no"],
            "club_id": r["club_id"],
            "clubs": r["clubs"],
            "department": r["department"],
        }
        for r in rows
    ]


def get_club(club_id: str) -> dict[str, Any]:
    cid = str(club_id or "").strip()
    if not cid:
        raise ValidationError("club_id is required.")
    with db_cursor() as cur:
        cur.execute(
            "SELECT s_no, club_id, clubs, department FROM clubing WHERE club_id = %s",
            (cid,),
        )
        row = cur.fetchone()
    if not row:
        raise ValidationError(f"Club {cid!r} not found.")
    return {
        "s_no": row["s_no"],
        "club_id": row["club_id"],
        "clubs": row["clubs"],
        "department": row["department"],
    }


def count_clubs() -> int:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM clubing")
        return int(cur.fetchone()["c"])


def insert_club(club_id: str, clubs: str, department: str) -> None:
    dept = normalize_department(department)
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO clubing (club_id, clubs, department)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              clubs = VALUES(clubs),
              department = VALUES(department)
            """,
            (club_id, clubs, dept),
        )
