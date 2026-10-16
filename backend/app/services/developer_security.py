"""Security helpers for Developer Panel data access."""
from __future__ import annotations

import os
import re
from typing import Any

from backend.app.services.validation import ValidationError

SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|credential|auth[_-]?code|"
    r"db_password|encryption[_-]?key|signing[_-]?key)",
    re.IGNORECASE,
)

MASK = "***REDACTED***"

# Tables developers may mutate freely (all app tables). System/meta tables blocked.
BLOCKED_TABLES = frozenset(
    {
        "information_schema",
        "mysql",
        "performance_schema",
        "sys",
    }
)

DESTRUCTIVE_CONFIRM_PHRASE = "CONFIRM"


def app_environment() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()


def is_production() -> bool:
    return app_environment() in {"production", "prod"}


def is_sensitive_field(name: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(str(name or "")))


def mask_record(record: dict[str, Any] | None, *, reveal_secrets: bool = False) -> dict[str, Any] | None:
    if record is None:
        return None
    if reveal_secrets:
        return dict(record)
    out: dict[str, Any] = {}
    for k, v in record.items():
        if is_sensitive_field(str(k)):
            out[k] = MASK if v not in (None, "") else v
        else:
            out[k] = v
    return out


def mask_records(
    rows: list[dict[str, Any]], *, reveal_secrets: bool = False
) -> list[dict[str, Any]]:
    return [mask_record(r, reveal_secrets=reveal_secrets) or {} for r in rows]


def require_destructive_confirm(
    *,
    confirm: bool,
    confirm_phrase: str | None = None,
    production_password: str | None = None,
    actor_password_hash: str | None = None,
) -> None:
    if not confirm:
        raise ValidationError("Destructive action requires confirm=true.")
    phrase = (confirm_phrase or "").strip()
    if phrase != DESTRUCTIVE_CONFIRM_PHRASE:
        raise ValidationError(
            f'Destructive action requires confirm_phrase="{DESTRUCTIVE_CONFIRM_PHRASE}".'
        )
    if is_production():
        if not production_password:
            raise ValidationError(
                "Production destructive actions require re-authentication password."
            )
        from backend.app.services.password_utils import verify_password

        if not actor_password_hash or not verify_password(
            production_password, actor_password_hash
        ):
            raise ValidationError("Re-authentication failed.")


def assert_safe_identifier(name: str, *, kind: str = "identifier") -> str:
    value = str(name or "").strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValidationError(f"Invalid {kind}.")
    return value
