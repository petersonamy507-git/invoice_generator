from __future__ import annotations

from datetime import datetime
from typing import Any

import pymysql

from backend.app.db.connection import db_cursor, db_transaction
from backend.app.services.validation import ValidationError

VALID_DEPARTMENTS = ("QA", "Devops", "Call centre", "Account", "HR")


def normalize_department(department: str) -> str:
    raw = str(department or "").strip()
    aliases = {
        "qa": "QA",
        "devops": "Devops",
        "devops/qa": "Devops",
        "call_centre": "Call centre",
        "call centre": "Call centre",
        "call center": "Call centre",
        "account": "Account",
        "accounts": "Account",
        "hr": "HR",
        "sales": "Call centre",
        "sales staff": "Call centre",
    }
    key = raw.lower().replace("-", "_")
    label = aliases.get(key, raw)
    if label not in VALID_DEPARTMENTS:
        raise ValidationError(
            f"Invalid department {department!r}. "
            f"Choose one of: {', '.join(VALID_DEPARTMENTS)}."
        )
    return label


def _row_to_employee(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "employee_id": row["employee_id"],
        "name": row["name"],
        "department": row["department"],
        "iban": row["iban"],
        "bank_name": row["bank_name"],
        "branch_code": row.get("branch_code") or "",
        "last_invoice": row.get("last_invoice"),
        "is_active": bool(row.get("is_active", 1)),
        "created_at": row.get("created_at").isoformat(sep=" ")
        if isinstance(row.get("created_at"), datetime)
        else row.get("created_at"),
        "updated_at": row.get("updated_at").isoformat(sep=" ")
        if isinstance(row.get("updated_at"), datetime)
        else row.get("updated_at"),
    }


def list_employees(department: str | None = None, *, active_only: bool = True) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if active_only:
        clauses.append("is_active = 1")
    if department:
        clauses.append("department = %s")
        params.append(normalize_department(department))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT employee_id, name, department, iban, bank_name, branch_code,
               last_invoice, is_active, created_at, updated_at
        FROM employees
        {where}
        ORDER BY name ASC, employee_id ASC
    """
    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_row_to_employee(r) for r in rows]


def get_employee(employee_id: str, *, active_only: bool = False) -> dict:
    eid = str(employee_id or "").strip()
    if not eid:
        raise ValidationError("employee_id is required.")
    sql = """
        SELECT employee_id, name, department, iban, bank_name, branch_code,
               last_invoice, is_active, created_at, updated_at
        FROM employees
        WHERE employee_id = %s
    """
    with db_cursor() as cur:
        cur.execute(sql, (eid,))
        row = cur.fetchone()
    if not row:
        raise ValidationError(f"Employee {eid!r} not found.")
    if active_only and not row.get("is_active"):
        raise ValidationError(f"Employee {eid!r} is inactive.")
    return _row_to_employee(row)


def create_employee(payload: dict[str, Any]) -> dict:
    employee_id = str(payload.get("employee_id") or "").strip()
    name = str(payload.get("name") or "").strip()
    department = normalize_department(str(payload.get("department") or ""))
    iban = str(payload.get("iban") or "").strip()
    bank_name = str(payload.get("bank_name") or "").strip()
    branch_code = str(payload.get("branch_code") or "").strip()
    last_invoice = payload.get("last_invoice")
    last_invoice = str(last_invoice).strip() if last_invoice not in (None, "") else None

    if not employee_id:
        raise ValidationError("employee_id is required.")
    if not name:
        raise ValidationError("name is required.")
    if not iban:
        raise ValidationError("iban is required.")
    if not bank_name:
        raise ValidationError("bank_name is required.")

    sql = """
        INSERT INTO employees
          (employee_id, name, department, iban, bank_name, branch_code, last_invoice, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                sql,
                (employee_id, name, department, iban, bank_name, branch_code, last_invoice),
            )
    except pymysql.err.IntegrityError as e:
        raise ValidationError(
            f"Employee ID {employee_id!r} already exists."
        ) from e
    return get_employee(employee_id)


def update_employee(employee_id: str, payload: dict[str, Any]) -> dict:
    existing = get_employee(employee_id)
    name = str(payload.get("name", existing["name"]) or "").strip()
    department = normalize_department(
        str(payload.get("department", existing["department"]) or "")
    )
    iban = str(payload.get("iban", existing["iban"]) or "").strip()
    bank_name = str(payload.get("bank_name", existing["bank_name"]) or "").strip()
    branch_code = str(
        payload.get("branch_code", existing.get("branch_code") or "") or ""
    ).strip()
    if "last_invoice" in payload:
        raw_last = payload.get("last_invoice")
        last_invoice = (
            str(raw_last).strip() if raw_last not in (None, "") else None
        )
    else:
        last_invoice = existing.get("last_invoice")

    if not name:
        raise ValidationError("name is required.")
    if not iban:
        raise ValidationError("iban is required.")
    if not bank_name:
        raise ValidationError("bank_name is required.")

    sql = """
        UPDATE employees
        SET name = %s,
            department = %s,
            iban = %s,
            bank_name = %s,
            branch_code = %s,
            last_invoice = %s
        WHERE employee_id = %s AND is_active = 1
    """
    with db_cursor(commit=True) as cur:
        cur.execute(
            sql,
            (name, department, iban, bank_name, branch_code, last_invoice, employee_id),
        )
        if cur.rowcount == 0:
            raise ValidationError(
                f"Employee {employee_id!r} not found or is inactive."
            )
    return get_employee(employee_id)


def delete_employee(employee_id: str) -> dict:
    """Permanently remove employee and their invoice_backup history (FK RESTRICT)."""
    get_employee(employee_id)
    with db_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM invoice_backup WHERE employee_id = %s",
            (employee_id,),
        )
        cur.execute(
            "DELETE FROM employees WHERE employee_id = %s",
            (employee_id,),
        )
        if cur.rowcount == 0:
            raise ValidationError(f"Employee {employee_id!r} not found.")
    return {"employee_id": employee_id, "deleted": True}


def update_last_invoice(employee_id: str, invoice_no: str, cur=None) -> None:
    sql = "UPDATE employees SET last_invoice = %s WHERE employee_id = %s"
    if cur is not None:
        cur.execute(sql, (invoice_no, employee_id))
        return
    with db_cursor(commit=True) as c:
        c.execute(sql, (invoice_no, employee_id))
