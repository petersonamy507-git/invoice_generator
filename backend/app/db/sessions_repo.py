from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from backend.app.db.connection import db_cursor


SESSION_TTL_HOURS = 12


def create_session(
    user_id: int,
    *,
    ttl_hours: int = SESSION_TTL_HOURS,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    session_id = secrets.token_urlsafe(48)[:64]
    with db_cursor(commit=True) as cur:
        # Prefer meta columns; fall back if migration not applied yet.
        try:
            cur.execute(
                """
                INSERT INTO auth_sessions (id, user_id, ip_address, user_agent, expires_at)
                VALUES (%s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))
                """,
                (
                    session_id,
                    user_id,
                    ip_address,
                    (user_agent or "")[:512] or None,
                    int(ttl_hours),
                ),
            )
        except Exception:
            cur.execute(
                """
                INSERT INTO auth_sessions (id, user_id, expires_at)
                VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))
                """,
                (session_id, user_id, int(ttl_hours)),
            )
    return session_id


def get_session_user_id(session_id: str) -> int | None:
    if not session_id:
        return None
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT user_id
            FROM auth_sessions
            WHERE id = %s AND expires_at > NOW()
            LIMIT 1
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "DELETE FROM auth_sessions WHERE id = %s OR expires_at <= NOW()",
                (session_id,),
            )
            return None
        return int(row["user_id"])


def delete_session(session_id: str) -> None:
    if not session_id:
        return
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM auth_sessions WHERE id = %s", (session_id,))


def delete_user_sessions(user_id: int) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM auth_sessions WHERE user_id = %s", (user_id,))


def cleanup_expired_sessions() -> None:
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM auth_sessions WHERE expires_at <= NOW()")


def list_active_sessions() -> list[dict[str, Any]]:
    """Who is currently logged in (unexpired sessions)."""
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM auth_sessions WHERE expires_at <= NOW()")
        cur.execute(
            """
            SELECT s.id AS session_id, s.user_id, s.expires_at, s.created_at,
                   s.ip_address, s.user_agent,
                   u.username, u.email, u.role, u.is_active, u.last_login
            FROM auth_sessions s
            INNER JOIN users u ON u.id = s.user_id
            WHERE s.expires_at > NOW()
            ORDER BY s.created_at DESC
            """
        )
        rows = cur.fetchall() or []

    def _ts(v: Any) -> Any:
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v

    return [
        {
            "session_id": r["session_id"],
            "user_id": int(r["user_id"]),
            "username": r.get("username"),
            "email": r.get("email"),
            "role": r.get("role"),
            "is_active": bool(r.get("is_active")),
            "ip_address": r.get("ip_address"),
            "user_agent": r.get("user_agent"),
            "last_login": _ts(r.get("last_login")),
            "session_started": _ts(r.get("created_at")),
            "expires_at": _ts(r.get("expires_at")),
        }
        for r in rows
    ]
