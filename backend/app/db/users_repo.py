from __future__ import annotations

from datetime import datetime
from typing import Any

import pymysql

from backend.app.db.connection import db_cursor
from backend.app.services.password_utils import hash_password
from backend.app.services.validation import ValidationError

ALLOWED_ROLES = ("admin", "user")


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "last_login": row["last_login"].isoformat(sep=" ")
        if isinstance(row.get("last_login"), datetime)
        else row.get("last_login"),
        "created_at": row["created_at"].isoformat(sep=" ")
        if isinstance(row.get("created_at"), datetime)
        else row.get("created_at"),
        "updated_at": row["updated_at"].isoformat(sep=" ")
        if isinstance(row.get("updated_at"), datetime)
        else row.get("updated_at"),
    }


def find_user_by_identifier(identifier: str) -> dict[str, Any] | None:
    ident = str(identifier or "").strip()
    if not ident:
        return None
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, username, email, password_hash, role, is_active,
                   last_login, created_at, updated_at
            FROM users
            WHERE username = %s OR email = %s
            LIMIT 1
            """,
            (ident, ident),
        )
        return cur.fetchone()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, username, email, password_hash, role, is_active,
                   last_login, created_at, updated_at
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        return cur.fetchone()


def list_users() -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, username, email, role, is_active, last_login,
                   created_at, updated_at
            FROM users
            ORDER BY id ASC
            """
        )
        rows = cur.fetchall() or []
    return [_public_user(r) for r in rows]


def create_user(
    *,
    username: str,
    email: str,
    password: str,
    role: str = "user",
    is_active: bool = True,
) -> dict[str, Any]:
    username = str(username or "").strip()
    email = str(email or "").strip().lower()
    role = str(role or "user").strip().lower()
    if not username:
        raise ValidationError("Username is required.")
    if not email or "@" not in email:
        raise ValidationError("A valid email is required.")
    if role not in ALLOWED_ROLES:
        raise ValidationError(f"Role must be one of: {', '.join(ALLOWED_ROLES)}.")
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")

    password_hash = hash_password(password)
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (username, email, password_hash, role, 1 if is_active else 0),
            )
            user_id = int(cur.lastrowid)
    except pymysql.err.IntegrityError as e:
        msg = str(e).lower()
        if "username" in msg:
            raise ValidationError("Username already exists.") from e
        if "email" in msg:
            raise ValidationError("Email already exists.") from e
        raise ValidationError("Could not create user (duplicate username or email).") from e

    row = get_user_by_id(user_id)
    assert row is not None
    return _public_user(row)


def update_user(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_user_by_id(user_id)
    if not existing:
        raise ValidationError(f"User {user_id} not found.")

    username = str(payload.get("username", existing["username"]) or "").strip()
    email = str(payload.get("email", existing["email"]) or "").strip().lower()
    role = str(payload.get("role", existing["role"]) or "").strip().lower()
    is_active = payload.get("is_active", bool(existing["is_active"]))
    is_active = bool(is_active)

    if not username:
        raise ValidationError("Username is required.")
    if not email or "@" not in email:
        raise ValidationError("A valid email is required.")
    if role not in ALLOWED_ROLES:
        raise ValidationError(f"Role must be one of: {', '.join(ALLOWED_ROLES)}.")

    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE users
                SET username = %s, email = %s, role = %s, is_active = %s
                WHERE id = %s
                """,
                (username, email, role, 1 if is_active else 0, user_id),
            )
    except pymysql.err.IntegrityError as e:
        msg = str(e).lower()
        if "username" in msg:
            raise ValidationError("Username already exists.") from e
        if "email" in msg:
            raise ValidationError("Email already exists.") from e
        raise ValidationError("Could not update user.") from e

    row = get_user_by_id(user_id)
    assert row is not None
    return _public_user(row)


def set_user_password(user_id: int, password: str) -> None:
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if not get_user_by_id(user_id):
        raise ValidationError(f"User {user_id} not found.")
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(password), user_id),
        )


def delete_user(user_id: int) -> dict[str, Any]:
    if not get_user_by_id(user_id):
        raise ValidationError(f"User {user_id} not found.")
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    return {"id": user_id, "deleted": True}


def touch_last_login(user_id: int) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
            (user_id,),
        )


def count_users() -> int:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM users")
        return int(cur.fetchone()["c"])


def public_user_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return _public_user(row)
