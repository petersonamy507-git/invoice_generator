import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.app.db.migrate import run_migrations
from backend.app.db.users_repo import create_user, delete_user, find_user_by_identifier
from backend.app.main import app
from backend.app.services.auth_service import ensure_initial_admin
from backend.app.services.password_utils import hash_password, verify_password
from backend.app.services.validation import ValidationError


def test_password_hashing():
    hashed = hash_password("SecretPass1")
    assert hashed != "SecretPass1"
    assert verify_password("SecretPass1", hashed)
    assert not verify_password("wrong", hashed)


def test_auth_flow_and_protection():
    run_migrations()
    ensure_initial_admin()

    # Clean leftover test user
    existing = find_user_by_identifier("auth_test_user")
    if existing:
        delete_user(int(existing["id"]))

    admin = find_user_by_identifier("admin")
    assert admin is not None

    client = TestClient(app)

    # Unauthenticated employees API
    res = client.get("/api/employees")
    assert res.status_code == 401

    # Bad login
    bad = client.post(
        "/api/auth/login",
        json={"identifier": "admin", "password": "definitely-wrong"},
    )
    assert bad.status_code == 400

    # Good login
    login = client.post(
        "/api/auth/login",
        json={"identifier": "admin", "password": "Admin@12345"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"
    assert "invoice_session" in login.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is True

    # Protected endpoint works
    emp = client.get("/api/employees?department=QA")
    assert emp.status_code == 200

    # Create normal user as admin
    created = client.post(
        "/api/users",
        json={
            "username": "auth_test_user",
            "email": "auth_test_user@example.com",
            "password": "UserPass123",
            "confirm_password": "UserPass123",
            "role": "user",
            "is_active": True,
        },
    )
    assert created.status_code == 200
    user_id = created.json()["id"]

    # Duplicate username
    dup = client.post(
        "/api/users",
        json={
            "username": "auth_test_user",
            "email": "other@example.com",
            "password": "UserPass123",
            "confirm_password": "UserPass123",
            "role": "user",
            "is_active": True,
        },
    )
    assert dup.status_code == 400

    client.post("/api/auth/logout")
    assert client.get("/api/employees").status_code == 401

    # Normal user cannot manage users
    user_login = client.post(
        "/api/auth/login",
        json={"identifier": "auth_test_user@example.com", "password": "UserPass123"},
    )
    assert user_login.status_code == 200
    forbidden = client.get("/api/users")
    assert forbidden.status_code == 403

    # Cleanup as admin
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"identifier": "admin", "password": "Admin@12345"},
    )
    deleted = client.delete(f"/api/users/{user_id}")
    assert deleted.status_code == 200


if __name__ == "__main__":
    test_password_hashing()
    test_auth_flow_and_protection()
    print("Auth tests passed.")
