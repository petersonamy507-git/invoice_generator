"""Developer Panel API — developer role only."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.auth_deps import RequireDeveloper
from backend.app.db import api_logs_repo, developer_audit_repo, feature_flags_repo
from backend.app.db import sessions_repo
from backend.app.db.users_repo import get_user_by_id, public_user_from_row
from backend.app.services import developer_db
from backend.app.services.developer_security import (
    DESTRUCTIVE_CONFIRM_PHRASE,
    app_environment,
    require_destructive_confirm,
)
from backend.app.services.validation import ValidationError

router = APIRouter(prefix="/api/developer", tags=["developer"])


def _http(exc: ValidationError, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


def _audit(
    request: Request,
    actor: dict[str, Any],
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    table_name: str | None = None,
    before: Any = None,
    after: Any = None,
    meta: Any = None,
) -> None:
    ip, ua = _client_meta(request)
    try:
        developer_audit_repo.record_audit(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            table_name=table_name,
            before=before,
            after=after,
            meta=meta,
            ip_address=ip,
            user_agent=ua,
        )
    except Exception:
        # Never block developer ops if audit write fails; surface via logs table later.
        pass


class ConfirmBody(BaseModel):
    confirm: bool = False
    confirm_phrase: str | None = None
    production_password: str | None = None


class RecordCreate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class RecordUpdate(BaseModel):
    pk: dict[str, Any]
    data: dict[str, Any] = Field(default_factory=dict)


class RecordDelete(ConfirmBody):
    pk: dict[str, Any]


class BulkUpdateBody(ConfirmBody):
    pk_list: list[dict[str, Any]]
    data: dict[str, Any] = Field(default_factory=dict)


class BulkDeleteBody(ConfirmBody):
    pk_list: list[dict[str, Any]]


class FlagUpsert(BaseModel):
    flag_key: str
    enabled: bool = False
    description: str | None = None
    value: Any = None


class CacheClearBody(ConfirmBody):
    target: str = "api_logs"


def _check_destructive(body: ConfirmBody, actor: dict[str, Any]) -> None:
    row = get_user_by_id(int(actor["id"]))
    try:
        require_destructive_confirm(
            confirm=body.confirm,
            confirm_phrase=body.confirm_phrase,
            production_password=body.production_password,
            actor_password_hash=(row or {}).get("password_hash"),
        )
    except ValidationError as e:
        raise _http(e, 400) from e


@router.get("/overview")
async def overview(user: RequireDeveloper):
    return {
        "role": user.get("role"),
        "environment": app_environment(),
        "destructive_confirm_phrase": DESTRUCTIVE_CONFIRM_PHRASE,
        "panels": [
            "database",
            "sessions",
            "users",
            "activity",
            "api_logs",
            "error_logs",
            "feature_flags",
            "settings",
            "cache",
            "migrations",
            "health",
            "tools",
        ],
        "notes": {
            "passwords": (
                "Plaintext passwords are never stored. Developers see full password_hash "
                "and can set a new password for any user."
            ),
            "webhooks": "Not used by this app; panel reserved.",
            "background_jobs": "No job queue configured; status is N/A.",
        },
    }


@router.get("/sessions")
async def active_sessions(user: RequireDeveloper):
    """Who is currently logged in."""
    return {"sessions": sessions_repo.list_active_sessions()}


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(session_id: str, request: Request, user: RequireDeveloper):
    sessions_repo.delete_session(session_id)
    _audit(
        request,
        user,
        action="session.revoke",
        resource_type="session",
        resource_id=session_id,
        table_name="auth_sessions",
    )
    return {"session_id": session_id, "revoked": True}


@router.get("/users/{user_id}/credentials")
async def user_credentials(user_id: int, user: RequireDeveloper):
    """Full credential visibility for developers (hash — plaintext is not stored)."""
    row = get_user_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    public = public_user_from_row(row)
    return {
        **public,
        "password_hash": row.get("password_hash"),
        "password_algo": (
            "bcrypt"
            if str(row.get("password_hash") or "").startswith(("$2a$", "$2b$", "$2y$"))
            else "unknown"
        ),
        "plaintext_available": False,
        "note": "Plaintext passwords cannot be recovered. Set a new password to take over the account.",
    }


@router.get("/health")
async def health(user: RequireDeveloper):
    return developer_db.system_health()


@router.get("/migrations")
async def migrations(user: RequireDeveloper):
    return developer_db.migration_status()


@router.get("/tables")
async def tables(user: RequireDeveloper):
    return {"tables": developer_db.list_tables()}


@router.get("/tables/{table}")
async def table_schema(table: str, user: RequireDeveloper):
    try:
        return developer_db.describe_table(table)
    except ValidationError as e:
        raise _http(e, 404) from e


@router.get("/tables/{table}/rows")
async def table_rows(
    table: str,
    user: RequireDeveloper,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = "asc",
    reveal_secrets: bool = True,
):
    try:
        return developer_db.query_rows(
            table,
            limit=limit,
            offset=offset,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            reveal_secrets=reveal_secrets,
        )
    except ValidationError as e:
        raise _http(e) from e


@router.post("/tables/{table}/rows")
async def table_create(table: str, body: RecordCreate, request: Request, user: RequireDeveloper):
    try:
        result = developer_db.create_row(table, body.data)
        _audit(
            request,
            user,
            action="db.create",
            resource_type="table_row",
            table_name=table,
            after=result.get("row"),
        )
        return result
    except ValidationError as e:
        raise _http(e) from e


@router.put("/tables/{table}/rows")
async def table_update(table: str, body: RecordUpdate, request: Request, user: RequireDeveloper):
    try:
        result = developer_db.update_row(table, body.pk, body.data)
        _audit(
            request,
            user,
            action="db.update",
            resource_type="table_row",
            table_name=table,
            resource_id=str(body.pk),
            before=result.get("before"),
            after=result.get("row"),
        )
        return result
    except ValidationError as e:
        raise _http(e) from e


@router.post("/tables/{table}/rows/delete")
async def table_delete(table: str, body: RecordDelete, request: Request, user: RequireDeveloper):
    _check_destructive(body, user)
    try:
        result = developer_db.delete_row(table, body.pk)
        _audit(
            request,
            user,
            action="db.delete",
            resource_type="table_row",
            table_name=table,
            resource_id=str(body.pk),
            before=result.get("before"),
        )
        return result
    except ValidationError as e:
        raise _http(e) from e


@router.post("/tables/{table}/rows/bulk-update")
async def table_bulk_update(
    table: str, body: BulkUpdateBody, request: Request, user: RequireDeveloper
):
    _check_destructive(body, user)
    try:
        result = developer_db.bulk_update(table, pk_list=body.pk_list, data=body.data)
        _audit(
            request,
            user,
            action="db.bulk_update",
            resource_type="table_row",
            table_name=table,
            meta={"count": result.get("updated_count"), "data": body.data},
        )
        return result
    except ValidationError as e:
        raise _http(e) from e


@router.post("/tables/{table}/rows/bulk-delete")
async def table_bulk_delete(
    table: str, body: BulkDeleteBody, request: Request, user: RequireDeveloper
):
    _check_destructive(body, user)
    try:
        result = developer_db.bulk_delete(table, pk_list=body.pk_list)
        _audit(
            request,
            user,
            action="db.bulk_delete",
            resource_type="table_row",
            table_name=table,
            meta={"count": result.get("deleted_count")},
            before=[r.get("before") for r in result.get("rows", [])],
        )
        return result
    except ValidationError as e:
        raise _http(e) from e


@router.get("/audit")
async def audit_list(
    user: RequireDeveloper,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    table_name: str | None = None,
):
    return developer_audit_repo.list_audit(
        limit=limit, offset=offset, action=action, table_name=table_name
    )


@router.get("/activity")
async def activity_feed(
    user: RequireDeveloper,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    table_name: str | None = None,
):
    """Alias of audit — full system activity (employees, users, logins, API mutates)."""
    return developer_audit_repo.list_audit(
        limit=limit, offset=offset, action=action, table_name=table_name
    )


@router.get("/api-logs")
async def api_logs(
    user: RequireDeveloper,
    limit: int = 100,
    offset: int = 0,
    status_code: int | None = None,
    path_contains: str | None = None,
    errors_only: bool = False,
):
    return api_logs_repo.list_logs(
        limit=limit,
        offset=offset,
        status_code=status_code,
        path_contains=path_contains,
        errors_only=errors_only,
    )


@router.get("/error-logs")
async def error_logs(user: RequireDeveloper, limit: int = 100, offset: int = 0):
    return api_logs_repo.list_logs(limit=limit, offset=offset, errors_only=True)


@router.get("/feature-flags")
async def flags_list(user: RequireDeveloper):
    return {"flags": feature_flags_repo.list_flags()}


@router.put("/feature-flags")
async def flags_upsert(body: FlagUpsert, request: Request, user: RequireDeveloper):
    before = feature_flags_repo.get_flag(body.flag_key)
    try:
        after = feature_flags_repo.upsert_flag(
            flag_key=body.flag_key,
            enabled=body.enabled,
            description=body.description,
            value=body.value,
            updated_by=int(user["id"]),
        )
    except ValidationError as e:
        raise _http(e) from e
    _audit(
        request,
        user,
        action="feature_flag.upsert",
        resource_type="feature_flag",
        resource_id=body.flag_key,
        before=before,
        after=after,
    )
    return after


@router.delete("/feature-flags/{flag_key}")
async def flags_delete(flag_key: str, request: Request, user: RequireDeveloper):
    before = feature_flags_repo.get_flag(flag_key)
    try:
        result = feature_flags_repo.delete_flag(flag_key)
    except ValidationError as e:
        raise _http(e, 404) from e
    _audit(
        request,
        user,
        action="feature_flag.delete",
        resource_type="feature_flag",
        resource_id=flag_key,
        before=before,
    )
    return result


@router.get("/settings")
async def settings(user: RequireDeveloper):
    health = developer_db.system_health()
    return {
        "environment": health["environment"],
        "masked_env": health["masked_env"],
        "database": {
            "name": health["database"]["name"],
            "host": health["database"]["host"],
            "ok": health["database"]["ok"],
        },
        "note": "Secrets are masked. Change real secrets via secure server env, not this panel.",
    }


@router.post("/cache/clear")
async def cache_clear(body: CacheClearBody, request: Request, user: RequireDeveloper):
    _check_destructive(body, user)
    target = (body.target or "").strip().lower()
    if target == "api_logs":
        result = api_logs_repo.clear_logs()
    else:
        raise HTTPException(status_code=400, detail="Unknown cache target. Use api_logs.")
    _audit(
        request,
        user,
        action="cache.clear",
        resource_type="cache",
        resource_id=target,
        meta=result,
    )
    return result


@router.get("/jobs")
async def jobs_status(user: RequireDeveloper):
    return {
        "queue": None,
        "jobs": [],
        "message": "No background job runner is configured in this project.",
    }


@router.get("/webhooks")
async def webhooks_status(user: RequireDeveloper):
    return {
        "webhooks": [],
        "message": "No webhook integrations are configured in this project.",
    }
