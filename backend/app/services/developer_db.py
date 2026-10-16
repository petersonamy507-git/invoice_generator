"""Database explorer / CRUD for the Developer Panel."""
from __future__ import annotations

from typing import Any

from backend.app.db.connection import db_config, db_cursor
from backend.app.services.developer_security import (
    assert_safe_identifier,
    is_sensitive_field,
    mask_record,
    mask_records,
)
from backend.app.services.validation import ValidationError


def list_tables() -> list[dict[str, Any]]:
    db = db_config()["database"]
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT table_name, table_rows, engine, table_collation, create_time, update_time
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name ASC
            """,
            (db,),
        )
        rows = cur.fetchall() or []
    return [
        {
            "name": r["table_name"] if "table_name" in r else r["TABLE_NAME"],
            "approx_rows": r.get("table_rows") if "table_rows" in r else r.get("TABLE_ROWS"),
            "engine": r.get("engine") if "engine" in r else r.get("ENGINE"),
            "collation": r.get("table_collation")
            if "table_collation" in r
            else r.get("TABLE_COLLATION"),
            "create_time": str(
                r.get("create_time") if "create_time" in r else r.get("CREATE_TIME") or ""
            ),
            "update_time": str(
                r.get("update_time") if "update_time" in r else r.get("UPDATE_TIME") or ""
            ),
        }
        for r in rows
    ]


def _table_exists(table: str) -> bool:
    db = db_config()["database"]
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS c FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s AND table_type = 'BASE TABLE'
            """,
            (db, table),
        )
        return int(cur.fetchone()["c"]) > 0


def ensure_app_table(table: str) -> str:
    name = assert_safe_identifier(table, kind="table name")
    if not _table_exists(name):
        raise ValidationError(f"Table {name!r} not found in this database.")
    return name


def describe_table(table: str) -> dict[str, Any]:
    name = ensure_app_table(table)
    db = db_config()["database"]
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, column_type, is_nullable, column_key,
                   column_default, extra, character_maximum_length, numeric_precision
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position ASC
            """,
            (db, name),
        )
        cols = cur.fetchall() or []
        cur.execute(
            """
            SELECT index_name, non_unique, column_name, seq_in_index
            FROM information_schema.statistics
            WHERE table_schema = %s AND table_name = %s
            ORDER BY index_name, seq_in_index
            """,
            (db, name),
        )
        indexes = cur.fetchall() or []
        cur.execute(
            """
            SELECT constraint_name, column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s AND table_name = %s
              AND referenced_table_name IS NOT NULL
            ORDER BY constraint_name, ordinal_position
            """,
            (db, name),
        )
        fks = cur.fetchall() or []

    def _c(r: dict[str, Any], *keys: str) -> Any:
        for k in keys:
            if k in r:
                return r[k]
            up = k.upper()
            if up in r:
                return r[up]
        return None

    columns = []
    for r in cols:
        col = str(_c(r, "column_name"))
        columns.append(
            {
                "name": col,
                "data_type": _c(r, "data_type"),
                "column_type": _c(r, "column_type"),
                "nullable": str(_c(r, "is_nullable")).upper() == "YES",
                "key": _c(r, "column_key"),
                "default": _c(r, "column_default"),
                "extra": _c(r, "extra"),
                "sensitive": is_sensitive_field(col),
            }
        )
    return {
        "table": name,
        "columns": columns,
        "indexes": [
            {
                "name": _c(r, "index_name"),
                "unique": int(_c(r, "non_unique") or 0) == 0,
                "column": _c(r, "column_name"),
                "seq": _c(r, "seq_in_index"),
            }
            for r in indexes
        ],
        "foreign_keys": [
            {
                "constraint": _c(r, "constraint_name"),
                "column": _c(r, "column_name"),
                "references_table": _c(r, "referenced_table_name"),
                "references_column": _c(r, "referenced_column_name"),
            }
            for r in fks
        ],
        "primary_key": [c["name"] for c in columns if c.get("key") == "PRI"],
    }


def _primary_key(table: str) -> list[str]:
    meta = describe_table(table)
    pk = meta.get("primary_key") or []
    if not pk:
        raise ValidationError(f"Table {table!r} has no primary key; edits are blocked.")
    return pk


def query_rows(
    table: str,
    *,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = "asc",
    filters: dict[str, Any] | None = None,
    reveal_secrets: bool = True,
) -> dict[str, Any]:
    name = ensure_app_table(table)
    meta = describe_table(name)
    col_names = {c["name"] for c in meta["columns"]}
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    where: list[str] = []
    params: list[Any] = []
    if filters:
        for key, value in filters.items():
            col = assert_safe_identifier(key, kind="column")
            if col not in col_names:
                raise ValidationError(f"Unknown filter column {col!r}.")
            where.append(f"`{col}` = %s")
            params.append(value)
    if search:
        like = f"%{search}%"
        text_cols = [
            c["name"]
            for c in meta["columns"]
            if str(c.get("data_type") or "").lower()
            in {"varchar", "char", "text", "mediumtext", "longtext", "enum"}
        ]
        if text_cols:
            where.append("(" + " OR ".join(f"`{c}` LIKE %s" for c in text_cols) + ")")
            params.extend([like] * len(text_cols))

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    order = ""
    if sort_by:
        col = assert_safe_identifier(sort_by, kind="sort column")
        if col not in col_names:
            raise ValidationError(f"Unknown sort column {col!r}.")
        direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
        order = f"ORDER BY `{col}` {direction}"

    with db_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS c FROM `{name}` {clause}", params)
        total = int(cur.fetchone()["c"])
        cur.execute(
            f"SELECT * FROM `{name}` {clause} {order} LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        rows = cur.fetchall() or []

    return {
        "table": name,
        "total": total,
        "limit": limit,
        "offset": offset,
        "primary_key": meta["primary_key"],
        "columns": meta["columns"],
        "rows": mask_records(rows, reveal_secrets=reveal_secrets),
    }


def get_row(
    table: str, pk_values: dict[str, Any], *, reveal_secrets: bool = True
) -> dict[str, Any]:
    name = ensure_app_table(table)
    pk = _primary_key(name)
    where = " AND ".join(f"`{c}` = %s" for c in pk)
    params = [_pk_value(pk_values, c) for c in pk]
    with db_cursor() as cur:
        cur.execute(f"SELECT * FROM `{name}` WHERE {where} LIMIT 1", params)
        row = cur.fetchone()
    if not row:
        raise ValidationError("Record not found.")
    return {
        "table": name,
        "primary_key": pk,
        "row": mask_record(row, reveal_secrets=reveal_secrets),
    }


def _prepare_write_value(table: str, column: str, value: Any) -> Any:
    """Developer may write any column; auto-hash plaintext password fields."""
    if value is None:
        return None
    col = str(column).lower()
    if table == "users" and col in {"password_hash", "password"}:
        text = str(value)
        # Already bcrypt / passlib hash — store as-is.
        if text.startswith(("$2a$", "$2b$", "$2y$", "$pbkdf2", "$argon2")):
            return text
        from backend.app.services.password_utils import hash_password

        return hash_password(text)
    return value


def create_row(table: str, data: dict[str, Any]) -> dict[str, Any]:
    name = ensure_app_table(table)
    meta = describe_table(name)
    allowed = {c["name"] for c in meta["columns"]}
    cleaned: dict[str, Any] = {}
    for k, v in (data or {}).items():
        if k not in allowed:
            continue
        # Map convenience "password" → password_hash on users.
        col = "password_hash" if name == "users" and k == "password" else k
        if col not in allowed:
            continue
        cleaned[col] = _prepare_write_value(name, col, v)
    if not cleaned:
        raise ValidationError("No writable fields provided.")
    cols = list(cleaned.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_sql = ", ".join(f"`{c}`" for c in cols)
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"INSERT INTO `{name}` ({col_sql}) VALUES ({placeholders})",
            [cleaned[c] for c in cols],
        )
        insert_id = cur.lastrowid
    pk = meta["primary_key"]
    if insert_id and len(pk) == 1:
        return get_row(name, {pk[0]: insert_id}, reveal_secrets=True)
    pk_vals = {c: cleaned[c] for c in pk if c in cleaned}
    if len(pk_vals) == len(pk):
        return get_row(name, pk_vals, reveal_secrets=True)
    return {"table": name, "created": True, "row": cleaned}


def update_row(table: str, pk_values: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    name = ensure_app_table(table)
    pk = _primary_key(name)
    before = get_row(name, pk_values, reveal_secrets=True)["row"]
    meta = describe_table(name)
    allowed = {c["name"] for c in meta["columns"]} - set(pk)
    cleaned: dict[str, Any] = {}
    for k, v in (data or {}).items():
        col = "password_hash" if name == "users" and k == "password" else k
        if col not in allowed:
            continue
        cleaned[col] = _prepare_write_value(name, col, v)
    if not cleaned:
        raise ValidationError("No writable fields provided.")
    sets = ", ".join(f"`{c}` = %s" for c in cleaned)
    where = " AND ".join(f"`{c}` = %s" for c in pk)
    params = [*[cleaned[c] for c in cleaned], *[_pk_value(pk_values, c) for c in pk]]
    with db_cursor(commit=True) as cur:
        cur.execute(f"UPDATE `{name}` SET {sets} WHERE {where}", params)
    after = get_row(name, pk_values, reveal_secrets=True)
    after["before"] = before
    return after


def delete_row(table: str, pk_values: dict[str, Any]) -> dict[str, Any]:
    name = ensure_app_table(table)
    pk = _primary_key(name)
    before = get_row(name, pk_values, reveal_secrets=True)["row"]
    where = " AND ".join(f"`{c}` = %s" for c in pk)
    params = [_pk_value(pk_values, c) for c in pk]
    with db_cursor(commit=True) as cur:
        cur.execute(f"DELETE FROM `{name}` WHERE {where}", params)
    return {"table": name, "deleted": True, "before": before}


def bulk_update(
    table: str, *, pk_list: list[dict[str, Any]], data: dict[str, Any]
) -> dict[str, Any]:
    if not pk_list:
        raise ValidationError("pk_list is required.")
    if len(pk_list) > 200:
        raise ValidationError("Bulk update limited to 200 rows.")
    updated = []
    for pk_values in pk_list:
        updated.append(update_row(table, pk_values, data))
    return {"table": table, "updated_count": len(updated), "rows": updated}


def bulk_delete(table: str, *, pk_list: list[dict[str, Any]]) -> dict[str, Any]:
    if not pk_list:
        raise ValidationError("pk_list is required.")
    if len(pk_list) > 200:
        raise ValidationError("Bulk delete limited to 200 rows.")
    deleted = []
    for pk_values in pk_list:
        deleted.append(delete_row(table, pk_values))
    return {"table": table, "deleted_count": len(deleted), "rows": deleted}


def migration_status() -> dict[str, Any]:
    from backend.app.db.migrate import MIGRATION_FILES, MIGRATIONS_DIR

    files = []
    for name in MIGRATION_FILES:
        path = MIGRATIONS_DIR / name
        files.append(
            {
                "name": name,
                "exists": path.is_file(),
                "size": path.stat().st_size if path.is_file() else 0,
            }
        )
    tables = list_tables()
    return {
        "migrations": files,
        "tables": tables,
        "database": db_config()["database"],
    }


def system_health() -> dict[str, Any]:
    import os
    import platform
    import time

    from backend.app.services.developer_security import app_environment

    started = time.time()
    db_ok = False
    db_error = None
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            db_ok = int(cur.fetchone()["ok"]) == 1
    except Exception as e:  # pragma: no cover
        db_error = str(e)
    return {
        "ok": db_ok,
        "environment": app_environment(),
        "database": {
            "ok": db_ok,
            "name": db_config()["database"],
            "host": db_config()["host"],
            "error": db_error,
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
        },
        "latency_ms": int((time.time() - started) * 1000),
        "masked_env": _masked_env_snapshot(),
    }


def _masked_env_snapshot() -> dict[str, str]:
    keys = [
        "APP_ENV",
        "ENVIRONMENT",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "CORS_ORIGINS",
        "INITIAL_ADMIN_USERNAME",
    ]
    out: dict[str, str] = {}
    import os

    for k in keys:
        v = os.getenv(k)
        if v is None:
            continue
        if is_sensitive_field(k) or k.endswith("PASSWORD"):
            out[k] = "***REDACTED***"
        else:
            out[k] = v
    out["DB_PASSWORD"] = "***REDACTED***" if os.getenv("DB_PASSWORD") else ""
    return out


def _pk_value(pk_values: dict[str, Any], column: str) -> Any:
    if column not in pk_values:
        raise ValidationError(f"Missing primary key field {column!r}.")
    return pk_values[column]
