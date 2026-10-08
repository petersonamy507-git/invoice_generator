# Invoice Finance API — backend on one PC, frontend on another

**Setup this project uses:**

| Role | Where it runs | What to share |
|------|----------------|---------------|
| **Backend (API)** | This PC (Invoice_finance + MySQL + Word/LibreOffice) | LAN URL, e.g. `http://10.100.4.15:8000` |
| **Frontend (Vite)** | Another system / another repo | Calls that API URL only — no backend install needed |

Copy this `API.md` to the frontend machine/repo. The frontend never needs the Python project — only the API base URL.

| Who | Base URL to use |
|-----|-----------------|
| Browser / Vite on **this** PC | `http://127.0.0.1:8000` |
| Vite / browser on **another** PC (same LAN) | `http://<THIS-PC-LAN-IP>:8000` (example: `http://10.100.4.15:8000`) |
| Deployed server | `https://api.your-domain.com` |

Find this PC’s LAN IP (API host):

```powershell
# Windows (API PC)
ipconfig
# use IPv4 Address of Ethernet / Wi-Fi (not 127.0.0.1)
```

```bash
# macOS / Linux (API PC)
ip addr   # or: hostname -I
```

Interactive Swagger: `{BASE_URL}/docs`  
OpenAPI JSON: `{BASE_URL}/openapi.json`

---

## 1. API host (this PC) — run so other systems can connect

On the **backend PC** (project root):

```bash
# IMPORTANT: 0.0.0.0 = listen on LAN (not only localhost)
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Checklist on this PC:

1. MySQL + `.env` configured
2. Server started with `--host 0.0.0.0 --port 8000`
3. Windows Firewall allows inbound **TCP 8000** (Private network)
4. Tell the frontend team: `http://<YOUR-LAN-IP>:8000`  
   Example right now: `http://10.100.4.15:8000`

Health check **on this PC**:

```bash
curl -s "http://127.0.0.1:8000/api/health"
# {"status":"ok","service":"invoice-generation","version":"1.2.0"}
```

Health check **from the other PC** (must work before frontend will):

```bash
curl -s "http://10.100.4.15:8000/api/health"
# same JSON — if this fails, fix firewall / IP / uvicorn host
```

Windows Firewall (API PC, PowerShell as Admin) if LAN cannot connect:

```powershell
New-NetFirewallRule -DisplayName "Invoice Finance API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

### 1.1 Live server (AWS / Linux) — required setup

Microsoft Word / `pywin32` are **Windows-only**. On live Linux the API now:

1. **Fills** templates 6–14 via **OOXML** (edits the `.docx` zip so header drawings stay)  
2. **Converts** DOCX→PDF with **LibreOffice**

```bash
# Ubuntu / Debian (EC2)
sudo apt-get update
sudo apt-get install -y libreoffice-writer
pip install -r requirements.txt   # includes lxml

# Confirm
which soffice || which libreoffice
soffice --version
```

Optional in API `.env`:

```env
SOFFICE_PATH=/usr/bin/soffice
```

Deploy checklist:

1. Pull latest code (includes `word_ooxml_fill.py`)
2. Upload full `Data/word/` templates
3. Install LibreOffice + restart uvicorn
4. Test: `POST /api/employees/generate` with `invoice_template: 11`

| Host | DOCX fill (6–14) | PDF |
|------|------------------|-----|
| Windows (local) | Microsoft Word COM | Word COM |
| AWS Linux (live) | OOXML zip edit (keeps drawings) | LibreOffice headless |

---

## 2. Frontend on another system (Vite) — call this PC’s API

Frontend PC only needs Node/Vite. It talks to the backend PC over the network.

Replace `10.100.4.15` below with **this backend PC’s real LAN IP**.

### 2.1 Env on the frontend PC

In the Vite project root, create `.env` / `.env.local`:

```env
# Backend runs on the OTHER PC — use that machine's LAN IP (not 127.0.0.1)
VITE_API_BASE_URL=http://10.100.4.15:8000
```

Do **not** use `http://127.0.0.1:8000` on the frontend PC — that points at itself, not the API host.

### 2.2 Recommended — direct call to API PC (simplest for two machines)

1. Frontend `.env`:

```env
VITE_API_BASE_URL=http://10.100.4.15:8000
```

2. On the **API PC** `.env`, allow the frontend origin(s):

```env
# Frontend may run as localhost:5173 on the other PC, or via that PC's LAN IP
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://10.100.4.20:5173
```

Use the **frontend PC’s** IP in `CORS_ORIGINS` if users open the Vite app as `http://<frontend-ip>:5173`.  
If they only open `http://localhost:5173` on the frontend PC, `http://localhost:5173` is enough.

3. Restart API on this PC after changing `CORS_ORIGINS`
4. Always use `credentials: "include"` (cookie session)

> Browsers reject `Access-Control-Allow-Origin: *` with cookies. List each frontend origin explicitly.

### 2.3 Optional — Vite proxy on the frontend PC

Proxy target must be the **API PC**, not localhost:

```ts
// vite.config.ts on the FRONTEND machine
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // optional: allow other devices to open this Vite UI
    proxy: {
      "/api": {
        target: "http://10.100.4.15:8000", // API host LAN IP
        changeOrigin: true,
      },
    },
  },
});
```

Then set `VITE_API_BASE_URL=` (empty) and call `/api/...` relatively.  
Still add the Vite origin to API `CORS_ORIGINS` only if you are **not** proxying (direct mode). With proxy, the browser talks to Vite same-origin; Vite server talks to the API PC.

### 2.4 Shared API client (`src/api/client.ts`)

```ts
const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include", // required: invoice_session cookie
    headers,
  });

  if (res.status === 401) {
    // redirect to your login route
    throw new ApiError(401, "Unauthorized");
  }

  const ct = res.headers.get("content-type") || "";
  if (!res.ok) {
    let detail = res.statusText;
    if (ct.includes("application/json")) {
      const j = await res.json().catch(() => null);
      detail = (j && (j.detail || j.message)) || detail;
    }
    throw new ApiError(res.status, String(detail));
  }

  if (res.status === 204) return undefined as T;
  if (ct.includes("application/json")) return res.json() as Promise<T>;
  return res.blob() as Promise<T>; // ZIP / PDF downloads
}

export const auth = {
  login: (identifier: string, password: string) =>
    api<{ user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    }),
  me: () => api<{ authenticated: boolean; user: User | null }>("/api/auth/me"),
  logout: () => api<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
};

/** Team portal logins (MySQL `users`). Admin-only except login/me. */
export const teamUsers = {
  list: () => api<{ users: User[] }>("/api/users"),
  create: (body: UserCreate) =>
    api<User>("/api/users", { method: "POST", body: JSON.stringify(body) }),
  update: (id: number, body: UserUpdate) =>
    api<User>(`/api/users/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  setPassword: (id: number, password: string, confirm_password: string) =>
    api<{ id: number; password_updated: boolean }>(`/api/users/${id}/password`, {
      method: "POST",
      body: JSON.stringify({ password, confirm_password }),
    }),
  remove: (id: number) =>
    api<{ id: number; deleted: boolean }>(`/api/users/${id}`, { method: "DELETE" }),
};

export type User = {
  id: number;
  username: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
  last_login?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type UserCreate = {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
  role?: "admin" | "user"; // default "user"
  is_active?: boolean; // default true
};

export type UserUpdate = {
  username?: string;
  email?: string;
  role?: "admin" | "user";
  is_active?: boolean;
};
```

### 2.5 Example usage

```ts
import { api, auth, teamUsers } from "./api/client";

await auth.login("admin", "Admin@12345");

// Add a teammate who can log in to the portal (saved in MySQL users)
await teamUsers.create({
  username: "mansoor",
  email: "mansoor@company.com",
  password: "TeamPass123",
  confirm_password: "TeamPass123",
  role: "user",
  is_active: true,
});
const { users } = await teamUsers.list();

const { employees } = await api<{ employees: unknown[] }>("/api/employees?department=QA");

// Download invoice ZIP
const zip = await api<Blob>("/api/employees/generate", {
  method: "POST",
  body: JSON.stringify({
    employees: [
      {
        employee_id: "EMP001",
        amount: 25000,
        invoice_no: "HH-007",
        invoice_template: 11,
      },
    ],
  }),
});
const url = URL.createObjectURL(zip);
const a = document.createElement("a");
a.href = url;
a.download = "invoices.zip";
a.click();
URL.revokeObjectURL(url);
```

| Topic | Rule |
|--------|------|
| Cookies | Always `credentials: "include"` |
| 401 | Send user to login |
| CORS | List Vite origin in API `CORS_ORIGINS` (or use proxy) |
| Binary | Treat non-JSON success as `Blob` (ZIP/PDF) |

---

## 3. Auth (cookie session)

- Cookie name: `invoice_session` (HTTP-only, ~12 hours)
- Roles: `admin` \| `user`
- No session → `401`. Non-admin on admin routes → `403`

Default seeded admin (from API host `.env` on first startup):

| Field | Value |
|-------|--------|
| Username | `admin` |
| Email | `admin@example.com` |
| Password | `Admin@12345` |

### curl (any OS)

```bash
export BASE_URL="http://127.0.0.1:8000"

curl -s -c cookies.txt -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"admin\",\"password\":\"Admin@12345\"}"

curl -s -b cookies.txt "$BASE_URL/api/auth/me"
curl -s -b cookies.txt -c cookies.txt -X POST "$BASE_URL/api/auth/logout"
```

PowerShell: use `$env:BASE_URL` and `curl.exe` the same way.

---

## 4. Endpoint reference

All paths are under `{BASE_URL}`. Auth = cookie required unless noted.

### Public

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/health` | No auth |
| POST | `/api/auth/login` | Body: `{ identifier, password }` → sets cookie |
| POST | `/api/auth/logout` | Clears cookie |
| GET | `/api/auth/me` | `{ authenticated, user }` |

### Team logins / users (admin only)

Portal login accounts live in MySQL **`users`**.  
This is **not** the Employees list (invoice people with IBAN). Only **`role: "admin"`** can call these.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/users` | admin | List all team logins |
| POST | `/api/users` | admin | **Add team login** (create user) |
| PUT | `/api/users/{id}` | admin | Update username / email / role / active |
| POST | `/api/users/{id}/password` | admin | Reset password |
| DELETE | `/api/users/{id}` | admin | Delete login |

See **§4.1** below for full request/response bodies and Vite examples.

### Departments / employees

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/departments` | `QA`, `Devops`, `Call centre`, `Account`, `HR` |
| GET | `/api/employees` | Query: `?department=` |
| GET | `/api/employees/{employee_id}` | |
| POST | `/api/employees` | `{ employee_id, name, department, iban, bank_name, branch_code, last_invoice? }` |
| PUT | `/api/employees/{employee_id}` | Partial update fields |
| DELETE | `/api/employees/{employee_id}` | Hard delete |
| POST | `/api/employees/generate` | See below → **ZIP of PDFs** |

### 4.1 Team login API (send this to Vite frontend)

**Important**

- Cookie session required (`credentials: "include"`).
- Caller must be logged in as **admin** (else `403`).
- Password min length: **8**. `password` and `confirm_password` must match.
- `role`: `"admin"` \| `"user"` (default `"user"`).
- Teammates log in with `POST /api/auth/login` using `username` **or** `email` as `identifier`.

#### Add team login — `POST /api/users`

Request:

```json
{
  "username": "mansoor",
  "email": "mansoor@company.com",
  "password": "TeamPass123",
  "confirm_password": "TeamPass123",
  "role": "user",
  "is_active": true
}
```

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `username` | string | yes | Unique |
| `email` | string | yes | Unique, must contain `@` |
| `password` | string | yes | ≥ 8 chars |
| `confirm_password` | string | yes | Must equal `password` |
| `role` | `"admin"` \| `"user"` | no | Default `"user"` |
| `is_active` | boolean | no | Default `true` |

Response `200` (also shape of each user in list):

```json
{
  "id": 9,
  "username": "mansoor",
  "email": "mansoor@company.com",
  "role": "user",
  "is_active": true,
  "last_login": null,
  "created_at": "2026-10-09 03:00:00",
  "updated_at": "2026-10-09 03:00:00"
}
```

Errors: `400` validation / duplicate username or email; `401` not logged in; `403` not admin.

#### List — `GET /api/users`

```json
{ "users": [ /* User objects */ ] }
```

#### Update — `PUT /api/users/{id}`

```json
{
  "username": "mansoor",
  "email": "mansoor@company.com",
  "role": "user",
  "is_active": true
}
```

All fields optional; omit unchanged ones.

#### Reset password — `POST /api/users/{id}/password`

```json
{
  "password": "NewPass123",
  "confirm_password": "NewPass123"
}
```

Response: `{ "id": 9, "password_updated": true }`

#### Delete — `DELETE /api/users/{id}`

Response: `{ "id": 9, "deleted": true }`

#### curl examples

```bash
export BASE_URL="http://127.0.0.1:8000"

# 1) Admin login (saves cookie)
curl -s -c cookies.txt -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"admin\",\"password\":\"Admin@12345\"}"

# 2) Add team login
curl -s -b cookies.txt -X POST "$BASE_URL/api/users" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"jane\",\"email\":\"jane@company.com\",\"password\":\"UserPass123\",\"confirm_password\":\"UserPass123\",\"role\":\"user\",\"is_active\":true}"

# 3) List team
curl -s -b cookies.txt "$BASE_URL/api/users"

# 4) Teammate login (their own session)
curl -s -c team.txt -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"jane\",\"password\":\"UserPass123\"}"
```

#### Vite / fetch example

```ts
// After admin login:
await fetch(`${BASE}/api/users`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    username: "jane",
    email: "jane@company.com",
    password: "UserPass123",
    confirm_password: "UserPass123",
    role: "user",
    is_active: true,
  }),
});

const res = await fetch(`${BASE}/api/users`, { credentials: "include" });
const { users } = await res.json();
```

Or use `teamUsers` from §2.4.

**UI hint:** Show “Team Logins” / “Add user” only when `user.role === "admin"`.

---

**Generate invoices**

```json
{
  "employees": [
    {
      "employee_id": "EMP001",
      "amount": 25000,
      "invoice_no": "HH-007",
      "invoice_template": 1
    }
  ]
}
```

- Request `invoice_no` = current **last invoice**
- PDF uses **last + 1**, then saves that as new `last_invoice`
- `invoice_template`: `1`–`14`
- Response: `application/zip`

### Clubbing / history / status

| Method | Path | Query |
|--------|------|--------|
| GET | `/api/clubbing` | `department` |
| GET | `/api/invoice-history` | `employee_id`, `department`, `limit` |
| GET | `/api/templates/status` | Word template presence |
| GET | `/api/categories/status` | |

### Legacy / file uploads

| Method | Path | Form fields | Response |
|--------|------|-------------|----------|
| POST | `/api/manual/generate` | `person_name`, `company_name`, `email`, `total_amount`, `invoice_number` | PDF |
| POST | `/api/bulk/generate` | `category`, `current_month` (file) | ZIP |
| POST | `/api/bulk/payment-generate` | `sheet` (file) | ZIP |
| POST | `/api/word-test/generate` | `sheet` (file) | ZIP |

---

## 5. curl cheat sheet

```bash
# From API PC:
export BASE_URL="http://127.0.0.1:8000"
# From another PC on LAN (use API host IP):
# export BASE_URL="http://10.100.4.15:8000"

# Login
curl -s -c cookies.txt -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"admin\",\"password\":\"Admin@12345\"}"

# Employees
curl -s -b cookies.txt "$BASE_URL/api/employees"
curl -s -b cookies.txt "$BASE_URL/api/employees?department=QA"

curl -s -b cookies.txt -X POST "$BASE_URL/api/employees" \
  -H "Content-Type: application/json" \
  -d "{\"employee_id\":\"EMP001\",\"name\":\"Ali Khan\",\"department\":\"QA\",\"iban\":\"PK00XXXX0000000000000000\",\"bank_name\":\"HBL\",\"branch_code\":\"1234\",\"last_invoice\":\"HH-007\"}"

# Generate ZIP
curl -s -b cookies.txt -X POST "$BASE_URL/api/employees/generate" \
  -H "Content-Type: application/json" \
  -o invoices.zip \
  -d "{\"employees\":[{\"employee_id\":\"EMP001\",\"amount\":25000,\"invoice_no\":\"HH-007\",\"invoice_template\":1}]}"

# Clubbing / history
curl -s -b cookies.txt "$BASE_URL/api/clubbing?department=Call%20centre"
curl -s -b cookies.txt "$BASE_URL/api/invoice-history?employee_id=EMP001&limit=50"
```

---

## 6. Invoice templates (frontend)

Full template list for UI dropdowns: see **`TEMPLATES.md`** (same folder / Desktop).

- `invoice_template` values: **1–14**
- Live list: `GET /api/templates/status` → each item has `id`, `label`, `name`, `exists`

---

## 7. Two-machine checklist

### On this PC (backend)

1. Start API: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`
2. Note LAN IP (example: `10.100.4.15`)
3. Allow firewall TCP **8000**
4. Set `CORS_ORIGINS` to include the frontend origin(s), then restart API
5. Confirm locally: `curl http://127.0.0.1:8000/api/health`

### On the other PC (frontend / Vite)

1. Copy this `API.md` into the Vite repo
2. Set `VITE_API_BASE_URL=http://10.100.4.15:8000` (API PC IP)
3. From that PC, confirm: `curl http://10.100.4.15:8000/api/health`
4. Use the `api()` helper with `credentials: "include"`
5. Login → `/api/auth/me` on boot → redirect to login on `401`
6. Admin UI: Team Logins via `GET/POST /api/users` (see §4.1) — only if `role === "admin"`
7. ZIP/PDF downloads: treat response as `Blob`
8. Optional: types from `http://10.100.4.15:8000/openapi.json`

### Quick troubleshooting

| Problem | Fix |
|---------|-----|
| Frontend gets connection refused | API not on `0.0.0.0`, wrong IP, or firewall blocking 8000 |
| `curl` from other PC fails | Same as above; test IP with `ping` first |
| Login works in curl but not browser | Add Vite origin to `CORS_ORIGINS`; use `credentials: "include"` |
| Frontend uses `127.0.0.1` | Wrong — that is the frontend PC itself; use API PC LAN IP |
