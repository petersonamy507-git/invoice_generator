from __future__ import annotations

from typing import Annotated, Any

from fastapi import Cookie, Depends, HTTPException, Request

from backend.app.db import sessions_repo
from backend.app.db.users_repo import get_user_by_id, public_user_from_row
from backend.app.services.auth_service import SESSION_COOKIE


def _load_user_from_session(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    user_id = sessions_repo.get_session_user_id(session_id)
    if not user_id:
        return None
    row = get_user_by_id(user_id)
    if not row or not row.get("is_active"):
        if session_id:
            sessions_repo.delete_session(session_id)
        return None
    return public_user_from_row(row)


async def get_optional_user(
    request: Request,
    invoice_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict[str, Any] | None:
    return _load_user_from_session(invoice_session)


async def require_user(
    user: Annotated[dict[str, Any] | None, Depends(get_optional_user)] = None,
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def require_role(*roles: str):
    allowed = {r.lower() for r in roles}

    async def _dep(
        user: Annotated[dict[str, Any], Depends(require_user)],
    ) -> dict[str, Any]:
        if str(user.get("role", "")).lower() not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return _dep


RequireUser = Annotated[dict[str, Any], Depends(require_user)]
RequireAdmin = Annotated[dict[str, Any], Depends(require_role("admin"))]
OptionalUser = Annotated[dict[str, Any] | None, Depends(get_optional_user)]
