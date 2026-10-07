import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.amount_distribution import distribute_amounts
from backend.app.services.task_assignment import (
    assign_tasks_for_person,
    build_person_history,
    load_available_tasks,
)
import pandas as pd


def test_amounts_sum_to_total():
    for total in [100, 1000, 3333, 99]:
        amounts = distribute_amounts(total)
        assert len(amounts) == 3
        assert sum(amounts) == total


def test_task_exclusion_for_person():
    history = pd.DataFrame(
        [
            {"person_name": "Alice", "task_name": "API Development", "invoice_month": "2026-01"},
        ]
    )
    tasks = pd.DataFrame(
        [
            {"main_task": "BE", "sub_task": "API Development"},
            {"main_task": "BE", "sub_task": "Database Design"},
            {"main_task": "BE", "sub_task": "Auth Setup"},
            {"main_task": "FE", "sub_task": "UI Work"},
        ]
    )
    person_history = build_person_history(history)
    available = load_available_tasks(tasks)
    assigned = assign_tasks_for_person(
        "Alice", available, person_history, set()
    )
    subtasks = [s.lower() for _, s in assigned]
    assert "api development" not in subtasks
    assert len(assigned) == 3


def test_wide_history_excludes_month_items():
    history = pd.DataFrame(
        [
            {
                "Name": "Alice",
                "May": "API Development",
                "April": "Database Design",
                "March": "Auth Setup",
            }
        ]
    )
    tasks = pd.DataFrame(
        [
            {"main_task": "BE", "sub_task": "API Development"},
            {"main_task": "BE", "sub_task": "Database Design"},
            {"main_task": "BE", "sub_task": "Auth Setup"},
            {"main_task": "FE", "sub_task": "UI Work"},
            {"main_task": "FE", "sub_task": "SM Post Designs"},
            {"main_task": "Web", "sub_task": "Domain & Hosting"},
        ]
    )
    person_history = build_person_history(history)
    available = load_available_tasks(tasks)
    assigned = assign_tasks_for_person(
        "Alice", available, person_history, set()
    )
    subtasks = [s.lower() for _, s in assigned]
    assert "api development" not in subtasks
    assert "database design" not in subtasks
    assert "auth setup" not in subtasks
    assert len(assigned) == 3


def test_wide_tasks_sheet_format():
    tasks = pd.DataFrame(
        {
            "Identity Designing": [
                "Brand Identity/Guidline Design",
                "Logo Design (6 Variations)",
            ],
            "Social Media Management": [
                "SM Post Designs",
                "Social Media Posting",
            ],
            "Website Designing & Development": [
                "UI/UX Design (Figma)",
                "Domain & Hosting",
            ],
        }
    )
    loaded = load_available_tasks(tasks)
    assert len(loaded) >= 6
    mains = {mt for mt, _ in loaded}
    assert "Identity Designing" in mains
    subs = {st for _, st in loaded}
    assert "UI/UX Design (Figma)" in subs


def test_no_duplicate_items_across_batch():
    tasks = pd.DataFrame(
        [
            {"main_task": "BE", "sub_task": "API Development"},
            {"main_task": "BE", "sub_task": "Database Design"},
            {"main_task": "BE", "sub_task": "Auth Setup"},
            {"main_task": "FE", "sub_task": "UI Work"},
            {"main_task": "FE", "sub_task": "SM Post Designs"},
            {"main_task": "Web", "sub_task": "Domain & Hosting"},
            {"main_task": "Web", "sub_task": "SEO Setup"},
            {"main_task": "Web", "sub_task": "Analytics"},
            {"main_task": "Ops", "sub_task": "Monitoring"},
            {"main_task": "Ops", "sub_task": "Backup Config"},
            {"main_task": "Ops", "sub_task": "CI Pipeline"},
            {"main_task": "Ops", "sub_task": "Log Review"},
            {"main_task": "Ops", "sub_task": "Security Scan"},
            {"main_task": "Ops", "sub_task": "Patch Updates"},
            {"main_task": "Ops", "sub_task": "Load Testing"},
        ]
    )
    available = load_available_tasks(tasks)
    batch_used: set[str] = set()
    all_assigned: list[str] = []

    for name in ["Alice", "Bob", "Charlie", "Diana", "Eve"]:
        assigned = assign_tasks_for_person(name, available, {}, batch_used)
        for _, sub_task in assigned:
            key = sub_task.lower()
            assert key not in batch_used
            batch_used.add(key)
            all_assigned.append(key)

    assert len(all_assigned) == 15
    assert len(set(all_assigned)) == 15


if __name__ == "__main__":
    test_amounts_sum_to_total()
    test_task_exclusion_for_person()
    test_wide_history_excludes_month_items()
    test_wide_tasks_sheet_format()
    test_no_duplicate_items_across_batch()
    print("All tests passed.")
