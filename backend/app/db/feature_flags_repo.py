from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.app.db.connection import db_cursor
from backend.app.services.validation import ValidationError


def list_flags() -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT flag_key, enabled, value_json, description, updated_by,
                   created_at, updated_at
            FROM feature_flags
            ORDER BY flag_key ASC
            """
        )
        rows = cur.fetchall() or []
    return [_public(r) for r in rows]


def get_flag(flag_key: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT flag_key, enabled, value_json, description, updated_by,
                   created_at, updated_at
            FROM feature_flags WHERE flag_key = %s LIMIT 1
            """,
            (flag_key,),
        )
        row = cur.fetchone()
    return _public(row) if row else None


def upsert_flag(
    *,
    flag_key: str,
    enabled: bool,
    description: str | None = None,
    value: Any = None,
    updated_by: int | None = None,
) -> dict[str, Any]:
    key = str(flag_key or "").strip()
    if not key:
        raise ValidationError("flag_key is required.")
    value_json = None if value is None else json.dumps(value, default=str)
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO feature_flags (flag_key, enabled, value_json, description, updated_by)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              enabled = VALUES(enabled),
              value_json = VALUES(value_json),
              description = COALESCE(VALUES(description), description),
              updated_by = VALUES(updated_by)
            """,
            (
                key,
                1 if enabled else 0,
                value_json,
                description,
                updated_by,
            ),
        )
    row = get_flag(key)
    assert row is not None
    return row


def delete_flag(flag_key: str) -> dict[str, Any]:
    if not get_flag(flag_key):
        raise ValidationError(f"Feature flag {flag_key!r} not found.")
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM feature_flags WHERE flag_key = %s", (flag_key,))
    return {"flag_key": flag_key, "deleted": True}


def is_enabled(flag_key: str, default: bool = False) -> bool:
    row = get_flag(flag_key)
    if not row:
        return default
    return bool(row["enabled"])


def _public(row: dict[str, Any]) -> dict[str, Any]:
    value = None
    raw = row.get("value_json")
    if raw:
        try:
            value = json.loads(raw)
        except Exception:
            value = raw
    return {
        "flag_key": row["flag_key"],
        "enabled": bool(row["enabled"]),
        "value": value,
        "description": row.get("description"),
        "updated_by": row.get("updated_by"),
        "created_at": _ts(row.get("created_at")),
        "updated_at": _ts(row.get("updated_at")),
    }


def _ts(value: Any) -> Any:
    return value.isoformat(sep=" ") if isinstance(value, datetime) else value
