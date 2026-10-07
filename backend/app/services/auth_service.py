from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

from backend.app.db import sessions_repo
from backend.app.db.users_repo import (
    create_user,
    find_user_by_identifier,
    public_user_from_row,
    touch_last_login,
)
from backend.app.services.password_utils import verify_password
from backend.app.services.validation import ValidationError

SESSION_COOKIE = "invoice_session"
LOGIN_FAIL_MESSAGE = "Invalid username/email or password."


class LoginRateLimiter:
    """Simple in-memory sliding-window limiter (per process)."""

    def __init__(self, max_attempts: int = 8, window_seconds: int = 300) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_seconds:
                q.popleft()
            if len(q) >= self.max_attempts:
                raise ValidationError(
                    "Too many login attempts. Please try again later."
                )

    def hit(self, key: str) -> None:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_seconds:
                q.popleft()
            q.append(now)


login_rate_limiter = LoginRateLimiter()


def authenticate_login(identifier: str, password: str, *, client_key: str) -> tuple[dict, str]:
    login_rate_limiter.check(client_key)
    user = find_user_by_identifier(identifier)
    if not user or not verify_password(password, user["password_hash"]):
        login_rate_limiter.hit(client_key)
        raise ValidationError(LOGIN_FAIL_MESSAGE)
    if not user.get("is_active"):
        login_rate_limiter.hit(client_key)
        raise ValidationError(LOGIN_FAIL_MESSAGE)

    session_id = sessions_repo.create_session(int(user["id"]))
    touch_last_login(int(user["id"]))
    return public_user_from_row(user), session_id


def ensure_initial_admin() -> None:
    username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
    email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "").strip()
    if not username or not email or not password:
        return
    existing = find_user_by_identifier(username) or find_user_by_identifier(email)
    if existing:
        return
    create_user(
        username=username,
        email=email,
        password=password,
        role="admin",
        is_active=True,
    )
