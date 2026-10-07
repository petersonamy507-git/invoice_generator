"""Generate sample Excel files for bulk invoice testing."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_data"
SAMPLE.mkdir(exist_ok=True)

current = pd.DataFrame(
    [
        {
            "person_name": "John Doe",
            "company_name": "ABC Company",
            "email": "john@abc.com",
            "invoice_structure_number": 1,
            "total_amount": 1000,
        },
        {
            "person_name": "Jane Smith",
            "company_name": "XYZ Corp",
            "email": "jane@xyz.com",
            "invoice_structure_number": 2,
            "total_amount": 2500,
        },
        {
            "person_name": "Bob Wilson",
            "company_name": "Tech Labs",
            "email": "bob@techlabs.com",
            "invoice_structure_number": 3,
            "total_amount": 1800,
        },
    ]
)

history = pd.DataFrame(
    [
        {"person_name": "John Doe", "task_name": "API Development", "invoice_month": "2026-03"},
        {"person_name": "John Doe", "task_name": "Database Design", "invoice_month": "2026-04"},
        {"person_name": "Jane Smith", "task_name": "UI Component Library", "invoice_month": "2026-05"},
    ]
)

tasks = pd.DataFrame(
    [
        {"main_task": "Backend Engineering", "sub_task": "API Development"},
        {"main_task": "Backend Engineering", "sub_task": "Database Design"},
        {"main_task": "Backend Engineering", "sub_task": "Authentication Setup"},
        {"main_task": "Backend Engineering", "sub_task": "Payment Integration"},
        {"main_task": "Backend Engineering", "sub_task": "Server Deployment"},
        {"main_task": "Frontend Development", "sub_task": "UI Component Library"},
        {"main_task": "Frontend Development", "sub_task": "Responsive Layout"},
        {"main_task": "Frontend Development", "sub_task": "State Management"},
        {"main_task": "Quality Assurance", "sub_task": "Automated Testing"},
        {"main_task": "Quality Assurance", "sub_task": "Regression Testing"},
        {"main_task": "DevOps", "sub_task": "CI/CD Pipeline"},
        {"main_task": "DevOps", "sub_task": "Infrastructure Monitoring"},
    ]
)

current.to_excel(SAMPLE / "current_month.xlsx", index=False)
history.to_excel(SAMPLE / "history_3_months.xlsx", index=False)
tasks.to_excel(SAMPLE / "tasks.xlsx", index=False)
print(f"Sample files written to {SAMPLE}")
