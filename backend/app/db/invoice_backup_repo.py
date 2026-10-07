from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from backend.app.db.connection import db_cursor


def month_bounds(d: date) -> tuple[date, date]:
    start = date(d.year, d.month, 1)
    if d.month == 12:
        end = date(d.year + 1, 1, 1)
    else:
        end = date(d.year, d.month + 1, 1)
    return start, end


def clubs_used_in_month(year: int, month: int, cur=None) -> set[str]:
    sql = """
        SELECT club_id
        FROM invoice_backup
        WHERE invoice_year = %s AND invoice_month = %s
    """
    if cur is not None:
        cur.execute(sql, (year, month))
        rows = cur.fetchall() or []
    else:
        with db_cursor() as c:
            c.execute(sql, (year, month))
            rows = c.fetchall() or []
    return {str(r["club_id"]) for r in rows if r.get("club_id")}


def employee_assignment_months(
    employee_id: str,
    before_date: date,
    cur=None,
) -> list[tuple[int, int]]:
    """Distinct (year, month) of assignments strictly before before_date, newest first."""
    sql = """
        SELECT DISTINCT invoice_year, invoice_month
        FROM invoice_backup
        WHERE employee_id = %s
          AND invoice_date < %s
        ORDER BY invoice_year DESC, invoice_month DESC
    """
    if cur is not None:
        cur.execute(sql, (employee_id, before_date))
        rows = cur.fetchall() or []
    else:
        with db_cursor() as c:
            c.execute(sql, (employee_id, before_date))
            rows = c.fetchall() or []
    return [(int(r["invoice_year"]), int(r["invoice_month"])) for r in rows]


def employee_clubs_in_months(
    employee_id: str,
    months: list[tuple[int, int]],
    cur=None,
) -> set[str]:
    if not months:
        return set()
    clauses = " OR ".join(
        ["(invoice_year = %s AND invoice_month = %s)"] * len(months)
    )
    params: list[Any] = [employee_id]
    for y, m in months:
        params.extend([y, m])
    sql = f"""
        SELECT club_id
        FROM invoice_backup
        WHERE employee_id = %s
          AND ({clauses})
    """
    if cur is not None:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
    else:
        with db_cursor() as c:
            c.execute(sql, params)
            rows = c.fetchall() or []
    return {str(r["club_id"]) for r in rows if r.get("club_id")}


def insert_invoice_backup(record: dict[str, Any], cur) -> int:
    line_items = record.get("line_items")
    line_json = json.dumps(line_items) if line_items is not None else None
    cur.execute(
        """
        INSERT INTO invoice_backup (
          employee_id, department, club_id, club_name,
          invoice_template, sheet_invoice_no, document_invoice_no,
          amount, invoice_date, invoice_year, invoice_month, line_items_json
        ) VALUES (
          %s, %s, %s, %s,
          %s, %s, %s,
          %s, %s, %s, %s, %s
        )
        """,
        (
            record["employee_id"],
            record["department"],
            record["club_id"],
            record.get("club_name"),
            record["invoice_template"],
            record["sheet_invoice_no"],
            record["document_invoice_no"],
            record["amount"],
            record["invoice_date"],
            record["invoice_year"],
            record["invoice_month"],
            line_json,
        ),
    )
    return int(cur.lastrowid)


def list_invoice_history(
    employee_id: str | None = None,
    department: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if employee_id:
        clauses.append("employee_id = %s")
        params.append(employee_id)
    if department:
        clauses.append("department = %s")
        params.append(department)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(int(limit), 500)))
    sql = f"""
        SELECT id, employee_id, department, club_id, club_name,
               invoice_template, sheet_invoice_no, document_invoice_no,
               amount, invoice_date, invoice_year, invoice_month, created_at
        FROM invoice_backup
        {where}
        ORDER BY invoice_date DESC, id DESC
        LIMIT %s
    """
    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("invoice_date"), date):
            item["invoice_date"] = item["invoice_date"].isoformat()
        if isinstance(item.get("created_at"), datetime):
            item["created_at"] = item["created_at"].isoformat(sep=" ")
        out.append(item)
    return out
