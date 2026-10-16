from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.app.db.connection import db_cursor
from backend.app.services.developer_security import mask_record


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, ensure_ascii=False)


def record_audit(
    *,
    actor: dict[str, Any] | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    table_name: str | None = None,
    before: Any = None,
    after: Any = None,
    meta: Any = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    before_m = mask_record(before) if isinstance(before, dict) else before
    after_m = mask_record(after) if isinstance(after, dict) else after
    if isinstance(before, list):
        before_m = [mask_record(x) if isinstance(x, dict) else x for x in before]
    if isinstance(after, list):
        after_m = [mask_record(x) if isinstance(x, dict) else x for x in after]
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO developer_audit_log (
              actor_user_id, actor_username, action, resource_type, resource_id,
              table_name, before_json, after_json, meta_json, ip_address, user_agent
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(actor["id"]) if actor and actor.get("id") is not None else None,
                (actor or {}).get("username"),
                action,
                resource_type,
                resource_id,
                table_name,
                _json(before_m),
                _json(after_m),
                _json(meta),
                ip_address,
                (user_agent or "")[:512] or None,
            ),
        )


def list_audit(
    *,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    table_name: str | None = None,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    where: list[str] = []
    params: list[Any] = []
    if action:
        where.append("action = %s")
        params.append(action)
    if table_name:
        where.append("table_name = %s")
        params.append(table_name)
    if actor_user_id is not None:
        where.append("actor_user_id = %s")
        params.append(actor_user_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with db_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS c FROM developer_audit_log {clause}", params)
        total = int(cur.fetchone()["c"])
        cur.execute(
            f"""
            SELECT id, actor_user_id, actor_username, action, resource_type, resource_id,
                   table_name, before_json, after_json, meta_json, ip_address, user_agent,
                   created_at
            FROM developer_audit_log
            {clause}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        )
        rows = cur.fetchall() or []

    def _row(r: dict[str, Any]) -> dict[str, Any]:
        created = r.get("created_at")
        return {
            "id": int(r["id"]),
            "actor_user_id": r.get("actor_user_id"),
            "actor_username": r.get("actor_username"),
            "action": r["action"],
            "resource_type": r["resource_type"],
            "resource_id": r.get("resource_id"),
            "table_name": r.get("table_name"),
            "before": json.loads(r["before_json"]) if r.get("before_json") else None,
            "after": json.loads(r["after_json"]) if r.get("after_json") else None,
            "meta": json.loads(r["meta_json"]) if r.get("meta_json") else None,
            "ip_address": r.get("ip_address"),
            "user_agent": r.get("user_agent"),
            "created_at": created.isoformat(sep=" ")
            if isinstance(created, datetime)
            else created,
        }

    return {"total": total, "limit": limit, "offset": offset, "items": [_row(r) for r in rows]}
