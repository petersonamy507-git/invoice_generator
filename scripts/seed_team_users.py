"""
Seed login accounts for the ops team (admin is created from .env on API startup).

Edit TEAM_USERS below, then:
  .venv\\Scripts\\python.exe scripts\\seed_team_users.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from backend.app.db.users_repo import create_user, find_user_by_identifier, list_users
from backend.app.services.auth_service import ensure_initial_admin
from backend.app.services.validation import ValidationError

# Temporary shared password — change after first login via admin UI / API.
DEFAULT_PASSWORD = "Team@12345"

# Internal team logins (not invoice employees). role: admin | user
TEAM_USERS = [
    {
        "username": "hafeez",
        "email": "hafeez@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "admin",
    },
    {
        "username": "mansoor",
        "email": "mansoor@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "user",
    },
    {
        "username": "yaqoob",
        "email": "yaqoob@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "user",
    },
    {
        "username": "ahad",
        "email": "ahad@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "user",
    },
    {
        "username": "dinesh",
        "email": "dinesh@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "user",
    },
    {
        "username": "fahad",
        "email": "fahad@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "user",
    },
    {
        "username": "junaid",
        "email": "junaid@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "user",
    },
    {
        "username": "jahanzaib",
        "email": "jahanzaib@invoice.local",
        "password": DEFAULT_PASSWORD,
        "role": "user",
    },
]


def main() -> int:
    ensure_initial_admin()
    created = 0
    skipped = 0
    for row in TEAM_USERS:
        existing = find_user_by_identifier(row["username"]) or find_user_by_identifier(
            row["email"]
        )
        if existing:
            print(f"skip  {row['username']} (already exists, id={existing['id']})")
            skipped += 1
            continue
        try:
            user = create_user(
                username=row["username"],
                email=row["email"],
                password=row["password"],
                role=row.get("role", "user"),
                is_active=True,
            )
            print(f"add   {user['username']}  {user['email']}  role={user['role']}")
            created += 1
        except ValidationError as exc:
            print(f"fail  {row['username']}: {exc}")
            return 1

    print()
    print(f"Done. created={created} skipped={skipped}")
    print("All users:")
    for u in list_users():
        print(
            f"  {u['id']:3}  {u['username']:<16}  {u['email']:<28}  {u['role']:<6}  active={u['is_active']}"
        )
    print()
    print("Login: POST /api/auth/login  { identifier, password }")
    print(f"  admin     / Admin@12345   (from .env INITIAL_ADMIN_*)")
    print(f"  team      / {DEFAULT_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
