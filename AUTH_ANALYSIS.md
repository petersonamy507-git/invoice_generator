# Authentication Analysis — invoice_generation

## 1–4. Current stack

| Area | Finding |
|------|---------|
| Backend | FastAPI (`backend/app/main.py`) |
| Frontend | Static HTML/JS (`frontend/`), no SPA router |
| DB | MySQL via **PyMySQL** + custom migrations |
| ORM | None (raw SQL) |
| Env | `.env` via `python-dotenv` |
| Existing auth | **None** |

## 5. Proposed `users` schema

```sql
users (
  id BIGINT PK AI,
  username VARCHAR(64) UNIQUE NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','user') NOT NULL DEFAULT 'user',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  last_login DATETIME NULL,
  created_at / updated_at
)
auth_sessions (
  id CHAR(64) PK,          -- random session token
  user_id BIGINT FK users,
  expires_at DATETIME,
  created_at DATETIME,
  INDEX (user_id), INDEX (expires_at)
)
```

**No `employee_id` on users. No FK to employees.**

## 6. Auth mechanism

**Server-side sessions + HttpOnly cookie** (`invoice_session`):
- Fits static same-origin frontend
- Logout can invalidate immediately
- Avoids JWT in localStorage

Password hashing: **bcrypt** (passlib).

## 7–8. Files

**Modify:** `main.py`, `migrate.py`, `requirements.txt`, `.env` / `.env.example`, `frontend/index.html`, `app.js`, `styles.css`, `memory.md`

**Create:** migrations `002_users.sql`, auth services/repos, `login.html`, auth tests

## 9. Protected endpoints

All `/api/employees*`, `/api/clubbing`, `/api/invoice-history`, `/api/categories*`, `/api/templates*`, `/api/bulk*`, `/api/manual*`, `/api/word-test*`, `/api/departments`, `/api/users*`

**Public:** `GET /`, `/login.html`, `/static/*`, `POST /api/auth/login`, `GET /api/auth/me` (returns authenticated false), `POST /api/auth/logout`

## 10. Roles

- **admin:** full app + user management
- **user:** invoice workflow (employees view/select/generate, excel bulk, templates)

## 11. Initial admin

Env: `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` — created once if missing.

## 12. Compatibility

Auth wraps existing APIs; employee/club/invoice logic unchanged. Frontend shows login gate before dashboard.
