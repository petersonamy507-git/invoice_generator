from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.db.connection import db_cursor

# Keep table from growing unbounded.
MAX_ROWS = 5000
RETENTION_DELETE_BATCH = 1000


def record_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int | None = None,
    user_id: int | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    error_detail: str | None = None,
) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO api_request_logs (
              method, path, status_code, duration_ms, user_id, username,
              ip_address, error_detail
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                method[:16],
                path[:512],
                int(status_code),
                duration_ms,
                user_id,
                username,
                ip_address,
                (error_detail or "")[:1000] or None,
            ),
        )
        cur.execute("SELECT COUNT(*) AS c FROM api_request_logs")
        count = int(cur.fetchone()["c"])
        if count > MAX_ROWS:
            cur.execute(
                """
                DELETE FROM api_request_logs
                ORDER BY id ASC
                LIMIT %s
                """,
                (min(RETENTION_DELETE_BATCH, count - MAX_ROWS),),
            )


def list_logs(
    *,
    limit: int = 100,
    offset: int = 0,
    status_code: int | None = None,
    path_contains: str | None = None,
    errors_only: bool = False,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    where: list[str] = []
    params: list[Any] = []
    if status_code is not None:
        where.append("status_code = %s")
        params.append(status_code)
    if path_contains:
        where.append("path LIKE %s")
        params.append(f"%{path_contains}%")
    if errors_only:
        where.append("status_code >= 400")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with db_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS c FROM api_request_logs {clause}", params)
        total = int(cur.fetchone()["c"])
        cur.execute(
            f"""
            SELECT id, method, path, status_code, duration_ms, user_id, username,
                   ip_address, error_detail, created_at
            FROM api_request_logs
            {clause}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        )
        rows = cur.fetchall() or []

    items = []
    for r in rows:
        created = r.get("created_at")
        items.append(
            {
                "id": int(r["id"]),
                "method": r["method"],
                "path": r["path"],
                "status_code": int(r["status_code"]),
                "duration_ms": r.get("duration_ms"),
                "user_id": r.get("user_id"),
                "username": r.get("username"),
                "ip_address": r.get("ip_address"),
                "error_detail": r.get("error_detail"),
                "created_at": created.isoformat(sep=" ")
                if isinstance(created, datetime)
                else created,
            }
        )
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def clear_logs() -> dict[str, Any]:
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM api_request_logs")
    return {"cleared": True}
