from __future__ import annotations

from datetime import datetime
from typing import Any

import pymysql

from backend.app.db.connection import db_cursor
from backend.app.services.password_utils import hash_password
from backend.app.services.validation import ValidationError

ALLOWED_ROLES = ("admin", "developer", "user")
# Who may change roles at all (Team / users API).
ROLE_GRANT_ROLES = ("admin", "developer")
# Only Developer may assign the developer role (Admin cannot).
DEVELOPER_ASSIGN_ROLES = ("developer",)


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


def assert_can_assign_role(
    *,
    actor_role: str,
    new_role: str,
    previous_role: str | None = None,
) -> None:
    """Admin/Developer may change roles; only Developer may assign developer."""
    actor = str(actor_role or "").strip().lower()
    target = str(new_role or "").strip().lower()
    previous = str(previous_role or "").strip().lower() if previous_role is not None else None
    if target not in ALLOWED_ROLES:
        raise ValidationError(f"Role must be one of: {', '.join(ALLOWED_ROLES)}.")
    if previous is not None and target == previous:
        return
    if actor not in ROLE_GRANT_ROLES:
        raise ValidationError("Only Admin or Developer can change user roles.")
    # Admin cannot grant or keep assigning developer via create/update to developer.
    if target == "developer" and actor not in DEVELOPER_ASSIGN_ROLES:
        raise ValidationError("Admin cannot assign the Developer role.")


def create_user(
    *,
    username: str,
    email: str,
    password: str,
    role: str = "user",
    is_active: bool = True,
    actor_role: str | None = None,
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
    if actor_role is not None:
        assert_can_assign_role(actor_role=actor_role, new_role=role, previous_role=None)
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
    created = _public_user(row)
    from backend.app.services.activity_trace import trace

    trace(
        action="user.create",
        resource_type="user",
        resource_id=str(user_id),
        table_name="users",
        after={**created, "password_hash": row.get("password_hash")},
    )
    return created


def update_user(
    user_id: int,
    payload: dict[str, Any],
    *,
    actor_role: str | None = None,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
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
    if actor_role is not None:
        assert_can_assign_role(
            actor_role=actor_role,
            new_role=role,
            previous_role=str(existing.get("role") or ""),
        )
    # Plain users must never elevate themselves.
    if (
        actor_user_id is not None
        and int(actor_user_id) == int(user_id)
        and str(actor_role or "").lower() not in ROLE_GRANT_ROLES
        and role != str(existing.get("role") or "").lower()
    ):
        raise ValidationError("You cannot change your own role.")

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
    updated = _public_user(row)
    from backend.app.services.activity_trace import trace

    trace(
        action="user.update",
        resource_type="user",
        resource_id=str(user_id),
        table_name="users",
        before=_public_user(existing),
        after=updated,
    )
    return updated


def set_user_password(user_id: int, password: str) -> None:
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    existing = get_user_by_id(user_id)
    if not existing:
        raise ValidationError(f"User {user_id} not found.")
    new_hash = hash_password(password)
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_hash, user_id),
        )
    from backend.app.services.activity_trace import trace

    trace(
        action="user.password_change",
        resource_type="user",
        resource_id=str(user_id),
        table_name="users",
        before={"password_hash": existing.get("password_hash")},
        after={"password_hash": new_hash, "username": existing.get("username")},
        meta={"note": "Plaintext passwords are never stored; hash updated."},
    )


def delete_user(user_id: int) -> dict[str, Any]:
    existing = get_user_by_id(user_id)
    if not existing:
        raise ValidationError(f"User {user_id} not found.")
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    from backend.app.services.activity_trace import trace

    trace(
        action="user.delete",
        resource_type="user",
        resource_id=str(user_id),
        table_name="users",
        before=_public_user(existing),
    )
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
