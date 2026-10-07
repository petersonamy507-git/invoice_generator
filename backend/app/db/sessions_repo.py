from __future__ import annotations

import secrets

from backend.app.db.connection import db_cursor


SESSION_TTL_HOURS = 12


def create_session(user_id: int, *, ttl_hours: int = SESSION_TTL_HOURS) -> str:
    session_id = secrets.token_urlsafe(48)[:64]
    with db_cursor(commit=True) as cur:
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
