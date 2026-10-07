from __future__ import annotations

from datetime import date

import pymysql

from backend.app.db.invoice_backup_repo import (
    clubs_used_in_month,
    employee_assignment_months,
    employee_clubs_in_months,
)
from backend.app.services.validation import ValidationError


def parse_club_line_items(clubs_text: str) -> list[str]:
    """
    Split clubing.clubs into exactly 3 invoice line items.
    Expected format: 'Item A | Item B | Item C'
    """
    text = str(clubs_text or "").strip()
    if not text:
        raise ValidationError("Club has empty clubs text.")
    parts = [p.strip() for p in text.split("|")]
    parts = [p for p in parts if p]
    if len(parts) != 3:
        raise ValidationError(
            f"Club packages must contain exactly 3 items separated by ' | ' "
            f"(found {len(parts)}): {text!r}"
        )
    return parts


def history_window_months(
    employee_id: str,
    as_of: date,
    cur=None,
    max_months: int = 3,
) -> list[tuple[int, int]]:
    """
    Preferred: previous 3 months of assignment history.
    Fallback: 2 months, then 1 month, then empty.
    Uses distinct months that actually have records (newest first).
    """
    months = employee_assignment_months(employee_id, as_of, cur=cur)
    return months[:max_months]


def eligible_clubs_for_employee(
    *,
    employee_id: str,
    department: str,
    department_clubs: list[dict],
    as_of: date,
    cur=None,
    extra_excluded_club_ids: set[str] | None = None,
) -> list[dict]:
    history_months = history_window_months(employee_id, as_of, cur=cur)
    personal_excluded = employee_clubs_in_months(
        employee_id, history_months, cur=cur
    )
    month_excluded = clubs_used_in_month(as_of.year, as_of.month, cur=cur)
    batch_excluded = extra_excluded_club_ids or set()

    blocked = personal_excluded | month_excluded | batch_excluded
    eligible: list[dict] = []
    for c in department_clubs:
        club_id = str(c.get("club_id") or "").strip()
        if not club_id or club_id in blocked:
            continue
        try:
            parse_club_line_items(str(c.get("clubs") or ""))
        except ValidationError:
            continue
        eligible.append(c)
    return eligible


def assign_club_for_employee(
    *,
    employee_id: str,
    department: str,
    as_of: date,
    cur,
    extra_excluded_club_ids: set[str] | None = None,
) -> dict:
    """
    Lock department clubs, pick an eligible club_id using invoice_backup history.
    Rules:
      - only clubs for this department
      - exclude clubs this employee used in last 1-3 history months
      - exclude clubs used by anyone in the current month (unique club_id/month)
    """
    cur.execute(
        """
        SELECT s_no, club_id, clubs, department
        FROM clubing
        WHERE department = %s
        ORDER BY s_no ASC
        FOR UPDATE
        """,
        (department,),
    )
    clubs = cur.fetchall() or []
    if not clubs:
        raise ValidationError(
            f"No clubs configured for department {department!r}."
        )

    eligible = eligible_clubs_for_employee(
        employee_id=employee_id,
        department=department,
        department_clubs=clubs,
        as_of=as_of,
        cur=cur,
        extra_excluded_club_ids=extra_excluded_club_ids,
    )
    if not eligible:
        raise ValidationError(
            f"No eligible club is currently available for employee {employee_id!r}."
        )
    chosen = eligible[0]
    line_items = parse_club_line_items(str(chosen["clubs"]))
    return {
        "s_no": chosen["s_no"],
        "club_id": chosen["club_id"],
        "clubs": chosen["clubs"],
        "department": chosen["department"],
        "line_items": line_items,
    }


def assert_club_insert_ok(exc: Exception, club_id: str) -> None:
    if isinstance(exc, pymysql.err.IntegrityError):
        raise ValidationError(
            f"Club {club_id!r} was already assigned this month "
            "(concurrent assignment blocked)."
        ) from exc
    raise exc
