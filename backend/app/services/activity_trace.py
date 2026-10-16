"""Request-scoped activity tracing for the Developer Panel."""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_actor: ContextVar[dict[str, Any] | None] = ContextVar("activity_actor", default=None)
_ip: ContextVar[str | None] = ContextVar("activity_ip", default=None)
_ua: ContextVar[str | None] = ContextVar("activity_ua", default=None)


def set_request_context(
    *,
    actor: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    _actor.set(actor)
    _ip.set(ip_address)
    _ua.set((user_agent or "")[:512] or None)


def clear_request_context() -> None:
    _actor.set(None)
    _ip.set(None)
    _ua.set(None)


def current_actor() -> dict[str, Any] | None:
    return _actor.get()


def trace(
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    table_name: str | None = None,
    before: Any = None,
    after: Any = None,
    meta: Any = None,
    actor: dict[str, Any] | None = None,
) -> None:
    """Best-effort audit write — never raises into business logic."""
    try:
        from backend.app.db import developer_audit_repo

        developer_audit_repo.record_audit(
            actor=actor if actor is not None else current_actor(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            table_name=table_name,
            before=before,
            after=after,
            meta=meta,
            ip_address=_ip.get(),
            user_agent=_ua.get(),
        )
    except Exception:
        pass
