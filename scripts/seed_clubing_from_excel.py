"""Seed clubing table from ListOFservicesforInvoices category Items sheets."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db.clubing_repo import count_clubs, insert_club
from backend.app.db.migrate import run_migrations
from backend.app.services.category_tasks import CATEGORIES, load_category_tasks_df

CATEGORY_TO_DEPARTMENT = {
    "qa": "QA",
    "devops": "Devops",
    "call_centre": "Call centre",
    "account": "Account",
    "hr": "HR",
}


def _club_id_for(department: str, item: str) -> str:
    digest = hashlib.sha1(f"{department}|{item}".encode("utf-8")).hexdigest()[:10]
    return f"{department[:3].upper()}-{digest}"


def seed_clubs(*, force: bool = False) -> int:
    run_migrations()
    existing = count_clubs()
    if existing > 0 and not force:
        print(f"clubing already has {existing} rows; skip seed (use --force to re-seed).")
        return 0

    inserted = 0
    for key in CATEGORIES:
        dept = CATEGORY_TO_DEPARTMENT[key]
        df = load_category_tasks_df(key)
        for _, row in df.iterrows():
            item = str(row["sub_task"]).strip()
            if not item:
                continue
            club_id = _club_id_for(dept, item)
            insert_club(club_id, item, dept)
            inserted += 1
    print(f"Seeded/updated {inserted} clubing rows.")
    return inserted


if __name__ == "__main__":
    force = "--force" in sys.argv
    seed_clubs(force=force)
