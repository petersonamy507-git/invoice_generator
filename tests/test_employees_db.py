import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db.migrate import run_migrations
from backend.app.db.employees_repo import (
    create_employee,
    list_employees,
    delete_employee,
    update_employee,
)
from backend.app.db.clubing_repo import insert_club, list_clubs
from backend.app.db.connection import db_cursor
from backend.app.services.club_assignment import assign_club_for_employee, eligible_clubs_for_employee
from backend.app.services.validation import ValidationError


def _cleanup(employee_ids: list[str]):
    with db_cursor(commit=True) as cur:
        for eid in employee_ids:
            cur.execute("DELETE FROM invoice_backup WHERE employee_id = %s", (eid,))
            cur.execute("DELETE FROM employees WHERE employee_id = %s", (eid,))


def test_employee_crud_and_department_filter():
    run_migrations()
    eid = "TEST-EMP-001"
    _cleanup([eid])
    created = create_employee(
        {
            "employee_id": eid,
            "name": "Test User",
            "department": "QA",
            "iban": "PK00TEST",
            "bank_name": "Test Bank",
            "branch_code": "001",
        }
    )
    assert created["employee_id"] == eid
    qa = list_employees("QA")
    assert any(e["employee_id"] == eid for e in qa)

    updated = update_employee(eid, {"name": "Test User Updated", "bank_name": "HBL"})
    assert updated["name"] == "Test User Updated"
    assert updated["bank_name"] == "HBL"

    delete_employee(eid)
    qa2 = list_employees("QA")
    assert all(e["employee_id"] != eid for e in qa2)
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM employees WHERE employee_id = %s", (eid,)
        )
        assert cur.fetchone()["n"] == 0
    _cleanup([eid])


def test_duplicate_employee_rejected():
    run_migrations()
    eid = "TEST-EMP-DUP"
    _cleanup([eid])
    create_employee(
        {
            "employee_id": eid,
            "name": "Dup",
            "department": "HR",
            "iban": "PK11",
            "bank_name": "Bank",
        }
    )
    try:
        create_employee(
            {
                "employee_id": eid,
                "name": "Dup2",
                "department": "HR",
                "iban": "PK22",
                "bank_name": "Bank",
            }
        )
        assert False, "expected ValidationError"
    except ValidationError as e:
        assert "already exists" in str(e)
    _cleanup([eid])


def test_club_assignment_excludes_same_month():
    run_migrations()
    insert_club("TEST-CLUB-A", "Club A", "QA")
    insert_club("TEST-CLUB-B", "Club B", "QA")
    e1, e2 = "TEST-EMP-C1", "TEST-EMP-C2"
    _cleanup([e1, e2])
    for eid, name in [(e1, "A"), (e2, "B")]:
        create_employee(
            {
                "employee_id": eid,
                "name": name,
                "department": "QA",
                "iban": "PK",
                "bank_name": "Bank",
            }
        )

    today = date(2026, 10, 5)
    with db_cursor(commit=True) as cur:
        club1 = assign_club_for_employee(
            employee_id=e1, department="QA", as_of=today, cur=cur
        )
        cur.execute(
            """
            INSERT INTO invoice_backup (
              employee_id, department, club_id, club_name, invoice_template,
              sheet_invoice_no, document_invoice_no, amount, invoice_date,
              invoice_year, invoice_month
            ) VALUES (%s,%s,%s,%s,1,'X-001','X-002',1000,%s,%s,%s)
            """,
            (
                e1,
                "QA",
                club1["club_id"],
                club1["clubs"],
                today,
                today.year,
                today.month,
            ),
        )
        club2 = assign_club_for_employee(
            employee_id=e2, department="QA", as_of=today, cur=cur
        )
        assert club2["club_id"] != club1["club_id"]

    clubs = list_clubs("QA")
    eligible = eligible_clubs_for_employee(
        employee_id=e1,
        department="QA",
        department_clubs=clubs,
        as_of=today,
    )
    assert club1["club_id"] not in {c["club_id"] for c in eligible}
    _cleanup([e1, e2])


if __name__ == "__main__":
    test_employee_crud_and_department_filter()
    test_duplicate_employee_rejected()
    test_club_assignment_excludes_same_month()
    print("Employee/DB club tests passed.")
