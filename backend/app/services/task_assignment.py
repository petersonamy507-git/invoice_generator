import re
from collections import defaultdict

import pandas as pd

from backend.app.models import InvoiceData, InvoiceTask
from backend.app.services.amount_distribution import distribute_amounts
from backend.app.services.validation import ValidationError, normalize_columns


def _normalize_person(name: str) -> str:
    return str(name).strip().lower()


def _normalize_task(task: str) -> str:
    return str(task).strip().lower()


def _split_history_tasks(text: str) -> list[str]:
    tasks: list[str] = []
    for part in re.split(r"[,;\n|]+", str(text)):
        cleaned = part.strip()
        if cleaned:
            tasks.append(cleaned)
    return tasks


def _is_long_history_format(df: pd.DataFrame) -> bool:
    cols = set(df.columns)
    return "task_name" in cols and (
        "person_name" in cols or "name" in cols
    )


def build_person_history(history_df: pd.DataFrame) -> dict[str, set[str]]:
    """person -> set of subtasks used in last 3 months."""
    excluded: dict[str, set[str]] = defaultdict(set)
    if history_df is None or history_df.empty:
        return excluded

    history_df = history_df.copy()
    normalize_columns(history_df)

    if _is_long_history_format(history_df):
        for _, row in history_df.iterrows():
            person_col = "person_name" if "person_name" in history_df.columns else "name"
            person = row.get(person_col)
            task = row.get("task_name")
            if pd.isna(person) or pd.isna(task):
                continue
            excluded[_normalize_person(person)].add(_normalize_task(task))
        return excluded

    name_col = "name" if "name" in history_df.columns else None
    if not name_col:
        raise ValidationError(
            "History sheet must have a Name column (wide format: Name, May, April, March)."
        )

    month_cols = [c for c in history_df.columns if c != name_col]
    for _, row in history_df.iterrows():
        person = row.get(name_col)
        if pd.isna(person) or not str(person).strip():
            continue
        person_key = _normalize_person(person)
        for month_col in month_cols:
            value = row.get(month_col)
            if pd.isna(value) or not str(value).strip():
                continue
            for task in _split_history_tasks(str(value)):
                excluded[person_key].add(_normalize_task(task))

    return excluded


def _is_long_tasks_format(df: pd.DataFrame) -> bool:
    normalized_cols = {
        str(c).strip().lower().replace(" ", "_") for c in df.columns
    }
    return "main_task" in normalized_cols and "sub_task" in normalized_cols


def _load_tasks_long_format(tasks_df: pd.DataFrame) -> list[tuple[str, str]]:
    df = tasks_df.copy()
    normalize_columns(df)
    tasks: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        main_task = str(row["main_task"]).strip()
        sub_task = str(row["sub_task"]).strip()
        key = _normalize_task(sub_task)
        if not sub_task or key in seen:
            continue
        seen.add(key)
        tasks.append((main_task, sub_task))
    return tasks


def _load_tasks_wide_format(tasks_df: pd.DataFrame) -> list[tuple[str, str]]:
    """Row 1 = main task names (column headers); rows below = subtasks per column."""
    tasks: list[tuple[str, str]] = []
    seen: set[str] = set()
    for col in tasks_df.columns:
        main_task = str(col).strip()
        if not main_task or main_task.lower().startswith("unnamed"):
            continue
        for _, row in tasks_df.iterrows():
            value = row[col]
            if pd.isna(value) or not str(value).strip():
                continue
            sub_task = str(value).strip()
            key = _normalize_task(sub_task)
            if key in seen:
                continue
            seen.add(key)
            tasks.append((main_task, sub_task))
    return tasks


def load_available_tasks(tasks_df: pd.DataFrame) -> list[tuple[str, str]]:
    if _is_long_tasks_format(tasks_df):
        tasks = _load_tasks_long_format(tasks_df)
    else:
        tasks = _load_tasks_wide_format(tasks_df)

    if len(tasks) < 3:
        raise ValidationError(
            "Task sheet must contain at least 3 unique subtasks."
        )
    return tasks


def assign_tasks_for_person(
    person_name: str,
    available_tasks: list[tuple[str, str]],
    person_history: dict[str, set[str]],
    batch_used_subtasks: set[str],
) -> list[tuple[str, str]]:
    person_key = _normalize_person(person_name)
    used_for_person = person_history.get(person_key, set())

    eligible: list[tuple[str, str]] = []
    for main_task, sub_task in available_tasks:
        sub_key = _normalize_task(sub_task)
        if sub_key in used_for_person:
            continue
        if sub_key in batch_used_subtasks:
            continue
        eligible.append((main_task, sub_task))

    if len(eligible) < 3:
        raise ValidationError(
            f"Not enough eligible tasks for '{person_name}'. "
            f"Need 3 tasks but only {len(eligible)} available after applying "
            "3-month history and batch uniqueness rules."
        )

    return eligible[:3]


def build_invoices_from_dataframe(
    current_df: pd.DataFrame,
    history_df: pd.DataFrame,
    tasks_df: pd.DataFrame,
    invoice_date,
    row_validators,
) -> list[InvoiceData]:
    person_history = build_person_history(history_df)
    available_tasks = load_available_tasks(tasks_df)
    if len(available_tasks) < 3:
        raise ValidationError(
            "Task sheet must contain at least 3 unique subtasks."
        )

    batch_used_subtasks: set[str] = set()
    invoices: list[InvoiceData] = []

    for idx, row in current_df.iterrows():
        row_num = int(idx) + 2 if isinstance(idx, int) else idx
        ctx = f"Row {row_num}: "

        validated = row_validators(row, ctx)
        person_name = validated["person_name"]

        assigned = assign_tasks_for_person(
            person_name,
            available_tasks,
            person_history,
            batch_used_subtasks,
        )

        for _, sub_task in assigned:
            batch_used_subtasks.add(_normalize_task(sub_task))

        amounts = distribute_amounts(validated["total_amount"])
        invoice_tasks = [
            InvoiceTask(main_task=mt, sub_task=st, amount=amt)
            for (mt, st), amt in zip(assigned, amounts)
        ]

        invoices.append(
            InvoiceData(
                person_name=person_name,
                company_name=validated["company_name"],
                email=validated["email"],
                invoice_date=invoice_date,
                structure_number=validated["structure_number"],
                total_amount=validated["total_amount"],
                tasks=invoice_tasks,
            )
        )

    return invoices
